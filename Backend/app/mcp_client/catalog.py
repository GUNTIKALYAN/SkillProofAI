KNOWN_TOOLS: dict[str, set[str]] = {
    "skillgraph": {
        "canonicalize_skill",
        "score_match",
        "audit_skills",
        "related_skills",
        "explain_skill",
        "what_if_learn",
    },
    "github": {"search_repositories"},
    "tavily": {"tavily_search"},
    "verify": {"check_company"},
}

SERVER_TIMEOUTS = {
    "skillgraph": 10.0,
    "github": 20.0,
    "tavily": 15.0,
    "verify": 15.0,
}
