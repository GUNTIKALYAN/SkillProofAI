import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import jwt
import pytest
import redis
from fastapi.testclient import TestClient

from main import Settings, create_app, load_settings
from policy import ADMIN, PUBLIC, USER, match

SECRET = "test-jwt-secret-value-0123456789abcdef"
FRONTEND = Settings(
    jwt_secret=SECRET,
    redis_url="redis://localhost:6379/0",
    backend_url="http://backend:8000",
    frontend_dir=Path(__file__).resolve().parents[2] / "Frontend",
)


class FakeRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.expiry: dict[str, int] = {}

    def pipeline(self) -> "FakePipe":
        return FakePipe(self)

    def ttl(self, key: str) -> int:
        return self.expiry.get(key, -1)


class FakePipe:
    def __init__(self, store: FakeRedis) -> None:
        self.store = store
        self.ops: list[tuple] = []

    def incr(self, key: str) -> "FakePipe":
        self.ops.append(("incr", key))
        return self

    def expire(self, key: str, seconds: int, nx: bool = False) -> "FakePipe":
        self.ops.append(("expire", key, seconds, nx))
        return self

    def execute(self) -> list[int]:
        results: list[int] = []
        for op in self.ops:
            if op[0] == "incr":
                key = op[1]
                self.store.counts[key] = self.store.counts.get(key, 0) + 1
                results.append(self.store.counts[key])
            else:
                _, key, seconds, nx = op
                if not nx or key not in self.store.expiry:
                    self.store.expiry[key] = seconds
                results.append(1)
        return results


class BrokenRedis:
    def pipeline(self) -> None:
        raise redis.RedisError("unavailable")


class FakeUpstream:
    def __init__(
        self,
        status: int = 200,
        body: bytes = b"{}",
        headers: list[tuple[str, str]] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.status = status
        self.body = body
        self.headers = headers or [("content-type", "application/json")]
        self.error = error
        self.calls: list[tuple[str, str]] = []

    async def request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        self.calls.append((method, url))
        if self.error is not None:
            raise self.error
        return httpx.Response(self.status, content=self.body, headers=self.headers)


def _token(role: str = "user", sub: str = "user-1") -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": sub, "role": role, "exp": now + timedelta(minutes=15)},
        SECRET,
        algorithm="HS256",
    )


@contextmanager
def _client(
    upstream: FakeUpstream | None = None,
    store: FakeRedis | BrokenRedis | None = None,
) -> Iterator[tuple[TestClient, FakeUpstream]]:
    http = upstream or FakeUpstream()
    app = create_app(FRONTEND, store or FakeRedis(), http)
    with TestClient(app) as client:
        yield client, http


def test_policy_table() -> None:
    expected = {
        ("POST", "/api/auth/signup"): (PUBLIC, "auth"),
        ("POST", "/api/auth/login"): (PUBLIC, "auth"),
        ("POST", "/api/auth/refresh"): (PUBLIC, "auth"),
        ("POST", "/api/auth/logout"): (PUBLIC, "auth"),
        ("GET", "/api/auth/me"): (USER, None),
        ("DELETE", "/api/auth/me"): (USER, None),
        ("POST", "/api/analyses"): (USER, "analyze"),
        ("GET", "/api/analyses"): (USER, None),
        ("GET", "/api/analyses/abc"): (USER, None),
        ("PATCH", "/api/analyses/abc/plan"): (USER, None),
        ("POST", "/api/compare"): (USER, None),
        ("POST", "/api/chat"): (USER, "chat"),
        ("GET", "/api/chat"): (USER, "chat"),
        ("GET", "/api/admin/users"): (ADMIN, None),
        ("POST", "/api/admin/users/abc/block"): (ADMIN, None),
    }
    for key, (access, limit) in expected.items():
        rule = match(*key)
        assert rule is not None
        assert rule.access == access
        assert rule.limit == limit
    assert match("GET", "/api/no-such-route") is None
    assert match("POST", "/api/analyze") is None
    assert match("GET", "/api/auth/login") is None


def test_missing_or_bad_token_is_401_and_does_not_reach_the_backend() -> None:
    with _client() as (client, upstream):
        missing = client.get("/api/analyses")
        bad = client.get("/api/analyses", headers={"Authorization": "Bearer not-a-token"})
    assert missing.status_code == 401
    assert bad.status_code == 401
    assert upstream.calls == []


def test_user_on_admin_route_is_403() -> None:
    with _client() as (client, upstream):
        response = client.get(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {_token('user')}"},
        )
    assert response.status_code == 403
    assert upstream.calls == []


def test_admin_route_is_proxied_for_an_admin() -> None:
    with _client() as (client, upstream):
        response = client.get(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {_token('admin', 'admin-1')}"},
        )
    assert response.status_code == 200
    assert upstream.calls == [("GET", "http://backend:8000/api/admin/users")]


