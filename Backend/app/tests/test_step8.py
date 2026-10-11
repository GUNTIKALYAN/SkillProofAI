import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.conftest import TEST_PASSWORD, register
from app.db.models import Analysis, AuditLog, ChatMessage, ChatSession, User
from app.db.session import session_scope
from app.main import app
from app.services.metrics import observe_llm

ROOT = Path(__file__).resolve().parents[3]
FRONTEND = ROOT / "Frontend"


def _service_block(text: str, name: str) -> str:
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line == f"  {name}:":
            start = index + 1
            break
    assert start is not None, name
    block: list[str] = []
    for line in lines[start:]:
        if line.startswith("  ") and not line.startswith("   ") and line.endswith(":"):
            break
        block.append(line)
    return "\n".join(block)


def test_metrics_reports_request_latency_queue_depth_and_llm_latency() -> None:
    observe_llm(25)
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "skillproof_http_requests_total 1" in body
    assert "skillproof_llm_requests_total 1" in body
    assert "skillproof_llm_latency_ms_sum 25" in body
    assert "skillproof_queue_depth 0" in body
    assert "skillproof_http_latency_ms_sum " in body


def test_delete_my_data_removes_the_account(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.analysis_service.enqueue_analysis", lambda _analysis_id: None)
    with TestClient(app) as client:
        owner = {"Authorization": f"Bearer {register(client, 'gone@example.com')}"}
        other = register(client, "stay@example.com")
        created = client.post(
            "/api/analyses",
            headers=owner,
            data={"jd_text": "Requirements\nPython\nFastAPI\n", "github_username": "octocat"},
            files={
                "resume": (
                    "resume.docx",
                    _docx(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
        assert created.status_code == 202, created.text
        job_id = uuid.UUID(created.json()["job_id"])
        with session_scope() as session:
            user = session.scalar(select(User).where(User.email == "gone@example.com"))
            assert user is not None
            chat = ChatSession(user_id=user.id, analysis_id=job_id)
            session.add(chat)
            session.flush()
            session.add(ChatMessage(session_id=chat.id, role="user", content="What should I learn?"))
            session.add(AuditLog(user_id=user.id, action="rate_limit", target="analyze"))
        denied = client.delete("/api/auth/me")
        assert denied.status_code == 401
        removed = client.delete("/api/auth/me", headers=owner)
        assert removed.status_code == 204
        assert client.get("/api/auth/me", headers=owner).status_code == 401
        login = client.post(
            "/api/auth/login",
            json={"email": "gone@example.com", "password": TEST_PASSWORD},
        )
        assert login.status_code == 401
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {other}"}).status_code == 200
    with session_scope() as session:
        assert session.scalar(select(User).where(User.email == "gone@example.com")) is None
        assert session.scalar(select(func.count()).select_from(Analysis)) == 0
        assert session.scalar(select(func.count()).select_from(ChatMessage)) == 0
        log = session.scalar(select(AuditLog).where(AuditLog.action == "rate_limit"))
        assert log is not None
        assert log.user_id is None


def test_delete_control_is_on_each_signed_in_page() -> None:
    for name in ("app.html", "history.html", "chat.html", "compare.html", "admin.html"):
        assert "data-delete-account" in (FRONTEND / name).read_text(encoding="utf-8")
    guard = (FRONTEND / "js" / "guard.js").read_text(encoding="utf-8")
    assert 'api("/api/auth/me", { method: "DELETE" })' in guard


def test_containers_drop_root_and_mcp_is_not_published() -> None:
    dockerfiles = [
        ROOT / "Backend" / "Dockerfile",
        ROOT / "mcp_servers" / "skillgraph" / "Dockerfile",
        ROOT / "mcp_servers" / "tavily" / "Dockerfile",
        ROOT / "mcp_servers" / "verify" / "Dockerfile",
        ROOT / "mcp_servers" / "github" / "Dockerfile",
    ]
    for path in dockerfiles:
        text = path.read_text(encoding="utf-8")
        assert ".env" not in text
        assert "USER app" in text
    frontend = (ROOT / "Frontend" / "Dockerfile").read_text(encoding="utf-8")
    assert "nginx-unprivileged" in frontend
    assert ".env" not in frontend
    assert "listen 8080;" in (ROOT / "Frontend" / "nginx.conf").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "internal: true" in compose
    assert "3000:8080" in compose
    for name in ("skillgraph", "mcp-github", "mcp-tavily", "mcp-verify"):
        block = _service_block(compose, name)
        assert "ports:" not in block
        assert "- mcp" in block


def _docx() -> bytes:
    from io import BytesIO

    from docx import Document

    document = Document()
    document.add_paragraph("Python and FastAPI")
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()
