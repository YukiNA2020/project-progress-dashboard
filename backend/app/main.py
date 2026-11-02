"""Local application entry point.

Runs a loopback-only web app: FastAPI for the local API, and the built Vite
assets when ``dist/`` exists.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .db import initialize_database
from .routes import router

app = FastAPI(title="Project Progress Dashboard", version="0.4.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type"],
)
app.include_router(router)

LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1"}


@app.on_event("startup")
def startup() -> None:
    initialize_database()


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