def test_unlisted_api_path_is_denied() -> None:
    with _client() as (client, upstream):
        response = client.get("/api/parse-resume")
    assert response.status_code == 404
    assert upstream.calls == []


def test_expired_token_is_401() -> None:
    expired = jwt.encode(
        {
            "sub": "user-1",
            "role": "user",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
        },
        SECRET,
        algorithm="HS256",
    )
    with _client() as (client, upstream):
        response = client.get("/api/analyses", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401
    assert upstream.calls == []


def test_auth_limit_allows_again_after_the_window() -> None:
    store = FakeRedis()
    with _client(store=store) as (client, _upstream):
        body = {"email": "a@example.com", "password": "secret"}
        for _ in range(5):
            assert client.post("/api/auth/login", json=body).status_code == 200
        assert client.post("/api/auth/login", json=body).status_code == 429
        store.counts.clear()
        store.expiry.clear()
        assert client.post("/api/auth/login", json=body).status_code == 200


def test_sixth_login_from_one_ip_is_429() -> None:
    with _client() as (client, upstream):
        for _ in range(5):
            allowed = client.post("/api/auth/login", json={"email": "a@example.com", "password": "secret"})
            assert allowed.status_code == 200
        blocked = client.post("/api/auth/login", json={"email": "b@example.com", "password": "secret"})
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1
    assert len(upstream.calls) == 5


def test_analyze_limit_is_per_user_and_chat_limit_is_twenty() -> None:
    with _client() as (client, _upstream):
        first = {"Authorization": f"Bearer {_token('user', 'user-a')}"}
        second = {"Authorization": f"Bearer {_token('user', 'user-b')}"}
        for _ in range(5):
            assert client.post("/api/analyses", headers=first, json={}).status_code == 200
        blocked = client.post("/api/analyses", headers=first, json={})
        other = client.post("/api/analyses", headers=second, json={})
        assert blocked.status_code == 429
        assert other.status_code == 200
        chat = {"Authorization": f"Bearer {_token('user', 'user-c')}"}
        for _ in range(20):
            assert client.post("/api/chat", headers=chat, json={"message": "hi"}).status_code == 200
        assert client.post("/api/chat", headers=chat, json={"message": "hi"}).status_code == 429


def test_redis_down_on_a_limited_route_is_503() -> None:
    with _client(store=BrokenRedis()) as (client, upstream):
        response = client.post("/api/auth/login", json={"email": "a@example.com", "password": "x"})
    assert response.status_code == 503
    assert upstream.calls == []


def test_body_over_5mb_is_413() -> None:
    with _client() as (client, upstream):
        response = client.post("/api/auth/login", content=b"x" * (5 * 1024 * 1024 + 1))
    assert response.status_code == 413
    assert upstream.calls == []


def test_backend_down_is_502_and_set_cookie_is_forwarded() -> None:
    with _client(FakeUpstream(error=httpx.ConnectError("down"))) as (down, _upstream):
        failed = down.post("/api/auth/login", json={"email": "a@example.com", "password": "x"})
    assert failed.status_code == 502

    headers = [("set-cookie", "refresh_token=abc; HttpOnly"), ("content-type", "application/json")]
    with _client(FakeUpstream(headers=headers)) as (client, proxied):
        response = client.post("/api/auth/login", json={"email": "a@example.com", "password": "x"})
    assert response.status_code == 200
    assert "refresh_token=abc" in response.headers["set-cookie"]
    assert proxied.calls


def test_log_line_has_request_id_and_not_the_token_or_query(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    token = _token("admin", "admin-9")
    with _client() as (client, _upstream):
        response = client.get(
            "/api/admin/users?q=secret-query",
            headers={"Authorization": f"Bearer {token}", "X-Request-ID": "req-123"},
        )
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-123"
    logged = "\n".join(record.getMessage() for record in caplog.records if record.name == "main")
    assert '"request_id": "req-123"' in logged
    assert '"user_id": "admin-9"' in logged
    assert token not in logged
    assert "secret-query" not in logged


def test_pages_and_health_are_public() -> None:
    with _client() as (client, upstream):
        assert client.get("/healthz").status_code == 200
        home = client.get("/")
        assert home.status_code == 200
        assert "Log in" in home.text
        assert "Sign up" in home.text
        assert client.get("/css/tokens.css").status_code == 200
        assert client.get("/js/api.js").status_code == 200
        assert client.get("/missing.html").status_code == 404
    assert upstream.calls == []


def test_missing_settings_fail_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("JWT_SECRET", "REDIS_URL", "BACKEND_URL"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RuntimeError, match="Startup failed"):
        load_settings()
