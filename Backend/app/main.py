from fastapi import FastAPI
from app.api.routes import router

app = FastAPI(title="SKILL PROOF API")

app.include_router(router)