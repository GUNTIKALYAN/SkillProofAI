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

ALIASES = """
MATCH (a:Alias)-[:ALIAS_OF]->(s:Skill {key: $key})
RETURN a.name AS name
ORDER BY a.name
""".strip()

SKILL_CONSTRAINT = (
    "CREATE CONSTRAINT skill_key IF NOT EXISTS FOR (s:Skill) REQUIRE s.key IS UNIQUE"
)
ALIAS_CONSTRAINT = (
    "CREATE CONSTRAINT alias_key IF NOT EXISTS FOR (a:Alias) REQUIRE a.key IS UNIQUE"
)

MERGE_SKILL = """
MERGE (s:Skill {key: $key})
SET s.name = $name, s.category = $category
""".strip()

MERGE_ALIAS = """
MERGE (a:Alias {key: $key})
SET a.name = $name
WITH a
MATCH (s:Skill {key: $skill_key})
MERGE (a)-[:ALIAS_OF]->(s)
""".strip()

MERGE_PART_OF = """
MATCH (s:Skill {key: $source})
MATCH (t:Skill {key: $target})
MERGE (s)-[r:PART_OF]->(t)
SET r.weight = $weight
""".strip()

MERGE_IMPLIES = """
MATCH (s:Skill {key: $source})
MATCH (t:Skill {key: $target})
MERGE (s)-[r:IMPLIES]->(t)
SET r.weight = $weight
""".strip()

MERGE_RELATED = """
MATCH (s:Skill {key: $source})
MATCH (t:Skill {key: $target})
MERGE (s)-[r:RELATED_TO]->(t)
SET r.weight = $weight
""".strip()

_MERGE = {
    "PART_OF": MERGE_PART_OF,
    "IMPLIES": MERGE_IMPLIES,
    "RELATED_TO": MERGE_RELATED,
}


def merge_edge(relation: str) -> str:
    try:
        return _MERGE[relation]
    except KeyError as exc:
        raise ValueError(f"Unknown relation: {relation}") from exc
