import logging

import httpx
import redis
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from verifymcp.auth import StaticTokenVerifier
from verifymcp.company import classify, company_query

logger = logging.getLogger(__name__)

_SCOPE = "verify:read"
_ISSUER = AnyHttpUrl("http://mcp-verify")
_CACHE_SECONDS = 30 * 24 * 60 * 60


class VerifySettings(BaseSettings):
    tavily_api_key: str
    verify_mcp_token: str
    redis_url: str
    verify_public_url: str = "http://mcp-verify:8000/mcp"
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = SettingsConfigDict(extra="ignore")


def build_server(settings: VerifySettings) -> FastMCP:
    if len(settings.verify_mcp_token) < 16:
        raise ValueError("VERIFY_MCP_TOKEN must be at least 16 characters")
    cache = redis.Redis.from_url(settings.redis_url, socket_timeout=2, socket_connect_timeout=2)
    mcp = FastMCP(
        "Verify",
        token_verifier=StaticTokenVerifier(settings.verify_mcp_token, settings.verify_public_url, _SCOPE),
        auth=AuthSettings(
            issuer_url=_ISSUER,
            resource_server_url=AnyHttpUrl(settings.verify_public_url),
            required_scopes=[_SCOPE],
        ),
        host=settings.host,
        port=settings.port,
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    @mcp.tool()
    def check_company(name: str) -> dict:
        """Look up a company name. Returns found, not_found, ambiguous, or skipped."""
        try:
            query = company_query(name)
        except ValueError:
            return {"status": "skipped", "confidence": 0.0}
        cached = _read_cache(cache, query)
        if cached is not None:
            return cached
        status, confidence = classify(_result_count(settings.tavily_api_key, query))
        payload = {"status": status, "confidence": confidence}
        if status != "skipped":
            _write_cache(cache, query, payload)
        logger.info("company check status=%s", status)
        return payload

    return mcp


def _result_count(api_key: str, query: str) -> int | None:
    try:
        response = httpx.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "max_results": 3,
                "search_depth": "basic",
                "include_answer": False,
            },
            timeout=12,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        logger.error("company search failed")
        return None
    if not isinstance(payload, dict):
        return None
    results = payload.get("results")
    if not isinstance(results, list):
        return 0
    return len(results)


def _read_cache(cache: redis.Redis, query: str) -> dict | None:
    try:
        raw = cache.get(f"company:{query.lower()}")
    except redis.RedisError:
        logger.error("company cache read failed")
        return None
    if raw == b"found":
        return {"status": "found", "confidence": 0.6}
    if raw == b"not_found":
        return {"status": "not_found", "confidence": 0.3}
    if raw == b"ambiguous":
        return {"status": "ambiguous", "confidence": 0.4}
    return None


def _write_cache(cache: redis.Redis, query: str, payload: dict) -> None:
    try:
        cache.set(f"company:{query.lower()}", payload["status"], ex=_CACHE_SECONDS)
    except redis.RedisError:
        logger.error("company cache write failed")


def load_settings() -> VerifySettings:
    try:
        return VerifySettings()
    except ValidationError as exc:
        names = ", ".join(str(err["loc"][0]).upper() for err in exc.errors() if err["loc"])
        raise RuntimeError(f"Startup failed. Missing or invalid settings: {names}.") from exc


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = load_settings()
    build_server(settings).run(transport="streamable-http")
