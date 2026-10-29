import os
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, validator


def data_directory() -> Path:
    """Return an OS user-data location, always outside the source repository."""
    override = os.environ.get("PROJECT_PROGRESS_DASHBOARD_DATA_DIR")
    if override:
        target = Path(override).expanduser()
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        target = base / "ProjectProgressDashboard"
    elif os.sys.platform == "darwin":
        target = Path.home() / "Library" / "Application Support" / "ProjectProgressDashboard"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        target = base / "ProjectProgressDashboard"
    target.mkdir(parents=True, exist_ok=True)
    return target


DB_PATH = data_directory() / "dashboard.sqlite3"
app = FastAPI(title="Project Progress Dashboard", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type"],
)


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    try:
        yield db
        db.commit()
    finally:
        db.close()


def initialize_database() -> None:
    with connection() as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                folder_path TEXT NOT NULL,
                planned_start TEXT NOT NULL,
                planned_end TEXT NOT NULL,
                color TEXT NOT NULL,
                archived INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )


class ProjectInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    folder_path: str = Field(..., min_length=1, max_length=2000)
    planned_start: date
    planned_end: date

    @validator("name", "folder_path")
    def strip_required(cls, value: str) -> str:
        result = value.strip()
        if not result:
            raise ValueError("must not be blank")
        return result

    @validator("planned_end")
    def valid_range(cls, value: date, values: dict) -> date:
        start = values.get("planned_start")
        if start and value < start:
            raise ValueError("planned_end must be on or after planned_start")
        return value


def project_dict(row: sqlite3.Row) -> dict:
    result = dict(row)
    result["archived"] = bool(result["archived"])
    return result


@app.on_event("startup")
def startup() -> None:
    initialize_database()


@app.middleware("http")
async def local_host_guard(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        host = request.headers.get("host", "").split(":", 1)[0].lower()
        origin = request.headers.get("origin")
        if host not in {"127.0.0.1", "localhost", "[::1]"}:
            return Response(status_code=403, content="Local requests only")
        if origin:
            from urllib.parse import urlparse

            origin_host = (urlparse(origin).hostname or "").lower()
            if origin_host not in {"127.0.0.1", "localhost", "::1"}:
                return Response(status_code=403, content="Local requests only")
    return await call_next(request)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "project-progress-dashboard-api"}


@app.get("/api/projects")
def list_projects(include_archived: bool = False) -> list[dict]:
    with connection() as db:
        rows = db.execute(
            "SELECT * FROM projects WHERE archived = ? OR ? = 1 ORDER BY planned_start, name",
            (0, int(include_archived)),
        ).fetchall()
    return [project_dict(row) for row in rows]


@app.post("/api/projects", status_code=201)
def create_project(payload: ProjectInput) -> dict:
    project_id = str(uuid4())
    color = "#" + ("%06x" % (int(project_id.replace("-", "")[:6], 16) & 0xFFFFFF))
    with connection() as db:
        db.execute(
            "INSERT INTO projects (id, name, folder_path, planned_start, planned_end, color) VALUES (?, ?, ?, ?, ?, ?)",
            (project_id, payload.name, payload.folder_path, payload.planned_start.isoformat(), payload.planned_end.isoformat(), color),
        )
        row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return project_dict(row)


@app.put("/api/projects/{project_id}")
def update_project(project_id: str, payload: ProjectInput) -> dict:
    with connection() as db:
        existing = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Project not found")
        db.execute(
            "UPDATE projects SET name = ?, folder_path = ?, planned_start = ?, planned_end = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (payload.name, payload.folder_path, payload.planned_start.isoformat(), payload.planned_end.isoformat(), project_id),
        )
        row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return project_dict(row)


@app.put("/api/projects/{project_id}/archive")
def set_archived(project_id: str, archived: bool) -> dict:
    with connection() as db:
        cursor = db.execute(
            "UPDATE projects SET archived = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (int(archived), project_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Project not found")
        row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return project_dict(row)


@app.get("/api/projects/{project_id}")
def get_project(project_id: str) -> dict:
    with connection() as db:
        row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project_dict(row)


static_dir = Path(__file__).resolve().parents[2] / "dist"
if static_dir.is_dir():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
