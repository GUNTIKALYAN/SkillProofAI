import os

import pytest
from fastapi.testclient import TestClient

# Tests must not use a developer's database or secret.
os.environ.setdefault("GROQ_API_KEY", "test_dummy_key")
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = "test-jwt-secret-value-0123456789abcdef"
os.environ["COOKIE_SECURE"] = "false"
os.environ["SKILLGRAPH_URL"] = "http://skillgraph:8000/mcp"
os.environ["SKILLGRAPH_TOKEN"] = "test-skillgraph-token"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["GITHUB_MCP_URL"] = "http://mcp-github:8000/mcp"
os.environ["GITHUB_MCP_TOKEN"] = "test-github-token-0001"
os.environ["TAVILY_MCP_URL"] = "http://mcp-tavily:8000/mcp"
os.environ["TAVILY_MCP_TOKEN"] = "test-tavily-token-0001"
os.environ["VERIFY_MCP_URL"] = "http://mcp-verify:8000/mcp"
os.environ["VERIFY_MCP_TOKEN"] = "test-verify-token-0001"
os.environ["MCP_PROBE"] = "false"

TEST_PASSWORD = "password123"


@pytest.fixture(autouse=True)
def memory_metrics():
    from app.services.metrics import MemoryRecorder, set_recorder

    set_recorder(MemoryRecorder())
    yield
    set_recorder(None)


@pytest.fixture(autouse=True)
def memory_limiter():
    from app.services.rate_limit import MemoryLimiter, set_limiter

    set_limiter(MemoryLimiter())
    yield
    set_limiter(None)


@pytest.fixture(autouse=True)
def reset_database():
    from app.db import models
    from app.db.session import get_engine

    engine = get_engine()
    models.Base.metadata.drop_all(bind=engine)
    models.Base.metadata.create_all(bind=engine)
    yield
    models.Base.metadata.drop_all(bind=engine)


def register(client: TestClient, email: str = "user@example.com") -> str:
    response = client.post(
        "/api/auth/signup",
        json={"email": email, "password": TEST_PASSWORD},
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]
