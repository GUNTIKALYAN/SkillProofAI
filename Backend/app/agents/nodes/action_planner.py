import logging
import time

from pydantic import BaseModel, ValidationError

from app.agents.routing import gap_names
from app.agents.trace import write_step
from app.llm.complete import LlmError, complete_json
from app.mcp_client import McpError, call_tool
from app.schemas.agents import ActionPlan

logger = logging.getLogger(__name__)
_MAX_GAPS = 8


def action_planner(state: dict) -> dict:
    started = time.perf_counter()
    gaps = gap_names(state.get("audit"))[:_MAX_GAPS]
    payload = {"gaps": gaps}
    resources = _resources(gaps)
    try:
        plan, tokens = complete_json(
            "action_planner",
            {"gaps": gaps, "untrusted_results": resources},
            ActionPlan,
            check=_gap_check(gaps),
        )
        body = plan.model_dump()
        write_step("action_planner", 1, None, payload, {"items": len(body["items"])}, tokens, started, None)
        return {"plan": body}
    except (LlmError, ValidationError) as exc:
        logger.error("action plan fallback error=%s", type(exc).__name__)
        body = _fallback(gaps)
        write_step("action_planner", 1, None, payload, {"fallback": True}, 0, started, type(exc).__name__)
        return {"plan": body}


def _resources(gaps: list[str]) -> dict[str, list]:
    found: dict[str, list] = {}
    for skill in gaps:
        try:
            result = call_tool("tavily", "tavily_search", {"query": skill}, "action_planner")
            found[skill] = list(result.get("results") or [])[:5]
        except McpError:
            logger.error("resource search failed")
            found[skill] = []
    return found


def _gap_check(gaps: list[str]):
    allowed = set(gaps)

    def check(plan: BaseModel) -> None:
        for item in ActionPlan.model_validate(plan.model_dump()).items:
            if item.skill not in allowed:
                raise ValueError(f"{item.skill} is not a gap")

    return check


def _fallback(gaps: list[str]) -> dict:
    return {
        "items": [
            {
                "skill": skill,
                "steps": [f"Practice {skill} in a small project and write down what you built."],
                "resources": [],
            }
            for skill in gaps
        ],
        "fallback": True,
    }
