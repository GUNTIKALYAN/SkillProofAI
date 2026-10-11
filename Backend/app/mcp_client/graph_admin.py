import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class GraphAdminError(Exception):
    pass


def add_skill(name: str) -> bool:
    return _post("/admin/skill", {"name": name})


def add_alias(name: str, canonical: str) -> bool:
    return _post("/admin/alias", {"name": name, "canonical": canonical})


def _post(path: str, body: dict) -> bool:
    settings = get_settings()
    base = settings.skillgraph_url.removesuffix("/mcp").rstrip("/")
    try:
        response = httpx.post(
            f"{base}{path}",
            json=body,
            headers={"Authorization": f"Bearer {settings.skillgraph_token}"},
            timeout=10,
        )
    except httpx.HTTPError as exc:
        logger.error("skill graph admin failed error=%s", type(exc).__name__)
        raise GraphAdminError("Skill graph is unavailable") from exc
    if response.status_code == 404:
        return False
    if response.status_code != 200:
        logger.error("skill graph admin failed status=%s", response.status_code)
        raise GraphAdminError("Skill graph is unavailable")
    return True
