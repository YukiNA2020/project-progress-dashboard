"""Application entry point.

Binds loopback only, serves the single-file frontend and its two scripts, and
rejects state-changing requests that did not come from the local page.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .db import initialize_database, seed_defaults
from .routes import data, parse, provider, system

ROOT = Path(__file__).resolve().parents[1]
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}

app = FastAPI(title="业务项目看板", version=system.VERSION, docs_url="/api/docs",
              openapi_url="/api/openapi.json")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("bizboard")

app.include_router(data.router)
app.include_router(parse.router)
app.include_router(provider.router)
app.include_router(system.router)


@app.on_event("startup")
def startup() -> None:
    report = initialize_database()
    seed_defaults()
    if report.get("recovered"):
        logger.warning("数据库损坏，已重命名旧文件并新建：%s", report["path"])
    logger.info("数据目录：%s", report["path"])


@app.middleware("http")
async def local_only_guard(request: Request, call_next):
    """Block cross-site writes.

    The server has no auth because it only listens on loopback. That still
    leaves a hole: any web page the user visits could POST to 127.0.0.1. The
    Host/Origin check closes it.
    """
    if request.url.path.startswith("/api/") and request.method in {
            "POST", "PUT", "PATCH", "DELETE"}:
        host = request.headers.get("host", "").split(":")[0].lower()
        if host and host not in LOCAL_HOSTS:
            return Response(status_code=403, content="只接受本机请求")
        origin = request.headers.get("origin")
        if origin:
            origin_host = (urlparse(origin).hostname or "").lower()
            if origin_host and origin_host not in LOCAL_HOSTS:
                return Response(status_code=403, content="只接受本机请求")
    return await call_next(request)


@app.exception_handler(Exception)
async def unhandled(request: Request, error: Exception):  # noqa: ANN001
    logger.exception("未处理的错误：%s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={
        "error": {"code": "INTERNAL", "message": "服务端出错了，看窗口里的日志"}})


@app.get("/")
def index() -> FileResponse:
    return FileResponse(str(ROOT / "index.html"), media_type="text/html; charset=utf-8")


@app.get("/favicon.ico")
def favicon() -> Response:
    return Response(status_code=204)


assets = ROOT / "assets"
if assets.is_dir():
    app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")
