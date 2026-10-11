import logging
import os
from pathlib import Path

import httpx
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from githubmcp.auth import StaticTokenVerifier
from githubmcp.repos import public_repos, valid_username

logger = logging.getLogger(__name__)

_SCOPE = "github:read"
_ISSUER = AnyHttpUrl("http://mcp-github")
_REPOS_URL = "https://api.github.com/users/{username}/repos"


class GithubSettings(BaseSettings):
    github_token: str = ""
    github_mcp_token: str
    github_public_url: str = "http://mcp-github:8000/mcp"
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = SettingsConfigDict(extra="ignore")


def build_server(settings: GithubSettings) -> FastMCP:
    if len(settings.github_mcp_token) < 16:
        raise ValueError("GITHUB_MCP_TOKEN must be at least 16 characters")
    mcp = FastMCP(
        "GitHub",
        token_verifier=StaticTokenVerifier(settings.github_mcp_token, settings.github_public_url, _SCOPE),
        auth=AuthSettings(
            issuer_url=_ISSUER,
            resource_server_url=AnyHttpUrl(settings.github_public_url),
            validate_token_resource=True,
            required_scopes=[_SCOPE],
        ),
        host=settings.host,
        port=settings.port,
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    @mcp.tool()
    def list_public_repos(username: str) -> dict:
        """List public repositories for one GitHub username. Read only."""
        cleaned = valid_username(username)
        if cleaned is None:
            return {"repositories": []}
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "skillproof",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        token = settings.github_token.strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            response = httpx.get(
                _REPOS_URL.format(username=cleaned),
                params={"per_page": 20, "sort": "updated", "type": "owner"},
                headers=headers,
                timeout=15,
            )
            if response.status_code == 404:
                return {"repositories": []}
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            logger.error("github repos failed")
            return {"repositories": []}
        found = public_repos(payload)
        logger.info("github repos count=%s", len(found["repositories"]))
        return found

    return mcp


def load_settings() -> GithubSettings:
    try:
        return GithubSettings()
    except ValidationError as exc:
        names = ", ".join(str(err["loc"][0]).upper() for err in exc.errors() if err["loc"])
        raise RuntimeError(f"Startup failed. Missing or invalid settings: {names}.") from exc


def _configure_logging(filename: str) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    log_dir = os.environ.get("LOG_DIR", "").strip()
    if log_dir:
        path = Path(log_dir) / filename
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            handlers.append(logging.FileHandler(path, encoding="utf-8"))
        except OSError:
            pass
    logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=handlers, force=True)


def main() -> None:
    _configure_logging("github.log")
    settings = load_settings()
    build_server(settings).run(transport="streamable-http")
