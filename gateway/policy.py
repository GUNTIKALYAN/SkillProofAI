from dataclasses import dataclass

PUBLIC = "public"
USER = "user"
ADMIN = "admin"

AUTH_PER_MINUTE = 5
AUTH_WINDOW_SECONDS = 60
ANALYZE_PER_HOUR = 5
ANALYZE_WINDOW_SECONDS = 60 * 60
CHAT_PER_MINUTE = 20
CHAT_WINDOW_SECONDS = 60
MAX_BODY_BYTES = 5 * 1024 * 1024

LIMITS: dict[str, tuple[int, int]] = {
    "auth": (AUTH_PER_MINUTE, AUTH_WINDOW_SECONDS),
    "analyze": (ANALYZE_PER_HOUR, ANALYZE_WINDOW_SECONDS),
    "chat": (CHAT_PER_MINUTE, CHAT_WINDOW_SECONDS),
}


@dataclass(frozen=True)
class Rule:
    access: str
    limit: str | None


# Exact routes win over the prefixes below. Anything under /api that misses both is denied.
_EXACT: dict[tuple[str, str], Rule] = {
    ("POST", "/api/auth/signup"): Rule(PUBLIC, "auth"),
    ("POST", "/api/auth/login"): Rule(PUBLIC, "auth"),
    ("POST", "/api/auth/refresh"): Rule(PUBLIC, "auth"),
    ("POST", "/api/auth/logout"): Rule(PUBLIC, "auth"),
    ("GET", "/api/auth/me"): Rule(USER, None),
    ("DELETE", "/api/auth/me"): Rule(USER, None),
    ("POST", "/api/analyses"): Rule(USER, "analyze"),
}


def match(method: str, path: str) -> Rule | None:
    exact = _EXACT.get((method.upper(), path))
    if exact is not None:
        return exact
    if path == "/api/analyses" or path.startswith("/api/analyses/"):
        return Rule(USER, None)
    if path == "/api/compare" or path.startswith("/api/compare/"):
        return Rule(USER, None)
    if path == "/api/chat" or path.startswith("/api/chat/"):
        return Rule(USER, "chat")
    if path == "/api/admin" or path.startswith("/api/admin/"):
        return Rule(ADMIN, None)
    return None
