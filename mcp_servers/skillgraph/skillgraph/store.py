from neo4j import Driver

from skillgraph.cypher import ALIASES, EDGES, RESOLVE
from skillgraph.ontology import Edge, Resolved, normalize_name


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

    def _rows(self, query: str, **params: object) -> list[dict]:
        with self._driver.session() as session:
            return list(session.run(query, **params).data())
