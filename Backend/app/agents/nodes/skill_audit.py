import logging
import time

from app.agents.nodes.collect import unsupported_flags
from app.agents.trace import write_step
from app.llm.complete import LlmError, complete_json
from app.mcp_client import McpError, call_tool
from app.schemas.agents import Explanations
from app.services.experience_checks import audit_flags

logger = logging.getLogger(__name__)


def skill_audit(state: dict) -> dict:
    started = time.perf_counter()
    match = state.get("match") or {}
    payload = {"has_score": "score" in match}
    if match.get("error") or "extraction" not in match:
        write_step("skill_audit", 1, None, payload, None, 0, started, "match unavailable")
        return {"audit": {"items": []}, "audit_error": "Match score is unavailable"}
    extraction = match["extraction"]
    try:
        audited = call_tool(
            "skillgraph",
            "audit_skills",
            {
                "jd_skills": extraction["jd_skills"],
                "candidate_skills": extraction["resume_skills"],
            },
            "skill_audit",
        )
        items = list(audited.get("items") or [])
        extra = unsupported_flags(state)
        tokens = _explain(items, state.get("github_evidence"))
        merged = _with_reasons(items, tokens[1])
        for flag in audit_flags((state.get("experience") or {}).get("flags") or []):
            merged.append({"skill": "experience", "status": "partial", "reason": flag["detail"]})
        for flag in extra:
            merged.append({"skill": "experience", "status": "partial", "reason": flag["detail"]})
        write_step("skill_audit", 1, None, payload, {"count": len(merged)}, tokens[0], started, None)
        return {"audit": {"items": merged}}
    except (McpError, LlmError) as exc:
        logger.error("skill audit failed error=%s", type(exc).__name__)
        write_step("skill_audit", 1, None, payload, None, 0, started, type(exc).__name__)
        return {"audit": {"items": []}, "audit_error": "Skill audit is unavailable"}


def _explain(items: list[dict], github: dict | None) -> tuple[int, dict[str, str]]:
    try:
        explained, tokens = complete_json(
            "skill_audit",
            {"classifications": items, "untrusted_github": github or {}},
            Explanations,
        )
    except LlmError:
        return 0, {}
    reasons = {item.skill: item.explanation for item in explained.items}
    return tokens, reasons


def _with_reasons(items: list[dict], reasons: dict[str, str]) -> list[dict]:
    merged: list[dict] = []
    for item in items:
        status = item.get("status")
        if status not in {"matched", "partial", "missing"}:
            status = "missing"
        merged.append(
            {
                "skill": item.get("skill") or "",
                "status": status,
                "reason": reasons.get(item.get("skill") or "") or item.get("reason") or "",
            }
        )
    return merged
