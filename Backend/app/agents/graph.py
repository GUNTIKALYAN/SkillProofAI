import logging
import threading
import time
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.nodes.action_planner import action_planner
from app.agents.nodes.collect import experience_check, github_fetch
from app.agents.nodes.match_score import match_score
from app.agents.nodes.skill_audit import skill_audit
from app.agents.routing import choose_next
from app.agents.trace import write_step

logger = logging.getLogger(__name__)

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


def supervisor(state: AnalysisState) -> dict:
    started = time.perf_counter()
    nxt = choose_next(state)
    write_step("supervisor", int(state.get("step_count") or 0) + 1, None, {"next": nxt}, {"next": nxt}, 0, started, None)
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
