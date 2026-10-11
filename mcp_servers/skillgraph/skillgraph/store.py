from neo4j import Driver

from skillgraph.cypher import ALIASES, EDGES, MERGE_ALIAS, MERGE_SKILL, RESOLVE
from skillgraph.ontology import Edge, Resolved, normalize_name

_PING = "RETURN 1"


class Neo4jStore:
    def __init__(self, driver: Driver) -> None:
        self._driver = driver

    def resolve(self, text: str) -> Resolved | None:
        key = normalize_name(text)
        if not key:
            return None
        rows = self._rows(RESOLVE, key=key)
        if not rows:
            return None
        rows.sort(key=lambda row: 0 if row.get("kind") == "exact" else 1)
        row = rows[0]
        return Resolved(key, str(row["name"]), str(row["category"]), str(row["kind"]))

    def edges(self) -> list[Edge]:
        edges: list[Edge] = []
        for row in self._rows(EDGES):
            weight = row.get("weight")
            if isinstance(weight, bool) or not isinstance(weight, (int, float)):
                continue
            edges.append(
                Edge(str(row["source"]), str(row["relation"]), str(row["target"]), float(weight))
            )
        return edges

    def aliases(self, canonical: str) -> list[str]:
        key = normalize_name(canonical)
        if not key:
            return []
        return [str(row["name"]) for row in self._rows(ALIASES, key=key)]

    def ping(self) -> None:
        self._rows(_PING)

    def add_skill(self, name: str) -> bool:
        key = normalize_name(name)
        if not key:
            return False
        self._rows(MERGE_SKILL, key=key, name=name.strip(), category="Reviewed")
        return True

    def add_alias(self, name: str, canonical: str) -> bool:
        if self.resolve(canonical) is None:
            return False
        key = normalize_name(name)
        skill_key = normalize_name(canonical)
        if not key or not skill_key or key == skill_key:
            return False
        self._rows(MERGE_ALIAS, key=key, name=name.strip(), skill_key=skill_key)
        return True

    def _rows(self, query: str, **params: object) -> list[dict]:
        with self._driver.session() as session:
            return list(session.run(query, **params).data())
