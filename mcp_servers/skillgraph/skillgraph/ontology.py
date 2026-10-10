import json
import re
from dataclasses import dataclass
from pathlib import Path

_NAME = re.compile(r"[^a-z0-9+#]+")
_MIN_WEIGHT = 0.4
_MAX_WEIGHT = 0.7
_RELATIONS = {
    "part_of": "PART_OF",
    "implies": "IMPLIES",
    "related_to": "RELATED_TO",
}


def default_data_path() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "skills.json"


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
class SkillRecord:
    key: str
    name: str
    category: str


@dataclass(frozen=True)
class AliasRecord:
    key: str
    name: str
    skill_key: str


@dataclass(frozen=True)
class EdgeRecord:
    relation: str
    source_key: str
    source_name: str
    target_key: str
    target_name: str
    weight: float


@dataclass(frozen=True)
class Document:
    skills: tuple[SkillRecord, ...]
    aliases: tuple[AliasRecord, ...]
    edges: tuple[EdgeRecord, ...]


class MemoryStore:
    def __init__(self, document: Document) -> None:
        self._skills = {skill.key: skill for skill in document.skills}
        self._aliases = {alias.key: alias for alias in document.aliases}
        self._alias_names: dict[str, list[str]] = {}
        for alias in document.aliases:
            self._alias_names.setdefault(alias.skill_key, []).append(alias.name)
        for names in self._alias_names.values():
            names.sort()
        self._edges = [
            Edge(edge.source_name, edge.relation, edge.target_name, edge.weight)
            for edge in document.edges
        ]

    def resolve(self, text: str) -> Resolved | None:
        key = normalize_name(text)
        if not key:
            return None
        skill = self._skills.get(key)
        if skill is not None:
            return Resolved(key, skill.name, skill.category, "exact")
        alias = self._aliases.get(key)
        if alias is None:
            return None
        target = self._skills[alias.skill_key]
        return Resolved(key, target.name, target.category, "alias")

    def edges(self) -> list[Edge]:
        return list(self._edges)

    def aliases(self, canonical: str) -> list[str]:
        skill = self._skills.get(normalize_name(canonical))
        if skill is None:
            return []
        return list(self._alias_names.get(skill.key, []))


def load_document(path: Path | None = None) -> Document:
    source = path or default_data_path()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Skill ontology file not found: {source}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("Skill ontology file is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise TypeError("Skill ontology file must be a JSON object")
    return _document(payload)


def _document(payload: dict) -> Document:
    skills = _skills(payload.get("skills"))
    by_name = {skill.name: skill for skill in skills}
    aliases = _aliases(payload.get("aliases"), by_name, {skill.key for skill in skills})
    edges: list[EdgeRecord] = []
    for field, relation in _RELATIONS.items():
        edges.extend(_edges(payload.get(field), relation, by_name))
    return Document(tuple(skills), tuple(aliases), tuple(edges))


def _skills(raw: object) -> list[SkillRecord]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("Skill ontology needs a non-empty skills list")
    skills: list[SkillRecord] = []
    seen: set[str] = set()
    for item in raw:
        name = _text(item, "name")
        category = _text(item, "category")
        key = normalize_name(name)
        if not key:
            raise ValueError("Skill name is empty")
        if key in seen:
            raise ValueError(f"Duplicate skill: {name}")
        seen.add(key)
        skills.append(SkillRecord(key, name, category))
    return skills


def _aliases(
    raw: object,
    skills: dict[str, SkillRecord],
    skill_keys: set[str],
) -> list[AliasRecord]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise TypeError("aliases must be a list")
    aliases: list[AliasRecord] = []
    seen: set[str] = set()
    for item in raw:
        name = _text(item, "name")
        skill_name = _text(item, "skill")
        key = normalize_name(name)
        skill = skills.get(skill_name)
        if skill is None:
            raise ValueError(f"Alias points at an unknown skill: {skill_name}")
        if key == skill.key:
            continue
        if not key or key in skill_keys or key in seen:
            raise ValueError(f"Alias collides with another name: {name}")
        seen.add(key)
        aliases.append(AliasRecord(key, name, skill.key))
    return aliases


def _edges(raw: object, relation: str, skills: dict[str, SkillRecord]) -> list[EdgeRecord]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise TypeError(f"{relation} must be a list")
    edges: list[EdgeRecord] = []
    seen: set[tuple[str, str]] = set()
    for item in raw:
        source_name = _text(item, "source")
        target_name = _text(item, "target")
        source = skills.get(source_name)
        target = skills.get(target_name)
        if source is None or target is None:
            raise ValueError(f"{relation} endpoint is not a skill")
        if source.key == target.key or (source.key, target.key) in seen:
            raise ValueError(f"Duplicate {relation} edge")
        weight = _weight(item)
        seen.add((source.key, target.key))
        edges.append(
            EdgeRecord(relation, source.key, source.name, target.key, target.name, weight)
        )
    return edges


def _text(item: object, field: str) -> str:
    if not isinstance(item, dict):
        raise TypeError("Ontology entries must be objects")
    value = item.get(field)
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 80:
        raise ValueError(f"Invalid ontology field: {field}")
    return value.strip()


def _weight(item: object) -> float:
    if not isinstance(item, dict):
        raise TypeError("Ontology entries must be objects")
    value = item.get("weight")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("Edge weight must be a number")
    weight = float(value)
    if weight < _MIN_WEIGHT or weight > _MAX_WEIGHT:
        raise ValueError("Edge weight must be between 0.4 and 0.7")
    return weight
