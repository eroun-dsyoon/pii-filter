"""PII Filter Service - FastAPI Application"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from .api.routes import router

app = FastAPI(
    title="PII Filter Service",
    description="개인정보 필터링 서비스 - 한국 개인정보 검출 및 우회 탐지",
    version="1.0.0",
)

app.include_router(router, prefix="/api")

# Static files
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def index():
    return FileResponse(str(static_dir / "index.html"))


@app.get("/admin")
async def admin():
    return FileResponse(str(static_dir / "admin.html"))
