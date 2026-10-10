import logging
import random
import time

from app.mcp_client.context import get_run
from app.mcp_client.errors import McpError, SkillGraphError, ToolFailure
from app.services.bucket import BucketError

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
_BREAKER_LIMIT = 5
_BREAKER_OPEN = 30.0
_NO_RETRY = {400, 401, 403, 404}


class _Breaker:
    def __init__(self) -> None:
        self.failures: dict[str, int] = {}
        self.open_until: dict[str, float] = {}

    def allow(self, server: str, now: float) -> bool:
        return now >= self.open_until.get(server, 0)

    def ok(self, server: str) -> None:
        self.failures[server] = 0
        self.open_until.pop(server, None)

    def fail(self, server: str, now: float) -> None:
        count = self.failures.get(server, 0) + 1
        self.failures[server] = count
        if count >= _BREAKER_LIMIT:
            self.open_until[server] = now + _BREAKER_OPEN
            self.failures[server] = 0


_breaker = _Breaker()


def reset_breaker() -> None:
    _breaker.failures.clear()
    _breaker.open_until.clear()


def _now() -> float:
    return time.monotonic()


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def call_tool(server: str, tool: str, args: dict, node: str) -> dict:
    ctx = get_run()
    if ctx is None:
        raise McpError("Tool call outside an analysis run")
    with ctx.lock:
        if (server, tool) not in ctx.allow.get(node, set()):
            raise McpError("Tool is not allowed for this step")
        if not _breaker.allow(server, _now()):
            raise McpError("Tool server is paused")
        limit = ctx.limits.get(node, 0)
        used = ctx.node_calls.get(node, 0)
        if ctx.budget <= 0 or used >= limit:
            raise McpError("Tool call budget is used up")
        try:
            allowed = ctx.bucket.take(server)
        except BucketError as exc:
            raise McpError("Tool server is rate limited") from exc
        if not allowed:
            raise McpError("Tool server is rate limited")
        ctx.budget -= 1
        ctx.node_calls[node] = used + 1
    last_error = "Tool call failed"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if not _breaker.allow(server, _now()):
            last_error = "Tool server is paused"
            break
        started = time.perf_counter()
        try:
            result = ctx.transport.call(server, tool, args)
        except ToolFailure as exc:
            last_error = f"status {exc.status}"
            logger.error(
                "mcp call failed server=%s tool=%s attempt=%s status=%s",
                server,
                tool,
                attempt,
                exc.status,
            )
            _write(node, attempt, f"{server}.{tool}", args, None, started, last_error)
            with ctx.lock:
                _breaker.fail(server, _now())
            if not exc.retry or exc.status in _NO_RETRY or attempt == MAX_ATTEMPTS:
                break
            _sleep(_delay(attempt, exc.retry_after))
            continue
        _write(node, attempt, f"{server}.{tool}", args, result, started, None)
        with ctx.lock:
            _breaker.ok(server)
        return result
    raise McpError(last_error)


def _write(node: str, attempt: int, tool: str, args: dict, output: dict | None, started: float, error: str | None) -> None:
    from app.agents.trace import write_step

    write_step(node, attempt, tool, args, output, 0, started, error)


def _delay(attempt: int, retry_after: float | None) -> float:
    if retry_after is not None:
        return max(retry_after, 0)
    base = 0.5 * (2 ** (attempt - 1))
    return base + random.uniform(0, 0.1)


__all__ = ["McpError", "SkillGraphError", "ToolFailure", "call_tool", "reset_breaker"]
