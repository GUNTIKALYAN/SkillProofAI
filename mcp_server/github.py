import logging
import re

import httpx

logger = logging.getLogger(__name__)

_USERNAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
_MAX_REPOS = 20
_REPOS_URL = "https://api.github.com/users/{username}/repos"
GITHUB_TIMEOUT = 20.0


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


def list_public_repos(username: str, github_token: str) -> dict:
    cleaned = valid_username(username)
    if cleaned is None:
        return {"repositories": []}
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "skillproof",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = github_token.strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = httpx.get(
            _REPOS_URL.format(username=cleaned),
            params={"per_page": 20, "sort": "updated", "type": "owner"},
            headers=headers,
            timeout=GITHUB_TIMEOUT,
        )
        if response.status_code == 404:
            return {"repositories": []}
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        logger.error("github repos failed")
        return {"repositories": []}
    found = public_repos(payload)
    logger.info("github repos count=%s", len(found["repositories"]))
    return found
