import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.api.routes import router

app = FastAPI(title="SKILL PROOF API")

# -------------------------
# API ROUTES
# -------------------------
app.include_router(router, prefix="/api")

# -------------------------
# PATH RESOLUTION
# -------------------------
# main.py -> Backend/app/main.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Go up: app/ -> Backend/ -> project-root/
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", ".."))

FRONTEND_DIR = os.path.join(PROJECT_ROOT, "Frontend")
STATIC_DIR = os.path.join(FRONTEND_DIR, "static")

# -------------------------
# STATIC FILES
# -------------------------
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# -------------------------
# SERVE FRONTEND
# -------------------------
@app.get("/")
def serve_frontend():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    return FileResponse(index_path)
