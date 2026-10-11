import asyncio
import logging
from datetime import timedelta
from urllib.parse import urlsplit, urlunsplit

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult

from app.config import Settings, get_settings
from app.mcp_client.catalog import SERVER_TIMEOUTS
from app.mcp_client.errors import ToolFailure

logger = logging.getLogger(__name__)


class HttpTransport:
    def call(self, server: str, tool: str, args: dict) -> dict:
        url, token, timeout = _target(get_settings(), server)
        try:
            return asyncio.run(_invoke(url, token, tool, args, timeout))
        except ToolFailure:
            raise
        except httpx.TimeoutException as exc:
            raise ToolFailure(504, retry=True) from exc
        except httpx.HTTPStatusError as exc:
            raise _from_status(exc) from exc
        except (httpx.HTTPError, OSError) as exc:
            logger.error("mcp transport failed server=%s tool=%s error=%s", server, tool, type(exc).__name__)
            raise ToolFailure(502, retry=True) from exc

    def list_tools(self, server: str) -> set[str]:
        url, token, timeout = _target(get_settings(), server)
        try:
            return asyncio.run(_list(url, token, timeout))
        except (httpx.HTTPError, OSError, ToolFailure) as exc:
            logger.error("mcp list failed server=%s error=%s", server, type(exc).__name__)
            raise ToolFailure(503, retry=False) from exc


def probe_servers(skills: dict) -> None:
    transport = HttpTransport()
    needed: dict[str, set[str]] = {}
    for skill in skills.values():
        for item in skill.tools:
            server, tool = item.split(".", 1)
            needed.setdefault(server, set()).add(tool)
    for server, tools in needed.items():
        try:
            found = transport.list_tools(server)
        except ToolFailure as exc:
            raise RuntimeError(f"Startup failed. MCP server {server} is not reachable.") from exc
        missing = tools - found
        if missing:
            names = ", ".join(sorted(missing))
            raise RuntimeError(f"Startup failed. MCP server {server} is missing {names}.")


def _target(settings: Settings, server: str) -> tuple[str, str | None, float]:
    if server == "skillgraph":
        return settings.skillgraph_url, settings.skillgraph_token, SERVER_TIMEOUTS[server]
    if server == "github":
        return settings.github_mcp_url, settings.github_mcp_token, SERVER_TIMEOUTS[server]
    if server == "tavily":
        return settings.tavily_mcp_url, settings.tavily_mcp_token, SERVER_TIMEOUTS[server]
    if server == "verify":
        return settings.verify_mcp_url, settings.verify_mcp_token, SERVER_TIMEOUTS[server]
    raise ToolFailure(404, retry=False)


def _from_status(exc: httpx.HTTPStatusError) -> ToolFailure:
    status = exc.response.status_code
    retry = status in {408, 429} or status >= 500
    header = exc.response.headers.get("Retry-After")
    retry_after = None
    if header:
        try:
            retry_after = float(header)
        except ValueError:
            retry_after = None
    return ToolFailure(status, retry=retry, retry_after=retry_after)


async def _invoke(url: str, token: str | None, tool: str, args: dict, timeout: float) -> dict:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    client_timeout = httpx.Timeout(timeout)
    async with (
        httpx.AsyncClient(headers=headers, timeout=client_timeout) as http,
        streamable_http_client(url, http_client=http) as (read, write, _session_id),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        result = await session.call_tool(
            tool,
            args,
            read_timeout_seconds=timedelta(seconds=timeout),
        )
    return _payload(result)


async def _list(url: str, token: str | None, timeout: float) -> set[str]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    client_timeout = httpx.Timeout(timeout)
    async with (
        httpx.AsyncClient(headers=headers, timeout=client_timeout) as http,
        streamable_http_client(url, http_client=http) as (read, write, _session_id),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        listed = await session.list_tools()
    return {item.name for item in listed.tools}


def skillgraph_ready(mcp_url: str, timeout: float = 2) -> bool:
    parts = urlsplit(mcp_url)
    url = urlunsplit((parts.scheme, parts.netloc, "/readyz", "", ""))
    try:
        response = httpx.get(url, timeout=timeout)
    except httpx.HTTPError as exc:
        logger.error("skillgraph check failed error=%s", type(exc).__name__)
        return False
    return response.status_code == 200


def _payload(result: CallToolResult) -> dict:
    if result.isError:
        text = " ".join(getattr(block, "text", "") or "" for block in result.content or [])
        if "not found" in text.lower():
            raise ToolFailure(404, retry=False)
        raise ToolFailure(502, retry=True)
    if isinstance(result.structuredContent, dict):
        return result.structuredContent
    raise ToolFailure(422, retry=True)
