import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.agents.graph import get_graph
from app.agents.skills.loader import SkillError, load_skills, require_listed_tools
from app.api.admin import router as admin_router
from app.api.analyses import router as analyses_router
from app.api.auth import router as auth_router
from app.config import load_settings
from app.db.session import get_engine
from app.logging_config import configure_logging
from app.mcp_client.catalog import KNOWN_TOOLS
from app.mcp_client.transport import probe_servers

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", ".."))
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "Frontend")
STATIC_DIR = os.path.join(FRONTEND_DIR, "static")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = load_settings()
    _check_database()
    _check_skills(settings.mcp_probe)
    get_graph()
    logger.info("application started")
    yield
    logger.info("application stopped")


def create_app() -> FastAPI:
    configure_logging()
    settings = load_settings()
    app = FastAPI(title="SkillProof AI", lifespan=lifespan)
    origins = [item.strip() for item in settings.cors_origins.split(",") if item.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router, prefix="/api")
    app.include_router(analyses_router, prefix="/api")
    app.include_router(admin_router, prefix="/api")

    if os.path.isdir(STATIC_DIR):
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    else:
        logger.warning("Static directory not found, skipping mount")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/")
    def serve_frontend():
        index_path = os.path.join(FRONTEND_DIR, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {
            "status": "ok",
            "message": "Frontend not available in this environment",
        }

    return app


def _check_database() -> None:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.error("database check failed error=%s", type(exc).__name__)
        raise RuntimeError("Startup failed. Database is not reachable.") from exc


def _check_skills(probe: bool) -> None:
    try:
        skills = load_skills()
        require_listed_tools(skills, KNOWN_TOOLS)
    except SkillError as exc:
        raise RuntimeError(f"Startup failed. {exc}") from exc
    if probe:
        probe_servers(skills)


app = create_app()
