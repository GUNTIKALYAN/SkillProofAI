import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.agents.graph import get_graph
from app.agents.skills.loader import SkillError, load_skills, require_listed_tools
from app.api.admin import router as admin_router
from app.api.analyses import router as analyses_router
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.compare import router as compare_router
from app.config import load_settings
from app.db.session import get_engine
from app.logging_config import configure_logging
from app.mcp_client.catalog import KNOWN_TOOLS
from app.mcp_client.transport import probe_servers
from app.services.metrics import observe_http, render_metrics
from app.services.ready import checks

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", ".."))
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "Frontend")
_PAGES = ("login.html", "signup.html", "app.html", "history.html", "chat.html", "compare.html", "admin.html")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = load_settings()
    _check_database()
    await _check_skills(settings.mcp_probe)
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

    app.middleware("http")(_record_request)

    app.include_router(auth_router, prefix="/api")
    app.include_router(analyses_router, prefix="/api")
    app.include_router(chat_router, prefix="/api")
    app.include_router(compare_router, prefix="/api")
    app.include_router(admin_router, prefix="/api")

    _mount_frontend(app)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/metrics")
    def metrics() -> PlainTextResponse:
        return PlainTextResponse(render_metrics(), media_type="text/plain; version=0.0.4")

    @app.get("/readyz")
    def readyz() -> JSONResponse:
        result = checks()
        ok = all(result.values())
        return JSONResponse(
            {"status": "ok" if ok else "unavailable", "checks": result},
            status_code=200 if ok else 503,
        )

    @app.get("/")
    def serve_frontend() -> RedirectResponse:
        return RedirectResponse(url="/app.html")

    for page_name in _PAGES:
        app.get(f"/{page_name}", name=f"page_{page_name}")(_page_route(page_name))

    return app


async def _record_request(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    started = time.perf_counter()
    response = await call_next(request)
    if request.url.path != "/metrics":
        observe_http(max(int((time.perf_counter() - started) * 1000), 0))
    return response


def _page_route(name: str) -> Callable[[], FileResponse]:
    def serve_page() -> FileResponse:
        return _frontend_file(name)

    return serve_page


def _mount_frontend(app: FastAPI) -> None:
    for folder in ("css", "js"):
        directory = os.path.join(FRONTEND_DIR, folder)
        if os.path.isdir(directory):
            app.mount(f"/{folder}", StaticFiles(directory=directory), name=folder)
        else:
            logger.warning("frontend folder missing folder=%s", folder)


def _frontend_file(name: str) -> FileResponse:
    if name not in _PAGES:
        raise HTTPException(status_code=404, detail="Not found")
    path = os.path.join(FRONTEND_DIR, name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path)


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
        require_listed_tools(skills, KNOWN_TOOLS)
    except SkillError as exc:
        raise RuntimeError(f"Startup failed. {exc}") from exc
    if not probe:
        logger.info("mcp probe skipped")
        return
    await asyncio.to_thread(probe_servers, skills)


app = create_app()
