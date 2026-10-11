import threading
import uuid
from io import BytesIO

from docx import Document
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.conftest import register
from app.db.models import AuditLog
from app.db.session import session_scope
from app.main import app
from app.services import ready
from app.services.bucket import BUCKET_LIMITS, RedisBucket
from app.services.rate_limit import MemoryLimiter

DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_auth_limit_is_per_email_and_writes_an_audit_row() -> None:
    body = {"email": "person@example.com", "password": "not-the-password"}
    with TestClient(app) as client:
        for _ in range(5):
            denied = client.post("/api/auth/login", json=body)
            assert denied.status_code == 401
        blocked = client.post("/api/auth/login", json=body)
        other = client.post(
            "/api/auth/login",
            json={"email": "other@example.com", "password": "not-the-password"},
        )
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1
    assert other.status_code == 401
    with session_scope() as session:
        rows = session.scalars(select(AuditLog).where(AuditLog.action == "rate_limit")).all()
    assert len(rows) == 1
    assert rows[0].target == "auth"
    assert rows[0].user_id is None


def test_analyze_limit_is_per_user(monkeypatch) -> None:
    monkeypatch.setattr("app.services.analysis_service.enqueue_analysis", lambda _analysis_id: None)
    payload = _docx()
    with TestClient(app) as client:
        token = register(client)
        headers = {"Authorization": f"Bearer {token}"}
        for _ in range(5):
            allowed = _analyze(client, headers, payload)
            assert allowed.status_code == 202
        blocked = _analyze(client, headers, payload)
        other = register(client, "second@example.com")
        still_open = _analyze(client, {"Authorization": f"Bearer {other}"}, payload)
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1
    assert still_open.status_code == 202


def test_two_limiters_share_one_window() -> None:
    hits: dict[str, list[float]] = {}
    lock = threading.Lock()
    first = MemoryLimiter(hits, lock)
    second = MemoryLimiter(hits, lock)
    for _ in range(5):
        assert first.take("auth", "10.0.0.1:a@example.com", now=1000) is None
    assert second.take("auth", "10.0.0.1:a@example.com", now=1000) is not None


def test_chat_limit_is_twenty_per_minute() -> None:
    limiter = MemoryLimiter()
    identity = str(uuid.uuid4())
    for _ in range(20):
        assert limiter.take("chat", identity, now=1000) is None
    assert limiter.take("chat", identity, now=1000) is not None


def test_shared_window_stays_exact_under_threads() -> None:
    limiter = MemoryLimiter()
    results: list[int | None] = []
    lock = threading.Lock()

    def once() -> None:
        retry = limiter.take("chat", "same-user", now=1000)
        with lock:
            results.append(retry)

    threads = [threading.Thread(target=once) for _ in range(25)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sum(item is None for item in results) == 20
    assert sum(item is not None for item in results) == 5


def test_mcp_bucket_is_shared_across_callers() -> None:
    counter = _Counter()
    first = RedisBucket("redis://unused", client=counter)
    second = RedisBucket("redis://unused", client=counter)
    limit = BUCKET_LIMITS["github"]
    for _ in range(limit):
        assert first.take("github") is True
    assert second.take("github") is False


def test_readyz_reports_each_dependency(monkeypatch) -> None:
    monkeypatch.setattr(ready, "postgres_ok", lambda: True)
    monkeypatch.setattr(ready, "redis_ok", lambda: True)
    monkeypatch.setattr(ready, "neo4j_ok", lambda: True)
    with TestClient(app) as client:
        ready_response = client.get("/readyz")
        monkeypatch.setattr(ready, "redis_ok", lambda: False)
        down = client.get("/readyz")
    assert ready_response.status_code == 200
    assert ready_response.json()["checks"] == {"postgres": True, "redis": True, "neo4j": True}
    assert down.status_code == 503
    assert down.json()["checks"]["redis"] is False


def _analyze(client: TestClient, headers: dict[str, str], payload: bytes):
    return client.post(
        "/api/analyses",
        headers=headers,
        data={"jd_text": "Python developer role", "github_username": "octocat"},
        files={"resume": ("resume.docx", payload, DOCX_TYPE)},
    )


def _docx() -> bytes:
    document = Document()
    document.add_paragraph("Python")
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


class _Counter:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}

    def incr(self, key: str) -> int:
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    def expire(self, key: str, seconds: int) -> bool:
        del key, seconds
        return True
