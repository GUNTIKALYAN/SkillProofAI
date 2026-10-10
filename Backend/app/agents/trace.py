import hashlib
import json
import time
import uuid

from app.db.models import AgentStep
from app.mcp_client.context import get_run


def write_step(
    node: str,
    attempt: int,
    tool: str | None,
    payload: dict,
    output: dict | None,
    tokens: int,
    started: float,
    error: str | None,
) -> None:
    ctx = get_run()
    if ctx is None:
        return
    latency = int((time.perf_counter() - started) * 1000)
    row = AgentStep(
        id=uuid.uuid4(),
        run_id=ctx.run_id,
        node=node,
        attempt=attempt,
        tool=tool,
        input_hash=_digest(payload),
        output_json=_shrink(output),
        tokens=tokens,
        latency_ms=max(latency, 0),
        error=error,
    )
    with ctx.lock:
        ctx.session.add(row)
        ctx.session.commit()


def _digest(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def _shrink(value: object) -> object:
    if isinstance(value, str):
        return value[:500]
    if isinstance(value, dict):
        return {str(key): _shrink(item) for key, item in list(value.items())[:30]}
    if isinstance(value, list):
        return [_shrink(item) for item in value[:20]]
    return value
