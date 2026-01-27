import os
import pytest

@pytest.fixture(autouse=True)
def mock_groq_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test_dummy_key")
