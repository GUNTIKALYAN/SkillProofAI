import logging
import time

from pydantic import BaseModel, ValidationError

from app.agents.graph import gap_names, write_step
from app.guard import guard_document
from app.llm import LlmError, complete_json
from app.mcp_client import McpError, call_tool
from app.schemas.agents import ActionPlan, ExperienceParse, Explanations
from app.services.experience_checks import audit_flags, check_entries
from app.services.skill_extract import SkillExtraction, clip_text

logger = logging.getLogger(__name__)
_MAX_GAPS = 8


def github_fetch(state: dict) -> dict:
    started = time.perf_counter()
    username = str(state.get("github_username") or "")
    payload = {"username": username}
    try:
        raw = call_tool("list_public_repos", {"username": username}, "github_fetch")
        evidence = {"repos": _repos(raw)}
        write_step("github_fetch", 1, None, payload, evidence, 0, started, None)
        return {"github_evidence": evidence}
    except McpError as exc:
        logger.error("github fetch failed error=%s", type(exc).__name__)
        write_step("github_fetch", 1, None, payload, None, 0, started, type(exc).__name__)
        return {"github_evidence": {"repos": []}, "github_error": "GitHub evidence is unavailable"}


def match_score(state: dict) -> dict:
    started = time.perf_counter()
    payload = {
        "resume_chars": len(_resume_text(state)),
        "jd_chars": len(state.get("jd_text") or ""),
    }
    try:
        extraction, tokens = complete_json(
            "match_score",
            {
                "resume": clip_text(_resume_text(state), "resume"),
                "job_description": clip_text(state.get("jd_text") or "", "job description"),
            },
            SkillExtraction,
        )
        score = call_tool(
            "score_match",
            {
                "jd_skills": [item.model_dump() for item in extraction.jd_skills],
                "candidate_skills": extraction.resume_skills,
            },
            "match_score",
        )
        unknown = _unknown_skills(score)
        low = _low_score(score)
        retries = int(state.get("match_retries") or 0)
        previous = state.get("match") or {}
        if previous.get("low_confidence"):
            retries += 1
        result = {
            "extraction": extraction.model_dump(),
            "score": score,
            "unknown_skills": unknown,
            "low_confidence": low,
        }
        write_step(
            "match_score",
            1,
            None,
            payload,
            {"score": score.get("score"), "low_confidence": low},
            tokens,
            started,
            None,
        )
        return {"match": result, "match_retries": retries}
    except (McpError, LlmError, ValidationError) as exc:
        logger.error("match score failed error=%s", type(exc).__name__)
        write_step("match_score", 1, None, payload, None, 0, started, type(exc).__name__)
        return {
            "match": {"error": "Match score is unavailable", "low_confidence": False, "unknown_skills": []},
            "match_retries": 1,
        }


def experience_check(state: dict) -> dict:
    started = time.perf_counter()
    text = "\n".join(str(line) for line in (state.get("resume") or {}).get("experience") or [])
    payload = {"chars": len(text)}
    try:
        parsed, tokens = complete_json(
            "experience_check",
            {"experience_text": guard_document("experience", text)},
            ExperienceParse,
        )
        flags = check_entries(parsed.entries)
        companies = _companies(parsed)
        result = {
            "flags": flags,
            "companies": companies,
            "entries": [entry.model_dump() for entry in parsed.entries],
        }
        write_step("experience_check", 1, None, payload, {"flags": len(flags)}, tokens, started, None)
        return {"experience": result}
    except (McpError, LlmError, ValidationError) as exc:
        logger.error("experience check failed error=%s", type(exc).__name__)
        write_step("experience_check", 1, None, payload, None, 0, started, type(exc).__name__)
        return {"experience": {"flags": [], "companies": []}, "experience_error": "Experience check is unavailable"}


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
            "audit_skills",
            {
                "jd_skills": extraction["jd_skills"],
                "candidate_skills": extraction["resume_skills"],
            },
            "skill_audit",
        )
        items = list(audited.get("items") or [])
        extra = _unsupported(state)
        tokens, reasons = _explain(items, state.get("github_evidence"))
        merged = _with_reasons(items, reasons)
        for flag in audit_flags((state.get("experience") or {}).get("flags") or []):
            merged.append({"skill": "experience", "status": "partial", "reason": flag["detail"]})
        for flag in extra:
            merged.append({"skill": "experience", "status": "partial", "reason": flag["detail"]})
        write_step("skill_audit", 1, None, payload, {"count": len(merged)}, tokens, started, None)
        return {"audit": {"items": merged}}
    except (McpError, LlmError) as exc:
        logger.error("skill audit failed error=%s", type(exc).__name__)
        write_step("skill_audit", 1, None, payload, None, 0, started, type(exc).__name__)
        return {"audit": {"items": []}, "audit_error": "Skill audit is unavailable"}


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


