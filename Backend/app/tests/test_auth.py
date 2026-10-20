import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.conftest import TEST_PASSWORD, register
from app.db import (
    STATUS_BLOCKED,
    AgentRun,
    AgentStep,
    Analysis,
    ChatMessage,
    ChatSession,
    User,
    session_scope,
)
from app.main import app
from app.security import ACCESS_ALGORITHM
from app.services.admin_seed import seed_admin


def test_signup_login_and_me() -> None:
    with TestClient(app) as client:
        token = register(client, "person@example.com")
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["email"] == "person@example.com"
        assert me.json()["role"] == "user"

        logged_in = client.post(
            "/api/auth/login",
            json={"email": "person@example.com", "password": TEST_PASSWORD},
        )
        assert logged_in.status_code == 200
        again = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {logged_in.json()['access_token']}"},
        )
        assert again.status_code == 200


def test_wrong_password_is_rejected() -> None:
    with TestClient(app) as client:
        register(client, "person@example.com")
        response = client.post(
            "/api/auth/login",
            json={"email": "person@example.com", "password": "not-the-password"},
        )
    assert response.status_code == 401


def test_user_cannot_call_admin_route() -> None:
    with TestClient(app) as client:
        token = register(client, "person@example.com")
        response = client.get(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 403


def test_admin_can_list_users() -> None:
    with TestClient(app) as client:
        with session_scope() as session:
            seed_admin(session, "admin@example.com", "admin-password-1")
        logged_in = client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "admin-password-1"},
        )
        assert logged_in.status_code == 200
        response = client.get(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {logged_in.json()['access_token']}"},
        )
    assert response.status_code == 200
    assert any(row["role"] == "admin" for row in response.json())


def test_signup_cannot_create_an_admin() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/auth/signup",
            json={
                "email": "sneaky@example.com",
                "password": TEST_PASSWORD,
                "role": "admin",
            },
        )
        assert response.status_code == 201
        me = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {response.json()['access_token']}"},
        )
    assert me.json()["role"] == "user"


def test_user_cannot_read_another_users_analysis() -> None:
    with TestClient(app) as client:
        token_a = register(client, "a@example.com")
        token_b = register(client, "b@example.com")
        owner_id = uuid.UUID(
            client.get(
                "/api/auth/me",
                headers={"Authorization": f"Bearer {token_b}"},
            ).json()["id"]
        )
        analysis_id = uuid.uuid4()
        with session_scope() as session:
            session.add(
                Analysis(
                    id=analysis_id,
                    user_id=owner_id,
                    jd_text="Requirements\npython\n",
                    jd_hash="abc123",
                    status="complete",
                )
            )
        denied = client.get(
            f"/api/analyses/{analysis_id}",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        allowed = client.get(
            f"/api/analyses/{analysis_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
    assert denied.status_code == 404
    assert allowed.status_code == 200
    assert allowed.json()["id"] == str(analysis_id)


def test_expired_access_token_is_rejected() -> None:
    with TestClient(app) as client:
        token = register(client)
        user_id = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        ).json()["id"]
        expired = jwt.encode(
            {
                "sub": user_id,
                "role": "user",
                "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
            },
            get_settings().jwt_secret,
            algorithm=ACCESS_ALGORITHM,
        )
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {expired}"},
        )
    assert response.status_code == 401


def test_reused_refresh_token_is_rejected() -> None:
    with TestClient(app) as client:
        register(client, "person@example.com")
        first = client.cookies.get("refresh_token")
        assert first
        rotated = client.post("/api/auth/refresh")
        assert rotated.status_code == 200
        client.cookies.set("refresh_token", first)
        reused = client.post("/api/auth/refresh")
    assert reused.status_code == 401


def test_duplicate_email_is_rejected() -> None:
    with TestClient(app) as client:
        register(client, "person@example.com")
        again = client.post(
            "/api/auth/signup",
            json={"email": "person@example.com", "password": TEST_PASSWORD},
        )
    assert again.status_code == 409


def test_blocked_user_cannot_login_or_refresh() -> None:
    with TestClient(app) as client:
        register(client, "person@example.com")
        with session_scope() as session:
            user = session.scalar(select(User).where(User.email == "person@example.com"))
            assert user is not None
            user.status = STATUS_BLOCKED
        login = client.post(
            "/api/auth/login",
            json={"email": "person@example.com", "password": TEST_PASSWORD},
        )
        refresh = client.post("/api/auth/refresh")
    assert login.status_code == 401
    assert refresh.status_code == 401


def test_delete_my_data_removes_the_account() -> None:
    with TestClient(app) as client:
        owner = {"Authorization": f"Bearer {register(client, 'gone@example.com')}"}
        other = register(client, "stay@example.com")
        user_id = client.get("/api/auth/me", headers=owner).json()["id"]
        with session_scope() as session:
            chat = ChatSession(user_id=uuid.UUID(user_id))
            session.add(chat)
            session.flush()
            session.add(ChatMessage(session_id=chat.id, role="user", content="What should I learn?"))
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
        assert session.scalar(select(ChatMessage).limit(1)) is None


def test_user_gets_404_on_another_users_chat_analysis() -> None:
    with TestClient(app) as client:
        token_a = register(client, "a@example.com")
        token_b = register(client, "b@example.com")
        owner_id = uuid.UUID(client.get("/api/auth/me", headers={"Authorization": f"Bearer {token_b}"}).json()["id"])
        analysis_id = uuid.uuid4()
        with session_scope() as session:
            session.add(
                Analysis(
                    id=analysis_id,
                    user_id=owner_id,
                    jd_text="Requirements\npython\n",
                    jd_hash="abc123",
                    status="completed",
                    result_json={"audit": []},
                )
            )
        denied = client.post(
            "/api/chat",
            headers={"Authorization": f"Bearer {token_a}"},
            json={"message": "What is missing?", "analysis_id": str(analysis_id)},
        )
    assert denied.status_code == 404


def test_admin_can_open_a_trace_and_cannot_change_an_admin() -> None:
    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {register(client, 'traced@example.com')}"}
        user_id = client.get("/api/auth/me", headers=headers).json()["id"]
        analysis_id = uuid.uuid4()
        with session_scope() as session:
            session.add(
                Analysis(
                    id=analysis_id,
                    user_id=uuid.UUID(user_id),
                    jd_text="Requirements\nPython\n",
                    jd_hash="abc",
                    status="completed",
                )
            )
            run = AgentRun(analysis_id=analysis_id, skill_hash="abc", status="completed")
            session.add(run)
            session.flush()
            session.add(
                AgentStep(run_id=run.id, node="supervisor", attempt=1, input_hash="abc", tokens=3, latency_ms=12)
            )
            run_id = run.id
            seed_admin(session, "admin@example.com", "admin-password-1")
            seed_admin(session, "other-admin@example.com", "admin-password-1")
        logged_in = client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "admin-password-1"},
        )
        admin = {"Authorization": f"Bearer {logged_in.json()['access_token']}"}
        normal = client.get("/api/admin/traces", headers=headers)
        assert normal.status_code == 403
        detail = client.get(f"/api/admin/traces/{run_id}", headers=admin)
        assert detail.status_code == 200, detail.text
        assert detail.json()["steps"][0]["node"] == "supervisor"
        other = client.get("/api/admin/users?q=other-admin", headers=admin).json()
        assert client.post(f"/api/admin/users/{other[0]['id']}/block", headers=admin).status_code == 403
        assert client.delete(f"/api/admin/users/{other[0]['id']}", headers=admin).status_code == 403
