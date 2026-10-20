import asyncio
import json
import logging
import random
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import timedelta

import httpx
import redis
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult
from sqlalchemy.orm import Session

from app.agents.skills_loader import allowlist, load_skills
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
EXTERNAL_LIMIT = 30
EXTERNAL_WINDOW = 60
EXTERNAL_TOOLS = frozenset({"list_public_repos", "tavily_search", "check_company"})
KNOWN_TOOLS = frozenset(
    {
        "canonicalize_skill",
        "score_match",
        "audit_skills",
        "related_skills",
        "explain_skill",
        "what_if_learn",
        "list_public_repos",
        "tavily_search",
        "check_company",
    }
)
_NO_RETRY = {400, 401, 403, 404}
_TIMEOUTS = {
    "list_public_repos": 20.0,
    "tavily_search": 15.0,
    "check_company": 15.0,
}

LlmCaller = Callable[[str, str], tuple[dict, int]]


class McpError(Exception):
    pass


class ToolFailure(Exception):
    def __init__(self, status: int, *, retry_after: float | None = None) -> None:
        self.status = status
        self.retry_after = retry_after
        super().__init__(f"status {status}")


@dataclass
class RunContext:
    run_id: uuid.UUID
    session: Session
    allow: dict[str, set[str]]
    limits: dict[str, int]
    budget: int
    transport: object
    lock: threading.Lock
    node_calls: dict[str, int]
    limiter: object
    trace: bool = True


@dataclass
class Clients:
    transport: object
    llm: object | None = None


_run: ContextVar[RunContext | None] = ContextVar("mcp_run", default=None)
_llm: ContextVar[LlmCaller | None] = ContextVar("llm_caller", default=None)
_redis: redis.Redis | None = None


def set_run(ctx: RunContext) -> Token[RunContext | None]:
    return _run.set(ctx)


def reset_run(token: Token[RunContext | None]) -> None:
    _run.reset(token)


def get_run() -> RunContext | None:
    return _run.get()


def set_llm(caller: LlmCaller) -> Token[LlmCaller | None]:
    return _llm.set(caller)


def reset_llm(token: Token[LlmCaller | None]) -> None:
    _llm.reset(token)


def get_llm() -> LlmCaller | None:
    return _llm.get()


def default_clients() -> Clients:
    return Clients(transport=HttpTransport())


class RedisLimiter:
    def __init__(self, client: object | None = None, limit: int = EXTERNAL_LIMIT) -> None:
        self._client = client
        self._limit = limit

    def allow(self, tool: str) -> None:
        if tool not in EXTERNAL_TOOLS:
            return
        client = self._client if self._client is not None else _redis_client()
        key = f"rl:mcp:{tool}"
        try:
            pipe = client.pipeline()
            pipe.incr(key)
            pipe.expire(key, EXTERNAL_WINDOW, nx=True)
            count, _set = pipe.execute()
            if int(count) <= self._limit:
                return
            retry = int(client.ttl(key))
        except redis.RedisError as exc:
            logger.error("mcp rate limiter unavailable tool=%s", tool)
            raise McpError("Rate limiter is unavailable") from exc
        raise McpError(f"Tool rate limit reached. Retry after {max(retry, 1)} seconds")


class HttpTransport:
    def call(self, tool: str, args: dict) -> dict:
        settings = get_settings()
        timeout = _TIMEOUTS.get(tool, 10.0)
        try:
            return asyncio.run(_invoke(settings, tool, args, timeout))
        except ToolFailure:
            raise
        except httpx.TimeoutException as exc:
            raise ToolFailure(504) from exc
        except httpx.HTTPStatusError as exc:
            raise _from_status(exc) from exc
        except (httpx.HTTPError, OSError) as exc:
            logger.error("mcp transport failed tool=%s error=%s", tool, type(exc).__name__)
            raise ToolFailure(502) from exc
        except BaseException as exc:
            if not getattr(exc, "exceptions", None):
                raise
            logger.error("mcp transport failed tool=%s error=%s", tool, type(exc).__name__)
            raise ToolFailure(502) from exc

    def list_tools(self) -> set[str]:
        settings = get_settings()
        try:
            return asyncio.run(_list(settings, 10.0))
        except (httpx.HTTPError, OSError, ToolFailure) as exc:
            logger.error("mcp list failed error=%s", type(exc).__name__)
            raise ToolFailure(503) from exc
        except BaseException as exc:
            if not getattr(exc, "exceptions", None):
                raise
            logger.error("mcp list failed error=%s", type(exc).__name__)
            raise ToolFailure(503) from exc


def probe_server(skills: dict) -> None:
    needed: set[str] = set()
    for skill in skills.values():
        needed.update(skill.tools)
    try:
        found = HttpTransport().list_tools()
    except ToolFailure as exc:
        raise RuntimeError("Startup failed. MCP server is not reachable.") from exc
    missing = needed - found
    if missing:
        names = ", ".join(sorted(missing))
        raise RuntimeError(f"Startup failed. MCP server is missing {names}.")


