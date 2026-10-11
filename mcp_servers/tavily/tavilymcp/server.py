import logging
import os
from pathlib import Path

import httpx
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from tavilymcp.auth import StaticTokenVerifier
from tavilymcp.search import parse_results, search_body

logger = logging.getLogger(__name__)

_SCOPE = "tavily:read"
_ISSUER = AnyHttpUrl("http://mcp-tavily")


class TavilySettings(BaseSettings):
    tavily_api_key: str
    tavily_mcp_token: str
    tavily_public_url: str = "http://mcp-tavily:8000/mcp"
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = SettingsConfigDict(extra="ignore")


def build_server(settings: TavilySettings) -> FastMCP:
    if len(settings.tavily_mcp_token) < 16:
        raise ValueError("TAVILY_MCP_TOKEN must be at least 16 characters")
    mcp = FastMCP(
        "Tavily",
        token_verifier=StaticTokenVerifier(settings.tavily_mcp_token, settings.tavily_public_url, _SCOPE),
        auth=AuthSettings(
            issuer_url=_ISSUER,
            resource_server_url=AnyHttpUrl(settings.tavily_public_url),
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
    def tavily_search(query: str) -> dict:
        """Search for learning resources. The query is a skill name, not a resume."""
        cleaned = " ".join(query.split())
        if not cleaned or len(cleaned) > 200:
            return {"results": []}
        try:
            response = httpx.post(
                "https://api.tavily.com/search",
                json=search_body(cleaned, settings.tavily_api_key),
                timeout=12,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.error("tavily search failed error=%s", type(exc).__name__)
            return {"results": []}
        if not isinstance(payload, dict):
            return {"results": []}
        found = parse_results(payload)
        logger.info("tavily search results=%s", len(found["results"]))
        return found

    return mcp


def load_settings() -> TavilySettings:
    try:
        return TavilySettings()
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
    _configure_logging("tavily.log")
    settings = load_settings()
    build_server(settings).run(transport="streamable-http")
