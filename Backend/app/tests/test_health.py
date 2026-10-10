import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pydantic_settings import SettingsConfigDict

from app.config import Settings, format_settings_error
from app.main import app

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_healthz() -> None:
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_responds() -> None:
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200


def test_config_imports_without_api_key() -> None:
    env = os.environ.copy()
    env.pop("GROQ_API_KEY", None)
    result = subprocess.run(
        [sys.executable, "-c", "import app.config"],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_missing_groq_key_names_the_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    class Isolated(Settings):
        model_config = SettingsConfigDict(env_file=None, extra="ignore")

    with pytest.raises(ValidationError) as caught:
        Isolated()

    message = format_settings_error(caught.value)
    assert "GROQ_API_KEY" in message
    assert "Startup failed" in message
