import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.api.routes import router

app = FastAPI(title="SKILL PROOF API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# API ROUTES
# -------------------------
app.include_router(router, prefix="/api")

# -------------------------
# PATH RESOLUTION
# -------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# app/ → Backend/ → project-root/
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", ".."))

FRONTEND_DIR = os.path.join(PROJECT_ROOT, "Frontend")
STATIC_DIR = os.path.join(FRONTEND_DIR, "static")

# -------------------------
# STATIC FILES (SAFE)
# -------------------------
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
else:
    # This prevents pytest / CI crashes
    print(f"⚠️ Static directory not found, skipping mount: {STATIC_DIR}")

# -------------------------
# SERVE FRONTEND (SAFE)
# -------------------------
@app.get("/")
def serve_frontend():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)

    return {
        "status": "ok",
        "message": "Frontend not available in this environment"
    }
