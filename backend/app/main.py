"""Local application entry point.

Runs a loopback-only web app: FastAPI for the local API, and the built Vite
assets when ``dist/`` exists.

When the login-startup launcher sets ``PROJECT_PROGRESS_DASHBOARD_AUTO_SCAN=1``,
the first start of the day also runs the automatic scan. The daily table makes
that at most once per local calendar day, even if the app is started twice.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .db import initialize_database
from .routes import router

AUTO_SCAN_ENV = "PROJECT_PROGRESS_DASHBOARD_AUTO_SCAN"

app = FastAPI(title="Project Progress Dashboard", version="0.5.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type"],
)
app.include_router(router)

LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1"}


def _run_daily_scan() -> None:
    from . import daily

    logger = logging.getLogger("dashboard.daily")
    try:
        result = daily.run_if_due()
    except Exception:  # noqa: BLE001 - a background scan must not kill the server
        logger.exception("每日自动巡检失败")
        return
    logger.info("每日自动巡检：%s（%s）", result.get("reason"), result.get("date"))


@app.on_event("startup")
def startup() -> None:
    initialize_database()
    if os.environ.get(AUTO_SCAN_ENV) == "1":
        threading.Thread(target=_run_daily_scan, name="daily-scan", daemon=True).start()



@app.middleware("http")
async def local_host_guard(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        host = request.headers.get("host", "").split(":", 1)[0].lower()
        if host not in LOCAL_HOSTS:
            return Response(status_code=403, content="Local requests only")
        origin = request.headers.get("origin")
        if origin:
            origin_host = (urlparse(origin).hostname or "").lower()
            if origin_host not in LOCAL_HOSTS:
                return Response(status_code=403, content="Local requests only")
    return await call_next(request)


static_dir = Path(__file__).resolve().parents[2] / "dist"
if static_dir.is_dir():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
