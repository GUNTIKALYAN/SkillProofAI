import asyncio
import logging
from collections.abc import Callable
from typing import ClassVar

from arq.connections import RedisSettings

from app.agents.skills.loader import SkillError, load_skills, require_listed_tools
from app.config import get_settings
from app.logging_config import configure_logging
from app.mcp_client.catalog import KNOWN_TOOLS
from app.mcp_client.transport import probe_servers

logger = logging.getLogger(__name__)


async def run_analysis(ctx, analysis_id: str) -> None:
    del ctx
    from app.services.runner import execute_analysis

    await asyncio.to_thread(execute_analysis, analysis_id)


async def startup(ctx) -> None:
    del ctx
    configure_logging("worker")
    settings = get_settings()
    try:
        skills = load_skills()
        require_listed_tools(skills, KNOWN_TOOLS)
    except SkillError as exc:
        raise RuntimeError(f"Startup failed. {exc}") from exc
    if settings.mcp_probe:
        await asyncio.to_thread(probe_servers, skills)
    logger.info("worker started")


class WorkerSettings:
    functions: ClassVar[list] = [run_analysis]
    on_startup: ClassVar[Callable] = startup
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
