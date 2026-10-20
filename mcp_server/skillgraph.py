import re
import threading
from collections import deque
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal, Protocol

from neo4j import Driver
from pydantic import BaseModel, Field

_NAME = re.compile(r"[^a-z0-9+#]+")
MAX_HOPS = 3
REVERSE_PART_OF = 0.4
EXACT_POINTS = 1.0
REQUIRED_WEIGHT = 2.0
PREFERRED_WEIGHT = 1.0
NEIGHBOUR_MIN = 0.4
NEIGHBOUR_MAX = 0.7
JD_MATCH_LABEL = "JD Match Score"

MatchKind = Literal["exact", "alias", "neighbour", "missing", "unknown"]
Priority = Literal["required", "preferred"]
AuditStatus = Literal["matched", "partial", "missing"]

RESOLVE = """
MATCH (s:Skill {key: $key})
RETURN s.name AS name, s.category AS category, 'exact' AS kind
UNION
MATCH (a:Alias {key: $key})-[:ALIAS_OF]->(s:Skill)
RETURN s.name AS name, s.category AS category, 'alias' AS kind
""".strip()

EDGES = """
MATCH (s:Skill)-[r:PART_OF|IMPLIES|RELATED_TO]->(t:Skill)
RETURN s.name AS source, type(r) AS relation, t.name AS target, r.weight AS weight
""".strip()

SKILLS = """
MATCH (s:Skill)
RETURN s.key AS key, s.name AS name, s.category AS category
""".strip()

ALL_ALIASES = """
MATCH (a:Alias)-[:ALIAS_OF]->(s:Skill)
RETURN a.key AS key, a.name AS name, s.key AS skill_key, s.name AS canonical, s.category AS category
""".strip()

ALIASES = """
MATCH (a:Alias)-[:ALIAS_OF]->(s:Skill {key: $key})
RETURN a.name AS name
ORDER BY a.name
""".strip()

_PING = "RETURN 1"


def normalize_name(value: str) -> str:
    text = value.strip().lower().replace("&", " and ")
    return " ".join(_NAME.sub(" ", text).split())


@dataclass(frozen=True)
class Resolved:
    key: str
    canonical: str
    category: str
    kind: str


@dataclass(frozen=True)
class Edge:
    source: str
    relation: str
    target: str
    weight: float


@dataclass(frozen=True)
class Hop:
    relation: str
    source: str
    target: str
    weight: float
    forward: bool


