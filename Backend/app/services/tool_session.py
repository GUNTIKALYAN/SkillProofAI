import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.agents.skills.loader import allowlist, load_skills
from app.config import get_settings
from app.mcp_client.context import RunContext, reset_llm, reset_run, set_llm, set_run
from app.mcp_client.transport import HttpTransport
from app.services.bucket import RedisBucket
from app.services.cache import RedisCache


@dataclass
class Clients:
    transport: object
    bucket: object
    cache: object
    llm: object | None = None


def default_clients() -> Clients:
    settings = get_settings()
    return Clients(
        transport=HttpTransport(),
        bucket=RedisBucket(settings.redis_url),
        cache=RedisCache(settings.redis_url),
    )


@contextmanager
def tool_session(node: str, session: Session, clients: Clients) -> Iterator[None]:
    skills = load_skills()
    ctx = RunContext(
        run_id=uuid.uuid4(),
        session=session,
        allow=allowlist(skills),
        limits={name: skill.limits["max_tool_calls"] for name, skill in skills.items()},
        budget=skills[node].limits["max_tool_calls"],
        transport=clients.transport,
        bucket=clients.bucket,
        cache=clients.cache,
        lock=threading.Lock(),
        node_calls={},
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
