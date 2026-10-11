import re

_USERNAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
_MAX_REPOS = 20


def valid_username(username: str) -> str | None:
    cleaned = username.strip()
    if _USERNAME.fullmatch(cleaned) is None:
        return None
    return cleaned


def public_repos(payload: object) -> dict:
    if not isinstance(payload, list):
        return {"repositories": []}
    repos: list[dict] = []
    for item in payload[:_MAX_REPOS]:
        if not isinstance(item, dict) or item.get("private") is True:
            continue
        name = str(item.get("name") or "")[:120]
        if not name:
            continue
        repos.append(
            {
                "name": name,
                "language": str(item.get("language") or "")[:40],
                "description": str(item.get("description") or "")[:200],
            }
        )
    return {"repositories": repos}
