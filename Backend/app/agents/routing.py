MAX_STEPS = 8
_GAPS = {"partial", "missing"}


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
