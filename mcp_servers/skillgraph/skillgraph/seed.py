"""Load the curated skill ontology into Neo4j.

The JSON file is a hand-curated AI, ML and backend subset. Canonical names
follow labels used by ESCO and O*NET. Aliases include common Stack Overflow
tags such as sklearn and k8s. It is not a full taxonomy dump.
"""

from pathlib import Path
from typing import Protocol

from skillgraph.cypher import (
    ALIAS_CONSTRAINT,
    MERGE_ALIAS,
    MERGE_SKILL,
    SKILL_CONSTRAINT,
    merge_edge,
)
from skillgraph.ontology import Document, load_document


class CypherSession(Protocol):
    def run(self, query: str, **params: object) -> object: ...


def seed(session: CypherSession, path: Path | None = None) -> int:
    document = load_document(path)
    _write(session, document)
    return len(document.skills)


def write_document(session: CypherSession, document: Document) -> None:
    _write(session, document)


def _write(session: CypherSession, document: Document) -> None:
    session.run(SKILL_CONSTRAINT)
    session.run(ALIAS_CONSTRAINT)
    for skill in document.skills:
        session.run(MERGE_SKILL, key=skill.key, name=skill.name, category=skill.category)
    for alias in document.aliases:
        session.run(MERGE_ALIAS, key=alias.key, name=alias.name, skill_key=alias.skill_key)
    for edge in document.edges:
        session.run(
            merge_edge(edge.relation),
            source=edge.source_key,
            target=edge.target_key,
            weight=edge.weight,
        )
