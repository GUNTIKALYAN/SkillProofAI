from functools import lru_cache
from pathlib import Path

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_NAMES = {
    "groq_api_key": "GROQ_API_KEY",
    "database_url": "DATABASE_URL",
    "jwt_secret": "JWT_SECRET",
    "skillgraph_url": "SKILLGRAPH_URL",
    "skillgraph_token": "SKILLGRAPH_TOKEN",
    "redis_url": "REDIS_URL",
    "github_mcp_url": "GITHUB_MCP_URL",
    "tavily_mcp_url": "TAVILY_MCP_URL",
    "tavily_mcp_token": "TAVILY_MCP_TOKEN",
    "verify_mcp_url": "VERIFY_MCP_URL",
    "verify_mcp_token": "VERIFY_MCP_TOKEN",
}

_DEFAULT_ORIGINS = (
    "http://localhost:3000,http://127.0.0.1:3000,"
    "http://localhost:8000,http://127.0.0.1:8000,"
    "http://localhost:5500,http://127.0.0.1:5500"
)


def _env_files() -> tuple[str, ...]:
    here = Path(__file__).resolve()
    candidates = (
        Path.cwd() / ".env",
        here.parents[1] / ".env",
        here.parents[2] / ".env",
    )
    return tuple(str(path) for path in candidates if path.is_file())


class Settings(BaseSettings):
    groq_api_key: str = Field(min_length=1)
    llama_model: str = "openai/gpt-oss-20b"
    max_upload_bytes: int = Field(default=5 * 1024 * 1024, gt=0)
    database_url: str = Field(min_length=1)
    jwt_secret: str = Field(min_length=32)
    access_token_minutes: int = Field(default=15, gt=0)
    refresh_token_days: int = Field(default=7, gt=0)
    cookie_secure: bool = False
    cors_origins: str = _DEFAULT_ORIGINS
    admin_email: str | None = None
    admin_password: str | None = None
    skillgraph_url: str = Field(min_length=1)
    skillgraph_token: str = Field(min_length=16)
    redis_url: str = Field(min_length=1)
    github_mcp_url: str = Field(min_length=1)
    tavily_mcp_url: str = Field(min_length=1)
    tavily_mcp_token: str = Field(min_length=16)
    verify_mcp_url: str = Field(min_length=1)
    verify_mcp_token: str = Field(min_length=16)
    mcp_probe: bool = True
    tool_budget: int = Field(default=40, gt=0)

    model_config = SettingsConfigDict(
        env_file=_env_files() or None,
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def format_settings_error(exc: ValidationError) -> str:
    names: list[str] = []
    for err in exc.errors():
        if not err["loc"]:
            continue
        field = str(err["loc"][0])
        names.append(_ENV_NAMES.get(field, field.upper()))
    listed = ", ".join(dict.fromkeys(names)) if names else "invalid values"
    return (
        f"Startup failed. Missing or invalid settings: {listed}. "
        "Copy .env.example to .env and set them."
    )


def load_settings() -> Settings:
    try:
        return get_settings()
    except ValidationError as exc:
        raise RuntimeError(format_settings_error(exc)) from exc
