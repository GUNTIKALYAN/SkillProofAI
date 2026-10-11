import logging
import time

from pydantic import ValidationError

from app.agents.trace import write_step
from app.llm.complete import LlmError, complete_json
from app.mcp_client import McpError, call_tool
from app.schemas.agents import ExperienceParse
from app.services.cache import CacheError
from app.services.experience_checks import check_entries

logger = logging.getLogger(__name__)

_GITHUB_TTL = 6 * 60 * 60


def github_fetch(state: dict) -> dict:
    started = time.perf_counter()
    username = str(state.get("github_username") or "")
    payload = {"username": username}
    key = f"github:user:{username}"
    try:
        cached = _cache_get(key)
        if cached is not None:
            write_step("github_fetch", 1, None, payload, {"repos": len(cached.get("repos") or [])}, 0, started, None)
            return {"github_evidence": cached}
        raw = call_tool("github", "list_public_repos", {"username": username}, "github_fetch")
        evidence = {"repos": _repos(raw)}
        _cache_set(key, evidence)
        write_step("github_fetch", 1, None, payload, evidence, 0, started, None)
        return {"github_evidence": evidence}
    except McpError as exc:
        logger.error("github fetch failed error=%s", type(exc).__name__)
        write_step("github_fetch", 1, None, payload, None, 0, started, type(exc).__name__)
        return {"github_evidence": {"repos": []}, "github_error": "GitHub evidence is unavailable"}


def experience_check(state: dict) -> dict:
    started = time.perf_counter()
    text = "\n".join(str(line) for line in (state.get("resume") or {}).get("experience") or [])
    payload = {"chars": len(text)}
    try:
        parsed, tokens = complete_json("experience_check", {"experience_text": text}, ExperienceParse)
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


def unsupported_flags(state: dict) -> list[dict]:
    entries = (state.get("experience") or {}).get("entries") or []
    evidence = _evidence(state)
    flags: list[dict] = []
    for entry in entries:
        for part in _parts(entry.get("bullets") or []):
            found = call_tool("skillgraph", "canonicalize_skill", {"text": part}, "skill_audit")
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


def _companies(parsed: ExperienceParse) -> list[dict]:
    found: list[dict] = []
    seen: set[str] = set()
    for entry in parsed.entries:
        name = entry.company.strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        result = call_tool("verify", "check_company", {"name": name}, "experience_check")
        status = result.get("status")
        if status not in {"found", "not_found", "ambiguous", "skipped"}:
            status = "skipped"
        found.append({"name": name, "status": status, "confidence": result.get("confidence")})
    return found


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


def _cache_get(key: str) -> dict | None:
    from app.mcp_client.context import get_run

    ctx = get_run()
    if ctx is None:
        return None
    try:
        return ctx.cache.get(key)
    except CacheError:
        logger.error("github cache read failed")
        return None


def _cache_set(key: str, value: dict) -> None:
    from app.mcp_client.context import get_run

    ctx = get_run()
    if ctx is None:
        return
    try:
        ctx.cache.set(key, value, _GITHUB_TTL)
    except CacheError:
        logger.error("github cache write failed")
