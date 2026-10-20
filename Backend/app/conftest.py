import os

import pytest
from fastapi.testclient import TestClient

# Tests must not use a developer's database or secret.
os.environ.setdefault("GROQ_API_KEY", "test_dummy_key")
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = "test-jwt-secret-value-0123456789abcdef"
os.environ["COOKIE_SECURE"] = "false"
os.environ["MCP_URL"] = "http://mcp:8000/mcp"
os.environ["MCP_TOKEN"] = "test-mcp-token-0001"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["MCP_PROBE"] = "false"

TEST_PASSWORD = "password123"


@pytest.fixture(autouse=True)
def reset_database():
    from app.db import Base, get_engine

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def register(client: TestClient, email: str = "user@example.com") -> str:
    response = client.post(
        "/api/auth/signup",
        json={"email": email, "password": TEST_PASSWORD},
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]