class JdSkill(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    priority: Priority


class BreakdownItem(BaseModel):
    skill: str
    canonical: str | None
    priority: Priority
    points: float
    kind: MatchKind
    reason: str


class ScoreMatch(BaseModel):
    label: str = JD_MATCH_LABEL
    score: float
    breakdown: list[BreakdownItem]


class AuditItem(BaseModel):
    skill: str
    status: AuditStatus
    reason: str


class AuditResult(BaseModel):
    items: list[AuditItem]


class CanonicalSkill(BaseModel):
    input: str
    key: str
    known: bool
    canonical: str | None
    category: str | None
    match: Literal["exact", "alias", "unknown"]
    ancestors: list[str]


class RelatedItem(BaseModel):
    skill: str
    relation: str
    weight: float


class RelatedSkills(BaseModel):
    skill: str
    known: bool
    related: list[RelatedItem]


class ExplainSkill(BaseModel):
    input: str
    known: bool
    canonical: str | None
    category: str | None
    match: Literal["exact", "alias", "unknown"]
    aliases: list[str]
    ancestors: list[str]
    relations: list[RelatedItem]


class WhatIfLearn(BaseModel):
    skill: str
    known: bool
    before: float
    after: float
    delta: float
    breakdown: list[BreakdownItem]


class SkillStore(Protocol):
    def resolve(self, text: str) -> Resolved | None: ...

    def edges(self) -> list[Edge]: ...

    def aliases(self, canonical: str) -> list[str]: ...

    def ping(self) -> None: ...


class Neo4jStore:
    def __init__(self, driver: Driver, database: str = "") -> None:
        self._driver = driver
        self._database = database or None
        self._lock = threading.Lock()
        self._loaded = False
        self._by_key: dict[str, Resolved] = {}
        self._alias_names: dict[str, list[str]] = {}
        self._edges: list[Edge] = []

    def resolve(self, text: str) -> Resolved | None:
        key = normalize_name(text)
        if not key:
            return None
        self._ensure()
        return self._by_key.get(key)

    def edges(self) -> list[Edge]:
        self._ensure()
        return list(self._edges)

    def aliases(self, canonical: str) -> list[str]:
        key = normalize_name(canonical)
        if not key:
            return []
        self._ensure()
        return list(self._alias_names.get(key, []))

    def _ensure(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            with self._driver.session(database=self._database) as session:
                skills = list(session.run(SKILLS).data())
                alias_rows = list(session.run(ALL_ALIASES).data())
                edge_rows = list(session.run(EDGES).data())
            by_key: dict[str, Resolved] = {}
            for row in skills:
                key = str(row.get("key") or "")
                if not key:
                    continue
                by_key[key] = Resolved(key, str(row["name"]), str(row["category"] or ""), "exact")
            alias_names: dict[str, list[str]] = {}
            for row in alias_rows:
                key = str(row.get("key") or "")
                skill_key = str(row.get("skill_key") or "")
                if key and key not in by_key:
                    by_key[key] = Resolved(key, str(row["canonical"]), str(row["category"] or ""), "alias")
                if skill_key:
                    alias_names.setdefault(skill_key, []).append(str(row["name"]))
            for names in alias_names.values():
                names.sort()
            edges: list[Edge] = []
            for row in edge_rows:
                weight = row.get("weight")
                if isinstance(weight, bool) or not isinstance(weight, (int, float)):
                    continue
                edges.append(Edge(str(row["source"]), str(row["relation"]), str(row["target"]), float(weight)))
            self._by_key = by_key
            self._alias_names = alias_names
            self._edges = edges
            self._loaded = True

    def ping(self) -> None:
        self._rows(_PING)

    def _rows(self, query: str, **params: object) -> list[dict]:
        with self._driver.session(database=self._database) as session:
            return list(session.run(query, **params).data())


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


def score_match(store: SkillStore, jd_skills: list[tuple[str, str]], candidate_skills: list[str]) -> ScoreMatch:
    edges = store.edges()
    graph = adjacency(edges)
    breakdown = [_score_one(store, name, priority, candidate_skills, graph) for name, priority in _unique_jd(jd_skills)]
    return ScoreMatch(label=JD_MATCH_LABEL, score=_overall(breakdown), breakdown=breakdown)


def audit_skills(store: SkillStore, jd_skills: list[tuple[str, str]], candidate_skills: list[str]) -> AuditResult:
    scored = score_match(store, jd_skills, candidate_skills)
    return AuditResult(items=[AuditItem(skill=item.skill, status=_status(item), reason=item.reason) for item in scored.breakdown])


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


def adjacency(edges: list[Edge]) -> dict[str, list[Hop]]:
    graph: dict[str, list[Hop]] = {}
    for edge in edges:
        _add(graph, Hop(edge.relation, edge.source, edge.target, edge.weight, True))
        if edge.relation == "RELATED_TO":
            _add(graph, Hop(edge.relation, edge.target, edge.source, edge.weight, True))
        elif edge.relation == "PART_OF":
            _add(graph, Hop("PART_OF", edge.target, edge.source, REVERSE_PART_OF, False))
    for hops in graph.values():
        hops.sort(key=lambda hop: (hop.target, hop.relation, hop.forward))
    return graph


def best_path(graph: dict[str, list[Hop]], source: str, target: str) -> tuple[Hop, ...] | None:
    if source == target:
        return None
    best: tuple[tuple[float, int, str], tuple[Hop, ...]] | None = None
    queue: deque[tuple[str, tuple[Hop, ...]]] = deque([(source, ())])
    while queue:
        node, path = queue.popleft()
        if len(path) >= MAX_HOPS:
            continue
        seen = {source, *(hop.target for hop in path)}
        for hop in graph.get(node, []):
            if hop.target in seen:
                continue
            new_path = path + (hop,)
            if hop.target == target:
                points = min(item.weight for item in new_path)
                signature = " ".join(f"{item.relation}:{item.target}" for item in new_path)
                rank = (-points, len(new_path), signature)
                if best is None or rank < best[0]:
                    best = (rank, new_path)
                continue
            queue.append((hop.target, new_path))
    if best is None:
        return None
    return best[1]


def path_reason(start: str, path: tuple[Hop, ...]) -> str:
    parts = [start]
    for hop in path:
        if hop.forward:
            parts.append(f"{hop.relation} {hop.target}")
        else:
            parts.append(f"is broader than {hop.target}")
    return " ".join(parts)


def ancestors(edges: list[Edge], canonical: str) -> list[str]:
    found: list[str] = []
    seen = {canonical}
    stack = [canonical]
    while stack:
        node = stack.pop()
        for edge in edges:
            if edge.source != node or edge.relation != "PART_OF" or edge.target in seen:
                continue
            seen.add(edge.target)
            found.append(edge.target)
            stack.append(edge.target)
    return sorted(found)


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
        reason = f"alias of {target.canonical}" if kind == "alias" else f"exact match on {target.canonical}"
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


def _add(graph: dict[str, list[Hop]], hop: Hop) -> None:
    graph.setdefault(hop.source, []).append(hop)
