import hashlib
import json
import logging
import threading
import time
import uuid
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.db import AgentStep
from app.mcp_client import get_run

logger = logging.getLogger(__name__)

MAX_STEPS = 8
_GAPS = {"partial", "missing"}
_WORKERS = (
    "github_fetch",
    "match_score",
    "experience_check",
    "skill_audit",
    "action_planner",
    "finalize",
)


class AnalysisState(TypedDict, total=False):
    step_count: int
    github_username: str | None
    has_experience: bool
    resume: dict
    jd_text: str
    github_evidence: dict | None
    github_skipped: bool
    github_error: str | None
    match: dict | None
    match_retries: int
    experience: dict | None
    experience_skipped: bool
    experience_error: str | None
    audit: dict | None
    audit_error: str | None
    plan: dict | None
    plan_error: str | None
    done: bool
    route: list[str]


def choose_next(state: dict) -> list[str]:
    if int(state.get("step_count") or 0) >= MAX_STEPS or state.get("done"):
        return ["finalize"]
    pending: list[str] = []
    if state.get("github_username") and state.get("github_evidence") is None and not state.get("github_error"):
        pending.append("github_fetch")
    match = state.get("match")
    retries = int(state.get("match_retries") or 0)
    if match is None or (match.get("low_confidence") and not match.get("error") and retries < 1):
        pending.append("match_score")
    if state.get("has_experience") and state.get("experience") is None and not state.get("experience_error"):
        pending.append("experience_check")
    if pending:
        return pending
    if state.get("audit") is None and not state.get("audit_error"):
        return ["skill_audit"]
    if gap_names(state.get("audit")) and state.get("plan") is None and not state.get("plan_error"):
        return ["action_planner"]
    return ["finalize"]


def gap_names(audit: dict | None) -> list[str]:
    if not audit:
        return []
    names: list[str] = []
    for item in audit.get("items") or []:
        skill = item.get("skill")
        if item.get("status") in _GAPS and skill and skill != "experience" and skill not in names:
            names.append(skill)
    return names


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
    if ctx is None or not ctx.trace:
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


def supervisor(state: AnalysisState) -> dict:
    started = time.perf_counter()
    nxt = choose_next(state)
    write_step(
        "supervisor",
        int(state.get("step_count") or 0) + 1,
        None,
        {"next": nxt},
        {"next": nxt},
        0,
        started,
        None,
    )
    return {
        "step_count": int(state.get("step_count") or 0) + 1,
        "route": nxt,
        "github_skipped": not state.get("github_username"),
        "experience_skipped": not state.get("has_experience"),
    }


def route(state: AnalysisState) -> list[str]:
    return list(state.get("route") or ["finalize"])


def finalize(state: AnalysisState) -> dict:
    del state
    return {"done": True}


def _build():
    from app.agents.nodes import (
        action_planner,
        experience_check,
        github_fetch,
        match_score,
        skill_audit,
    )

    graph = StateGraph(AnalysisState)
    graph.add_node("supervisor", supervisor)
    graph.add_node("github_fetch", github_fetch)
    graph.add_node("match_score", match_score)
    graph.add_node("experience_check", experience_check)
    graph.add_node("skill_audit", skill_audit)
    graph.add_node("action_planner", action_planner)
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges("supervisor", route, list(_WORKERS))
    for name in _WORKERS:
        if name != "finalize":
            graph.add_edge(name, "supervisor")
    graph.add_edge("finalize", END)
    return graph.compile()


_compiled = None
_lock = threading.Lock()


def get_graph():
    global _compiled
    if _compiled is None:
        with _lock:
            if _compiled is None:
                _compiled = _build()
                logger.info("supervisor graph built")
    return _compiled


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
