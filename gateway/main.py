import json
import logging
import os
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import httpx
import jwt
import redis
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from jwt.exceptions import PyJWTError

from policy import ADMIN, LIMITS, MAX_BODY_BYTES, PUBLIC, Rule, match

logger = logging.getLogger(__name__)

_REQUIRED = ("JWT_SECRET", "REDIS_URL", "BACKEND_URL")
_MIN_SECRET = 32
_PROXY_TIMEOUT_SECONDS = 120
_HOP = {
    "host",
    "content-length",
    "connection",
    "keep-alive",
    "transfer-encoding",
    "te",
    "trailer",
    "upgrade",
    "accept-encoding",
}
_RESPONSE_SKIP = {"content-encoding", "transfer-encoding", "content-length", "connection"}


@dataclass(frozen=True)
class Settings:
    jwt_secret: str
    redis_url: str
    backend_url: str
    frontend_dir: Path


def default_frontend() -> Path:
    configured = os.environ.get("FRONTEND_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[1] / "Frontend"


def load_settings() -> Settings:
    missing = [name for name in _REQUIRED if not os.environ.get(name)]
    if missing:
        listed = ", ".join(missing)
        raise RuntimeError(
            f"Startup failed. Missing or invalid settings: {listed}. "
            "Copy .env.example to .env and set them."
        )
    secret = os.environ["JWT_SECRET"]
    if len(secret) < _MIN_SECRET:
        raise RuntimeError("Startup failed. JWT_SECRET must be at least 32 characters.")
    frontend = default_frontend()
    _require_frontend(frontend)
    return Settings(
        jwt_secret=secret,
        redis_url=os.environ["REDIS_URL"],
        backend_url=os.environ["BACKEND_URL"].rstrip("/"),
        frontend_dir=frontend,
    )


def create_app(
    settings: Settings | None = None,
    redis_client: redis.Redis | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> FastAPI:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    resolved = settings.frontend_dir if settings is not None else default_frontend()
    _require_frontend(resolved)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings or load_settings()
        app.state.redis = redis_client or redis.Redis.from_url(
            app.state.settings.redis_url,
            socket_timeout=2,
            socket_connect_timeout=2,
        )
        app.state.http = http_client or httpx.AsyncClient(timeout=_PROXY_TIMEOUT_SECONDS)
        app.state.own_http = http_client is None
        try:
            yield
        finally:
            if app.state.own_http:
                await app.state.http.aclose()

    app = FastAPI(title="SkillProof gateway", lifespan=lifespan)
    app.middleware("http")(log_request)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(resolved / "auth.html")

    @app.api_route(
        "/api/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    )
    async def proxy(request: Request) -> Response:
        rule = match(request.method, request.url.path)
        if rule is None:
            raise HTTPException(status_code=404, detail="Not found")
        body = await _read_body(request)
        _authorize(request, rule)
        if rule.limit is not None:
            _limit(request, rule.limit)
        return await _forward(request, body)

    @app.get("/{page}")
    def page(page: str) -> FileResponse:
        if "/" in page or "\\" in page or not page.endswith(".html"):
            raise HTTPException(status_code=404, detail="Not found")
        path = (resolved / page).resolve()
        if path.parent != resolved.resolve() or not path.is_file():
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(path)

    app.mount("/css", StaticFiles(directory=resolved / "css"), name="css")
    app.mount("/js", StaticFiles(directory=resolved / "js"), name="js")
    return app


async def log_request(request: Request, call_next):
    request.state.request_id = _request_id(request)
    request.state.user_id = None
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "%s",
        json.dumps(
            {
                "request_id": request.state.request_id,
                "method": request.method,
                "route": request.url.path,
                "status": response.status_code,
                "ms": elapsed_ms,
                "user_id": request.state.user_id,
            }
        ),
    )
    response.headers["X-Request-ID"] = request.state.request_id
    return response


def _require_frontend(path: Path) -> None:
    if not (path / "css").is_dir() or not (path / "js").is_dir() or not (path / "index.html").is_file():
        raise RuntimeError(f"Startup failed. Frontend directory is incomplete: {path}")


def _request_id(request: Request) -> str:
    raw = request.headers.get("x-request-id", "")
    cleaned = "".join(ch for ch in raw if ch.isalnum() or ch in "-")[:64]
    return cleaned or str(uuid.uuid4())


def _authorize(request: Request, rule: Rule) -> None:
    if rule.access == PUBLIC:
        return
    payload = _payload(request)
    request.state.user_id = str(payload["sub"])
    if rule.access == ADMIN and payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not allowed")


def _payload(request: Request) -> dict:
    header = request.headers.get("authorization")
    if header is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Not authenticated")
    settings: Settings = request.app.state.settings
    try:
        payload = jwt.decode(token.strip(), settings.jwt_secret, algorithms=["HS256"])
    except PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Not authenticated") from exc
    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return payload


def _limit(request: Request, name: str) -> None:
    limit, window = LIMITS[name]
    identity = _client_ip(request) if name == "auth" else request.state.user_id
    key = f"rl:{name}:{identity}"
    client = request.app.state.redis
    try:
        pipe = client.pipeline()
        pipe.incr(key)
        pipe.expire(key, window, nx=True)
        count, _set = pipe.execute()
        if int(count) <= limit:
            return
        retry = int(client.ttl(key))
    except redis.RedisError as exc:
        logger.error("rate limiter unavailable limit=%s", name)
        raise HTTPException(status_code=503, detail="Rate limiter is unavailable") from exc
    raise HTTPException(
        status_code=429,
        detail="Too many requests",
        headers={"Retry-After": str(max(retry, 1))},
    )


def _client_ip(request: Request) -> str:
    if request.client is None:
        return "unknown"
    return request.client.host


async def _read_body(request: Request) -> bytes:
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Request body is too large")
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Request body is too large")
    return body


async def _forward(request: Request, body: bytes) -> Response:
    settings: Settings = request.app.state.settings
    headers = {
        key: value for key, value in request.headers.items() if key.lower() not in _HOP
    }
    headers["x-request-id"] = request.state.request_id
    try:
        upstream = await request.app.state.http.request(
            request.method,
            settings.backend_url + request.url.path,
            params=request.query_params,
            content=body,
            headers=headers,
        )
    except httpx.HTTPError as exc:
        logger.error("backend unreachable error=%s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Backend is unavailable") from exc
    return _downstream(upstream)


def _downstream(upstream: httpx.Response) -> Response:
    response = Response(content=upstream.content, status_code=upstream.status_code)
    for key, value in upstream.headers.multi_items():
        if key.lower() in _RESPONSE_SKIP:
            continue
        if key.lower() == "set-cookie":
            response.headers.append(key, value)
        else:
            response.headers[key] = value
    return response


app = create_app()
