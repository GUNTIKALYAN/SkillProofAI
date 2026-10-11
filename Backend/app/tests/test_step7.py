import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.conftest import register
from app.db.models import (
    AgentRun,
    AgentStep,
    Analysis,
    ChatMessage,
    ChatSession,
    UnknownSkill,
)
from app.db.session import session_scope
from app.main import app
from app.services.admin_seed import seed_admin
from app.services.bucket import MemoryBucket
from app.services.cache import MemoryCache
from app.services.tool_session import Clients

FRONTEND = Path(__file__).resolve().parents[3] / "Frontend"
ADMIN_GETS = (
    "/api/admin/overview",
    "/api/admin/users",
    "/api/admin/traces",
    "/api/admin/rate-limits",
    "/api/admin/unknown-skills",
    "/api/admin/audit",
    "/api/admin/agents",
)


class Tools:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def call(self, server: str, tool: str, args: dict) -> dict:
        self.calls.append((server, tool))
        if tool == "what_if_learn":
            return {"skill": "Docker", "known": True, "before": 0.4, "after": 0.7, "delta": 0.3}
        if tool == "explain_skill":
            return {"known": True, "canonical": args["skill"]}
        if tool == "score_match":
            names = [item["name"] for item in args["jd_skills"]]
            breakdown = [
                {"skill": name, "canonical": name, "points": 1.0 if name == "Python" else 0.0}
                for name in names
            ]
            score = sum(item["points"] for item in breakdown) / len(breakdown)
            return {"label": "JD Match Score", "score": score, "breakdown": breakdown}
        raise AssertionError(tool)


def _clients(llm) -> Clients:
    return Clients(transport=Tools(), bucket=MemoryBucket(), cache=MemoryCache(), llm=llm)


def _llm_cited(system: str, user: str) -> tuple[dict, int]:
    del system
    data = json.loads(user.split("\n\nValidation error:", 1)[0])
    if data.get("tool_results"):
        return {"answer": "Python is an exact match.", "citations": ["exact match on Python"], "tool": None}, 4
    return {
        "answer": "Looking it up.",
        "citations": [],
        "tool": {"name": "explain_skill", "skill": "Python"},
    }, 2


def _llm_uncited(system: str, user: str) -> tuple[dict, int]:
    del system, user
    return {"answer": "You should become a chef.", "citations": ["cooking"], "tool": None}, 1


def _llm_jobs(system: str, user: str) -> tuple[dict, int]:
    del system
    data = json.loads(user.split("\n\nValidation error:", 1)[0])
    skills = [
        {"name": line.strip(), "priority": "required"}
        for line in data["job_description"].splitlines()
        if line.strip() and line.strip().lower() != "requirements"
    ]
    return {"resume_skills": ["Python"], "jd_skills": skills}, 1


