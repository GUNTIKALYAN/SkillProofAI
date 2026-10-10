from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

from skillgraph.ontology import Edge, Resolved, normalize_name
from skillgraph.paths import MAX_HOPS, Hop, adjacency, ancestors, best_path, path_reason
from skillgraph.schemas import (
    JD_MATCH_LABEL,
    AuditItem,
    AuditResult,
    BreakdownItem,
    CanonicalSkill,
    ExplainSkill,
    RelatedItem,
    RelatedSkills,
    ScoreMatch,
    WhatIfLearn,
)

EXACT_POINTS = 1.0
REQUIRED_WEIGHT = 2.0
PREFERRED_WEIGHT = 1.0
NEIGHBOUR_MIN = 0.4
NEIGHBOUR_MAX = 0.7


class SkillStore(Protocol):
    def resolve(self, text: str) -> Resolved | None: ...

    def edges(self) -> list[Edge]: ...

    def aliases(self, canonical: str) -> list[str]: ...


def canonicalize(store: SkillStore, text: str) -> CanonicalSkill:
    resolved = store.resolve(text)
    if resolved is None:
        return CanonicalSkill(
            input=text,
            key=normalize_name(text),
            known=False,
            canonical=None,
            category=None,
            match="unknown",
            ancestors=[],
        )
    return CanonicalSkill(
        input=text,
        key=resolved.key,
        known=True,
        canonical=resolved.canonical,
        category=resolved.category,
        match=resolved.kind,
        ancestors=ancestors(store.edges(), resolved.canonical),
    )


def score_match(
    store: SkillStore,
    jd_skills: list[tuple[str, str]],
    candidate_skills: list[str],
) -> ScoreMatch:
    edges = store.edges()
    graph = adjacency(edges)
    breakdown = [
        _score_one(store, name, priority, candidate_skills, graph)
        for name, priority in _unique_jd(jd_skills)
    ]
    return ScoreMatch(label=JD_MATCH_LABEL, score=_overall(breakdown), breakdown=breakdown)


def audit_skills(
    store: SkillStore,
    jd_skills: list[tuple[str, str]],
    candidate_skills: list[str],
) -> AuditResult:
    scored = score_match(store, jd_skills, candidate_skills)
    return AuditResult(
        items=[
            AuditItem(skill=item.skill, status=_status(item), reason=item.reason)
            for item in scored.breakdown
        ]
    )


def related_skills(store: SkillStore, skill: str) -> RelatedSkills:
    resolved = store.resolve(skill)
    if resolved is None:
        return RelatedSkills(skill=skill, known=False, related=[])
    related: list[RelatedItem] = []
    for edge in store.edges():
        if edge.source == resolved.canonical:
            related.append(RelatedItem(skill=edge.target, relation=edge.relation, weight=edge.weight))
        elif edge.target == resolved.canonical:
            related.append(RelatedItem(skill=edge.source, relation=edge.relation, weight=edge.weight))
    related.sort(key=lambda item: (item.relation, item.skill))
    return RelatedSkills(skill=resolved.canonical, known=True, related=related)


def explain_skill(store: SkillStore, skill: str) -> ExplainSkill:
    found = canonicalize(store, skill)
    if not found.known or found.canonical is None:
        return ExplainSkill(
            input=skill,
            known=False,
            canonical=None,
            category=None,
            match="unknown",
            aliases=[],
            ancestors=[],
            relations=[],
        )
    relations = related_skills(store, found.canonical).related
    return ExplainSkill(
        input=skill,
        known=True,
        canonical=found.canonical,
        category=found.category,
        match=found.match,
        aliases=store.aliases(found.canonical),
        ancestors=found.ancestors,
        relations=relations,
    )


def what_if_learn(
    store: SkillStore,
    skill: str,
    candidate_skills: list[str],
    jd_skills: list[tuple[str, str]],
) -> WhatIfLearn:
    before = score_match(store, jd_skills, candidate_skills)
    after = score_match(store, jd_skills, [*candidate_skills, skill])
    learned = store.resolve(skill)
    return WhatIfLearn(
        skill=learned.canonical if learned else skill,
        known=learned is not None,
        before=before.score,
        after=after.score,
        delta=_round(after.score - before.score),
        breakdown=after.breakdown,
    )


def _unique_jd(jd_skills: list[tuple[str, str]]) -> list[tuple[str, str]]:
    chosen: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name, priority in jd_skills:
        if priority not in {"required", "preferred"}:
            raise ValueError("Skill priority must be required or preferred")
        key = normalize_name(name) or name.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        chosen.append((name.strip(), priority))
    return chosen


def _score_one(
    store: SkillStore,
    name: str,
    priority: str,
    candidate_skills: list[str],
    graph: dict[str, list[Hop]],
) -> BreakdownItem:
    target = store.resolve(name)
    if target is None:
        return BreakdownItem(
            skill=name.strip(),
            canonical=None,
            priority=priority,
            points=0.0,
            kind="unknown",
            reason="not in the skill graph",
        )
    best: tuple[tuple[float, int, int, str], BreakdownItem] | None = None
    for raw in candidate_skills:
        resolved = store.resolve(raw)
        if resolved is None:
            continue
        item, rank = _candidate_item(name, priority, target, resolved, graph)
        if best is None or rank < best[0]:
            best = (rank, item)
    if best is None:
        return BreakdownItem(
            skill=name.strip(),
            canonical=target.canonical,
            priority=priority,
            points=0.0,
            kind="missing",
            reason="no matching skill in the graph",
        )
    return best[1]


def _candidate_item(
    jd_name: str,
    priority: str,
    target: Resolved,
    resolved: Resolved,
    graph: dict[str, list[Hop]],
) -> tuple[BreakdownItem, tuple[float, int, int, str]]:
    if resolved.canonical == target.canonical:
        kind = "alias" if resolved.kind == "alias" else "exact"
        reason = (
            f"alias of {target.canonical}" if kind == "alias" else f"exact match on {target.canonical}"
        )
        item = BreakdownItem(
            skill=jd_name.strip(),
            canonical=target.canonical,
            priority=priority,
            points=EXACT_POINTS,
            kind=kind,
            reason=reason,
        )
        exact_rank = 0 if kind == "exact" else 1
        return item, (-EXACT_POINTS, 0, exact_rank, resolved.canonical)
    path = best_path(graph, resolved.canonical, target.canonical)
    if path is None:
        return (
            BreakdownItem(
                skill=jd_name.strip(),
                canonical=target.canonical,
                priority=priority,
                points=0.0,
                kind="missing",
                reason="no matching skill in the graph",
            ),
            (0.0, MAX_HOPS + 1, 1, resolved.canonical),
        )
    points = _round(min(NEIGHBOUR_MAX, max(NEIGHBOUR_MIN, min(hop.weight for hop in path))))
    item = BreakdownItem(
        skill=jd_name.strip(),
        canonical=target.canonical,
        priority=priority,
        points=points,
        kind="neighbour",
        reason=path_reason(resolved.canonical, path),
    )
    return item, (-points, len(path), 1, resolved.canonical)


def _overall(breakdown: list[BreakdownItem]) -> float:
    if not breakdown:
        return 0.0
    weighted = 0.0
    total = 0.0
    for item in breakdown:
        weight = REQUIRED_WEIGHT if item.priority == "required" else PREFERRED_WEIGHT
        weighted += item.points * weight
        total += weight
    return _round(weighted / total)


def _status(item: BreakdownItem) -> str:
    if item.points >= EXACT_POINTS:
        return "matched"
    if item.points > 0:
        return "partial"
    return "missing"


def _round(value: float) -> float:
    quantized = Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return float(quantized)
