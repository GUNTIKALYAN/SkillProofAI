import threading
from collections.abc import Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session


@dataclass
class RunContext:
    run_id: UUID
    session: Session
    allow: dict[str, set[tuple[str, str]]]
    limits: dict[str, int]
    budget: int
    transport: object
    bucket: object
    cache: object
    lock: threading.Lock
    node_calls: dict[str, int]


_run: ContextVar[RunContext | None] = ContextVar("mcp_run", default=None)


def set_run(ctx: RunContext) -> Token[RunContext | None]:
    return _run.set(ctx)


def reset_run(token: Token[RunContext | None]) -> None:
    _run.reset(token)


def get_run() -> RunContext | None:
    return _run.get()


LlmCaller = Callable[[str, str], tuple[dict, int]]

_llm: ContextVar[LlmCaller | None] = ContextVar("llm_caller", default=None)


def set_llm(caller: LlmCaller) -> Token[LlmCaller | None]:
    return _llm.set(caller)


def reset_llm(token: Token[LlmCaller | None]) -> None:
    _llm.reset(token)


def get_llm() -> LlmCaller | None:
    return _llm.get()