def call_tool(tool: str, args: dict, node: str) -> dict:
    ctx = get_run()
    if ctx is None:
        raise McpError("Tool call outside an analysis run")
    _reserve(ctx, tool, node)
    last_error = "Tool call failed"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        started = time.perf_counter()
        try:
            result = ctx.transport.call(tool, args)
        except ToolFailure as exc:
            last_error = f"status {exc.status}"
            logger.error("mcp call failed tool=%s attempt=%s status=%s", tool, attempt, exc.status)
            _write(node, attempt, tool, args, None, started, last_error)
            if exc.status in _NO_RETRY or attempt == MAX_ATTEMPTS or not _retryable(exc.status):
                break
            _sleep(_delay(attempt, exc.retry_after))
            continue
        if not isinstance(result, dict):
            last_error = "status 422"
            logger.error("mcp call failed tool=%s attempt=%s status=422", tool, attempt)
            _write(node, attempt, tool, args, None, started, last_error)
            if attempt == MAX_ATTEMPTS:
                break
            _sleep(_delay(attempt, None))
            continue
        _write(node, attempt, tool, args, result, started, None)
        return result
    raise McpError(last_error)


@contextmanager
def open_tools(node: str, session: Session, clients: Clients) -> Iterator[None]:
    skills = load_skills()
    ctx = RunContext(
        run_id=uuid.uuid4(),
        session=session,
        allow=allowlist(skills),
        limits={name: skill.limits["max_tool_calls"] for name, skill in skills.items()},
        budget=get_settings().tool_budget,
        transport=clients.transport,
        lock=threading.Lock(),
        node_calls={},
        limiter=RedisLimiter(),
        trace=False,
    )
    token_run = set_run(ctx)
    token_llm = set_llm(clients.llm) if clients.llm is not None else None
    try:
        yield
    finally:
        if token_llm is not None:
            reset_llm(token_llm)
        reset_run(token_run)


def _reserve(ctx: RunContext, tool: str, node: str) -> None:
    with ctx.lock:
        if tool not in ctx.allow.get(node, set()):
            raise McpError("Tool is not allowed for this step")
        limit = ctx.limits.get(node, 0)
        used = ctx.node_calls.get(node, 0)
        if ctx.budget <= 0 or used >= limit:
            raise McpError("Tool call budget is used up")
    ctx.limiter.allow(tool)
    with ctx.lock:
        if ctx.budget <= 0 or ctx.node_calls.get(node, 0) >= ctx.limits.get(node, 0):
            raise McpError("Tool call budget is used up")
        ctx.budget -= 1
        ctx.node_calls[node] = ctx.node_calls.get(node, 0) + 1


def _retryable(status: int) -> bool:
    return status == 422 or status == 429 or status >= 500


def _write(
    node: str,
    attempt: int,
    tool: str,
    args: dict,
    output: dict | None,
    started: float,
    error: str | None,
) -> None:
    from app.agents.graph import write_step

    write_step(node, attempt, tool, args, output, 0, started, error)


def _delay(attempt: int, retry_after: float | None) -> float:
    if retry_after is not None:
        return max(retry_after, 0)
    base = 0.5 * (2 ** (attempt - 1))
    return base + random.uniform(0, 0.1)


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _redis_client() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.Redis.from_url(get_settings().redis_url, socket_timeout=2, socket_connect_timeout=2)
    return _redis


def _from_status(exc: httpx.HTTPStatusError) -> ToolFailure:
    status = exc.response.status_code
    header = exc.response.headers.get("Retry-After")
    retry_after = None
    if header:
        try:
            retry_after = float(header)
        except ValueError:
            retry_after = None
    return ToolFailure(status, retry_after=retry_after)


async def _invoke(settings: Settings, tool: str, args: dict, timeout: float) -> dict:
    headers = {"Authorization": f"Bearer {settings.mcp_token}"}
    async with (
        httpx.AsyncClient(headers=headers, timeout=httpx.Timeout(timeout)) as http,
        streamable_http_client(settings.mcp_url, http_client=http) as (read, write, _session_id),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        result = await session.call_tool(tool, args, read_timeout_seconds=timedelta(seconds=timeout))
    return _payload(result)


async def _list(settings: Settings, timeout: float) -> set[str]:
    headers = {"Authorization": f"Bearer {settings.mcp_token}"}
    async with (
        httpx.AsyncClient(headers=headers, timeout=httpx.Timeout(timeout)) as http,
        streamable_http_client(settings.mcp_url, http_client=http) as (read, write, _session_id),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        listed = await session.list_tools()
    return {item.name for item in listed.tools}


def _payload(result: CallToolResult) -> dict:
    if result.isError:
        text = " ".join(getattr(block, "text", "") or "" for block in result.content or [])
        if "not found" in text.lower():
            raise ToolFailure(404)
        raise ToolFailure(502)
    if isinstance(result.structuredContent, dict):
        return result.structuredContent
    for block in result.content or []:
        text = getattr(block, "text", None)
        if not isinstance(text, str):
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ToolFailure(422)