def _headers(client: TestClient, email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {register(client, email)}"}


def _save_analysis(user_id: str) -> None:
    with session_scope() as session:
        session.add(
            Analysis(
                user_id=uuid.UUID(user_id),
                jd_text="Requirements\nPython\nDocker\n",
                jd_hash="abc",
                resume_json={"text": ["Python"]},
                score=0.4,
                status="completed",
                result_json={
                    "jd_match_score": {"label": "JD Match Score", "score": 0.4, "breakdown": []},
                    "audit": [{"skill": "Python", "status": "matched", "reason": "exact match on Python"}],
                    "resume_skills": ["Python"],
                    "jd_skills": [
                        {"name": "Python", "priority": "required"},
                        {"name": "Docker", "priority": "preferred"},
                    ],
                    "action_plan": {"items": [{"skill": "Docker", "steps": ["Practice it."], "resources": []}]},
                },
            )
        )


def test_what_if_streams_the_new_score(monkeypatch: pytest.MonkeyPatch) -> None:
    tools = Tools()
    monkeypatch.setattr(
        "app.services.chat.default_clients",
        lambda: Clients(transport=tools, bucket=MemoryBucket(), cache=MemoryCache(), llm=_llm_cited),
    )
    with TestClient(app) as client:
        headers = _headers(client, "chat@example.com")
        user_id = client.get("/api/auth/me", headers=headers).json()["id"]
        _save_analysis(user_id)
        response = client.post("/api/chat", headers=headers, json={"message": "What if I learn Docker?"})
    assert response.status_code == 200, response.text
    assert "40%" in response.text
    assert "70%" in response.text
    assert ("skillgraph", "what_if_learn") in tools.calls


def test_chat_without_evidence_says_it_does_not_know(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.chat.default_clients", lambda: _clients(_llm_uncited))
    with TestClient(app) as client:
        headers = _headers(client, "plain@example.com")
        user_id = client.get("/api/auth/me", headers=headers).json()["id"]
        _save_analysis(user_id)
        response = client.post("/api/chat", headers=headers, json={"message": "What should I cook tonight?"})
    assert response.status_code == 200, response.text
    assert "I don't know based on the saved analysis." in response.text


def test_cited_answer_can_use_a_graph_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    tools = Tools()
    monkeypatch.setattr(
        "app.services.chat.default_clients",
        lambda: Clients(transport=tools, bucket=MemoryBucket(), cache=MemoryCache(), llm=_llm_cited),
    )
    with TestClient(app) as client:
        headers = _headers(client, "cite@example.com")
        user_id = client.get("/api/auth/me", headers=headers).json()["id"]
        _save_analysis(user_id)
        response = client.post("/api/chat", headers=headers, json={"message": "How does Python look?"})
    assert response.status_code == 200, response.text
    assert "exact match" in response.text
    assert ("skillgraph", "explain_skill") in tools.calls


def test_chat_limits_reject_long_messages_and_token_budget() -> None:
    with TestClient(app) as client:
        headers = _headers(client, "limit@example.com")
        user_id = client.get("/api/auth/me", headers=headers).json()["id"]
        long = client.post("/api/chat", headers=headers, json={"message": "x" * 2001})
        assert long.status_code == 422
        with session_scope() as session:
            thread = ChatSession(user_id=uuid.UUID(user_id))
            session.add(thread)
            session.flush()
            session.add(
                ChatMessage(
                    session_id=thread.id,
                    role="assistant",
                    content="earlier",
                    tokens=get_settings().chat_daily_tokens,
                )
            )
        blocked = client.post("/api/chat", headers=headers, json={"message": "Another question"})
    assert blocked.status_code == 429


def test_compare_ranks_jobs_and_names_the_unlock_skill(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.compare.default_clients", lambda: _clients(_llm_jobs))
    with TestClient(app) as client:
        headers = _headers(client, "jobs@example.com")
        user_id = client.get("/api/auth/me", headers=headers).json()["id"]
        _save_analysis(user_id)
        response = client.post(
            "/api/compare",
            headers=headers,
            json={
                "job_descriptions": [
                    "Requirements\nDocker\n",
                    "Requirements\nPython\n",
                ]
            },
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ranked"][0]["score"] == 1.0
    assert body["unlock_skill"] == "Docker"
    assert body["unlock_jobs"] == 1


def test_plan_checks_stay_on_the_owners_analysis() -> None:
    with TestClient(app) as client:
        owner = _headers(client, "owner-plan@example.com")
        other = _headers(client, "other-plan@example.com")
        user_id = client.get("/api/auth/me", headers=owner).json()["id"]
        _save_analysis(user_id)
        with session_scope() as session:
            analysis_id = session.query(Analysis).one().id
        saved = client.patch(
            f"/api/analyses/{analysis_id}/plan",
            headers=owner,
            json={"skill": "Docker", "step": "Practice it.", "done": True},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["result"]["checked_steps"] == [{"skill": "Docker", "step": "Practice it."}]
        denied = client.patch(
            f"/api/analyses/{analysis_id}/plan",
            headers=other,
            json={"skill": "Docker", "step": "Practice it.", "done": True},
        )
    assert denied.status_code == 404


def test_user_gets_403_on_every_admin_route() -> None:
    sample = "00000000-0000-0000-0000-000000000000"
    with TestClient(app) as client:
        headers = _headers(client, "person@example.com")
        for path in ADMIN_GETS:
            assert client.get(path, headers=headers).status_code == 403
        assert client.get(f"/api/admin/traces/{sample}", headers=headers).status_code == 403
        assert client.post(f"/api/admin/users/{sample}/block", headers=headers).status_code == 403
        assert client.post(f"/api/admin/users/{sample}/unblock", headers=headers).status_code == 403
        assert client.delete(f"/api/admin/users/{sample}", headers=headers).status_code == 403
        assert client.post(f"/api/admin/unknown-skills/{sample}/approve", headers=headers).status_code == 403
        denied = client.post(
            f"/api/admin/unknown-skills/{sample}/alias",
            headers=headers,
            json={"canonical": "Python"},
        )
        assert denied.status_code == 403
        merged = client.post(
            f"/api/admin/unknown-skills/{sample}/merge",
            headers=headers,
            json={"canonical": "Python"},
        )
        assert merged.status_code == 403


def test_admin_can_open_a_users_trace_and_cannot_block_an_admin() -> None:
    with TestClient(app) as client:
        headers = _headers(client, "traced@example.com")
        user_id = client.get("/api/auth/me", headers=headers).json()["id"]
        _save_analysis(user_id)
        with session_scope() as session:
            analysis = session.query(Analysis).one()
            run = AgentRun(analysis_id=analysis.id, skill_hash="abc", status="completed")
            session.add(run)
            session.flush()
            session.add(AgentStep(run_id=run.id, node="supervisor", attempt=1, input_hash="abc", tokens=3, latency_ms=12))
            run_id = run.id
            seed_admin(session, "admin@example.com", "admin-password-1")
            seed_admin(session, "other-admin@example.com", "admin-password-1")
        logged_in = client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "admin-password-1"},
        )
        admin = {"Authorization": f"Bearer {logged_in.json()['access_token']}"}
        listing = client.get("/api/admin/traces", headers=admin)
        assert listing.status_code == 200
        assert any(row["email"] == "traced@example.com" for row in listing.json())
        detail = client.get(f"/api/admin/traces/{run_id}", headers=admin)
        assert detail.status_code == 200, detail.text
        assert detail.json()["steps"][0]["node"] == "supervisor"
        other = client.get("/api/admin/users?q=other-admin", headers=admin).json()
        blocked = client.post(f"/api/admin/users/{other[0]['id']}/block", headers=admin)
        assert blocked.status_code == 403
        person = client.get("/api/admin/users?q=traced@", headers=admin).json()
        assert client.post(f"/api/admin/users/{person[0]['id']}/block", headers=admin).status_code == 200


def test_admin_alias_updates_the_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.skill_review.add_alias", lambda name, canonical: True)
    with TestClient(app) as client:
        with session_scope() as session:
            skill = UnknownSkill(name="frobnicator")
            session.add(skill)
            session.flush()
            skill_id = skill.id
            seed_admin(session, "admin@example.com", "admin-password-1")
        logged_in = client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "admin-password-1"},
        )
        headers = {"Authorization": f"Bearer {logged_in.json()['access_token']}"}
        saved = client.post(
            f"/api/admin/unknown-skills/{skill_id}/alias",
            headers=headers,
            json={"canonical": "Python"},
        )
    assert saved.status_code == 200, saved.text
    assert saved.json()["status"] == "aliased"
    assert saved.json()["alias_of"] == "Python"


def test_user_pages_hide_the_admin_link() -> None:
    for name in ("app.html", "history.html", "chat.html", "compare.html"):
        text = (FRONTEND / name).read_text(encoding="utf-8")
        assert 'href="admin.html" data-admin hidden' in text
    assert "admin.html" not in (FRONTEND / "login.html").read_text(encoding="utf-8")
    assert "admin.html" not in (FRONTEND / "signup.html").read_text(encoding="utf-8")
    assert 'user.role !== "admin"' in (FRONTEND / "js" / "admin.js").read_text(encoding="utf-8")
