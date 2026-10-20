import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.agents.graph import get_graph
from app.agents.skills_loader import SkillError, load_skills, require_listed_tools
from app.api.admin import router as admin_router
from app.api.analyses import router as analyses_router
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.compare import router as compare_router
from app.config import load_settings
from app.db import get_engine
from app.mcp_client import KNOWN_TOOLS, probe_server

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    _check_database()
    await _check_skills(settings.mcp_probe)
    get_graph()
    logger.info("application started")
    yield
    logger.info("application stopped")


def create_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO)
    app = FastAPI(title="SkillProof AI", lifespan=lifespan)
    app.include_router(auth_router, prefix="/api")
    app.include_router(analyses_router, prefix="/api")
    app.include_router(chat_router, prefix="/api")
    app.include_router(compare_router, prefix="/api")
    app.include_router(admin_router, prefix="/api")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


def _check_database() -> None:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.error("database check failed error=%s", type(exc).__name__)
        raise RuntimeError("Startup failed. Database is not reachable.") from exc


async def _check_skills(probe: bool) -> None:
    try:
        skills = load_skills()
        require_listed_tools(skills, set(KNOWN_TOOLS))
    except SkillError as exc:
        raise RuntimeError(f"Startup failed. {exc}") from exc
    if not probe:
        logger.info("mcp probe skipped")
        return
    await asyncio.to_thread(probe_server, skills)


app = create_app()