def _unknown_skills(score: dict) -> list[str]:
    found: list[str] = []
    for item in score.get("breakdown") or []:
        if not isinstance(item, dict) or item.get("kind") != "unknown":
            continue
        key = str(item.get("skill") or "").strip().lower()
        if key and key not in found:
            found.append(key)
    return sorted(found)


def _low_score(score: dict) -> bool:
    items = [item for item in (score.get("breakdown") or []) if isinstance(item, dict)]
    if not items:
        return True
    unknown = sum(1 for item in items if item.get("kind") == "unknown")
    return unknown * 2 >= len(items)


def _resume_text(state: dict) -> str:
    resume = state.get("resume") or {}
    raw = resume.get("text") or []
    if raw:
        return "\n".join(str(line) for line in raw)
    lines: list[str] = []
    for key in ("skills", "projects", "experience"):
        lines.extend(str(line) for line in resume.get(key) or [])
    return "\n".join(lines)


def _companies(parsed: ExperienceParse) -> list[dict]:
    found: list[dict] = []
    seen: set[str] = set()
    for entry in parsed.entries:
        name = entry.company.strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        result = call_tool("check_company", {"name": name}, "experience_check")
        status = result.get("status")
        if status not in {"found", "not_found", "ambiguous", "skipped"}:
            status = "skipped"
        found.append({"name": name, "status": status, "confidence": result.get("confidence")})
    return found


def _unsupported(state: dict) -> list[dict]:
    entries = (state.get("experience") or {}).get("entries") or []
    evidence = _evidence(state)
    flags: list[dict] = []
    for entry in entries:
        for part in _parts(entry.get("bullets") or []):
            found = call_tool("canonicalize_skill", {"text": part}, "skill_audit")
            canonical = found.get("canonical")
            if not found.get("known") or not isinstance(canonical, str):
                continue
            if canonical.strip().lower() not in evidence:
                flags.append(
                    {
                        "kind": "unsupported",
                        "detail": f"{canonical} is not supported by the resume or GitHub evidence.",
                    }
                )
    return flags


def _evidence(state: dict) -> set[str]:
    names: set[str] = set()
    extraction = (state.get("match") or {}).get("extraction") or {}
    for name in extraction.get("resume_skills") or []:
        names.add(str(name).strip().lower())
    for repo in (state.get("github_evidence") or {}).get("repos") or []:
        language = str(repo.get("language") or "").strip().lower()
        if language:
            names.add(language)
    return names


def _parts(bullets: list[str]) -> list[str]:
    parts: list[str] = []
    for bullet in bullets:
        for part in bullet.replace(" and ", ",").split(","):
            cleaned = part.strip()
            if 1 < len(cleaned) <= 40:
                parts.append(cleaned)
    return parts


def _repos(payload: dict) -> list[dict]:
    raw = payload.get("repositories") or payload.get("items") or payload.get("results") or []
    repos: list[dict] = []
    if not isinstance(raw, list):
        return repos
    for item in raw[:20]:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("full_name") or ""
        repos.append(
            {
                "name": str(name)[:120],
                "language": str(item.get("language") or "")[:40],
                "description": str(item.get("description") or "")[:200],
                "readme": str(item.get("readme") or "")[:500],
            }
        )
    return repos


def _explain(items: list[dict], github: dict | None) -> tuple[int, dict[str, str]]:
    try:
        explained, tokens = complete_json(
            "skill_audit",
            {"classifications": items, "untrusted_github": _model_github(github)},
            Explanations,
        )
    except LlmError:
        return 0, {}
    reasons = {item.skill: item.explanation for item in explained.items}
    return tokens, reasons


def _model_github(github: dict | None) -> dict:
    if not github:
        return {}
    repos: list[dict] = []
    for repo in github.get("repos") or []:
        if not isinstance(repo, dict):
            continue
        repos.append(
            {
                "name": repo.get("name") or "",
                "language": repo.get("language") or "",
                "description": guard_document("description", str(repo.get("description") or ""), 500),
                "readme": guard_document("readme", str(repo.get("readme") or ""), 2000),
            }
        )
    return {"repos": repos}


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


def _resources(gaps: list[str]) -> dict[str, list]:
    found: dict[str, list] = {}
    for skill in gaps:
        try:
            result = call_tool("tavily_search", {"query": skill}, "action_planner")
            found[skill] = _search_rows(list(result.get("results") or [])[:5])
        except McpError:
            logger.error("resource search failed")
            found[skill] = []
    return found


def _search_rows(rows: list) -> list[dict]:
    safe: list[dict] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        safe.append(
            {
                "title": guard_document("search", str(item.get("title") or ""), 300),
                "url": str(item.get("url") or "")[:300],
                "content": guard_document("search", str(item.get("content") or ""), 500),
            }
        )
    return safe


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
