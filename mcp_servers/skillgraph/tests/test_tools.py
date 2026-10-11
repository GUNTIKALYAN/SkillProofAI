import asyncio
from typing import Any

from neo4j.exceptions import Neo4jError
from starlette.testclient import TestClient

from skillgraph.ontology import MemoryStore, load_document
from skillgraph.scoring import (
    audit_skills,
    canonicalize,
    explain_skill,
    related_skills,
    score_match,
    what_if_learn,
)
from skillgraph.server import build_server

TOKEN = "test-skillgraph-token"
PUBLIC = "http://skillgraph:8000/mcp"
JD = [
    ("Machine Learning", "required"),
    ("Python", "required"),
    ("Docker", "preferred"),
]
CANDIDATES = ["numpy", "pandas", "fastapi"]


def _store() -> MemoryStore:
    return MemoryStore(load_document())


def test_numpy_and_pandas_resolve_under_machine_learning() -> None:
    store = _store()
    numpy = canonicalize(store, "numpy")
    pandas = canonicalize(store, "pandas")

    assert numpy.canonical == "NumPy"
    assert pandas.canonical == "pandas"
    assert "Machine Learning" in numpy.ancestors
    assert "Machine Learning" in pandas.ancestors


def test_golden_score_is_stable_and_explained() -> None:
    store = _store()
    first = score_match(store, JD, CANDIDATES)
    second = score_match(store, JD, CANDIDATES)

    assert first == second
    assert first.label == "JD Match Score"
    assert first.score == 0.52
    by_skill = {item.skill: item for item in first.breakdown}
    assert by_skill["Machine Learning"].kind == "neighbour"
    assert by_skill["Machine Learning"].points == 0.6
    assert "PART_OF Machine Learning" in by_skill["Machine Learning"].reason
    assert by_skill["Python"].kind == "neighbour"
    assert by_skill["Python"].points == 0.7
    assert "IMPLIES Python" in by_skill["Python"].reason
    assert by_skill["Docker"].kind == "missing"
    assert by_skill["Docker"].points == 0.0


def test_alias_scores_as_exact_value() -> None:
    result = score_match(_store(), [("scikit-learn", "required")], ["sklearn"])

    assert result.score == 1.0
    assert result.breakdown[0].kind == "alias"
    assert result.breakdown[0].reason == "alias of scikit-learn"


def test_audit_and_what_if_follow_the_score() -> None:
    store = _store()
    audit = audit_skills(store, JD, CANDIDATES)
    statuses = {item.skill: item.status for item in audit.items}
    learned = what_if_learn(store, "Docker", CANDIDATES, JD)

    assert statuses == {
        "Machine Learning": "partial",
        "Python": "partial",
        "Docker": "missing",
    }
    assert learned.before == 0.52
    assert learned.after == 0.72
    assert learned.delta == 0.2
    assert learned.known is True


def test_explain_and_related_skills() -> None:
    store = _store()
    explained = explain_skill(store, "numpy")
    related = related_skills(store, "FastAPI")
    names = {item.skill for item in related.related}

    assert explained.known is True
    assert explained.canonical == "NumPy"
    assert explained.match == "exact"
    assert "Machine Learning" in explained.ancestors
    assert "Python" in names
    assert "REST" in names


def test_each_tool_from_the_mcp_client() -> None:
    client = _ToolClient(build_server(_store(), TOKEN, PUBLIC, "0.0.0.0", 8000))
    jd = [
        {"name": "Machine Learning", "priority": "required"},
        {"name": "Python", "priority": "required"},
        {"name": "Docker", "priority": "preferred"},
    ]

    canonical = client.call("canonicalize_skill", {"text": "numpy"})
    score = client.call("score_match", {"jd_skills": jd, "candidate_skills": CANDIDATES})
    audit = client.call("audit_skills", {"jd_skills": jd, "candidate_skills": CANDIDATES})
    related = client.call("related_skills", {"skill": "FastAPI"})
    explained = client.call("explain_skill", {"skill": "pandas"})
    learned = client.call(
        "what_if_learn",
        {"skill": "Docker", "candidate_skills": CANDIDATES, "jd_skills": jd},
    )

    assert "Machine Learning" in canonical["ancestors"]
    assert score["label"] == "JD Match Score"
    assert score["score"] == 0.52
    assert score["breakdown"][0]["reason"]
    assert {item["status"] for item in audit["items"]} == {"partial", "missing"}
    assert related["known"] is True
    assert "Machine Learning" in explained["ancestors"]
    assert learned["delta"] == 0.2


def test_readyz_checks_the_graph_without_a_token() -> None:
    server = build_server(_store(), TOKEN, PUBLIC, "0.0.0.0", 8000)
    with TestClient(server.streamable_http_app()) as client:
        response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readyz_is_unavailable_when_neo4j_fails() -> None:
    server = build_server(_Down(), TOKEN, PUBLIC, "0.0.0.0", 8000)
    with TestClient(server.streamable_http_app()) as client:
        response = client.get("/readyz")
    assert response.status_code == 503


class _Down:
    def ping(self) -> None:
        raise Neo4jError("down")


def test_admin_alias_requires_the_token_and_a_known_skill() -> None:
    server = build_server(_AdminStore(), TOKEN, PUBLIC, "0.0.0.0", 8000)
    with TestClient(server.streamable_http_app()) as client:
        missing = client.post("/admin/alias", json={"name": "sklearn", "canonical": "Python"})
        linked = client.post(
            "/admin/alias",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"name": "sklearn", "canonical": "Python"},
        )
        missing_skill = client.post(
            "/admin/alias",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"name": "sklearn", "canonical": "Missing"},
        )
    assert missing.status_code == 401
    assert linked.status_code == 200
    assert missing_skill.status_code == 404


class _AdminStore:
    def add_skill(self, name: str) -> bool:
        return bool(name.strip())

    def add_alias(self, name: str, canonical: str) -> bool:
        del name
        return canonical == "Python"

    def ping(self) -> None:
        return None


def test_missing_bearer_token_is_rejected() -> None:
    server = build_server(_store(), TOKEN, PUBLIC, "0.0.0.0", 8000)
    with TestClient(server.streamable_http_app()) as client:
        missing = client.post("/mcp")
        wrong = client.post("/mcp", headers={"Authorization": "Bearer not-the-token"})

    assert missing.status_code == 401
    assert wrong.status_code == 401


class _ToolClient:
    def __init__(self, server: Any) -> None:
        self._server = server

    def call(self, name: str, args: dict) -> dict:
        result = asyncio.run(self._server.call_tool(name, args))
        structured = getattr(result, "structuredContent", None)
        if isinstance(structured, dict):
            return structured
        if isinstance(result, tuple) and isinstance(result[1], dict):
            return result[1]
        if isinstance(result, dict):
            return result
        raise AssertionError(f"Unexpected tool result: {type(result).__name__}")
