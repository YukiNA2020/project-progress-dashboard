"""Local API routes.

Every route is intended for the loopback browser session that FastAPI serves.
State-changing routes are guarded by the Host/Origin check in ``main``.
"""

from __future__ import annotations

import threading
from typing import Dict, List, Optional
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query

from . import config_store, daily, service, system
from .db import connection
from .providers import client
from .schemas import DecisionInput, ProjectInput, ProviderInput, StartupInput
from .settings import data_directory, log_path

router = APIRouter(prefix="/api")

_scan_lock = threading.Lock()
APP_VERSION = "0.5.0"


def _project_dict(row) -> dict:
    result = dict(row)
    result["archived"] = bool(result["archived"])
    return result


def _state_summaries() -> Dict[str, dict]:
    with connection() as db:
        rows = db.execute("SELECT * FROM project_state").fetchall()
    summaries: Dict[str, dict] = {}
    for row in rows:
        data = dict(row)
        summaries[data["project_id"]] = {
            "status": data["status"],
            "reason": data["reason"],
            "current_phase": data["candidate_phase"] or data["accepted_phase"],
            "current_phase_ordinal": data["candidate_phase_ordinal"]
            if data["candidate_phase_ordinal"] is not None
            else data["accepted_phase_ordinal"],
            "accepted_phase": data["accepted_phase"],
            "testing": bool(data["candidate_testing"]),
            "newest_record_date": data["newest_record_date"],
            "scan_error": data["scan_error"],
            "scanned_at": data["scanned_at"],
            "last_success_at": data["last_success_at"],
            "files_scanned": data["files_scanned"],
            "basis": data["current_basis"],
            "model_status": data.get("model_status") or "disabled",
            "last_failure_at": data.get("last_failure_at"),
        }
    return summaries


EMPTY_STATE = {
    "status": "never",
    "reason": "",
    "current_phase": None,
    "current_phase_ordinal": None,
    "accepted_phase": None,
    "testing": False,
    "newest_record_date": None,
    "scan_error": None,
    "scanned_at": None,
    "last_success_at": None,
    "files_scanned": 0,
    "basis": "none",
    "model_status": "disabled",
    "last_failure_at": None,
}


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "project-progress-dashboard-api",
        "phase": 4,
        "scanner": "read-only-markdown",
        "model": "openai-compatible + anthropic",
        "version": APP_VERSION,
    }


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


@router.get("/projects")
def list_projects(include_archived: bool = False) -> List[dict]:
    with connection() as db:
        rows = db.execute(
            "SELECT * FROM projects WHERE archived = ? OR ? = 1 ORDER BY planned_start, name",
            (0, int(include_archived)),
        ).fetchall()
    summaries = _state_summaries()
    projects = []
    for row in rows:
        project = _project_dict(row)
        project["state"] = summaries.get(project["id"], dict(EMPTY_STATE))
        projects.append(project)
    return projects


@router.post("/projects", status_code=201)
def create_project(payload: ProjectInput) -> dict:
    project_id = str(uuid4())
    color = "#" + ("%06x" % (int(project_id.replace("-", "")[:6], 16) & 0xFFFFFF))
    with connection() as db:
        db.execute(
            "INSERT INTO projects (id, name, folder_path, planned_start, planned_end, color) VALUES (?, ?, ?, ?, ?, ?)",
            (
                project_id,
                payload.name,
                payload.folder_path,
                payload.planned_start.isoformat(),
                payload.planned_end.isoformat(),
                color,
            ),
        )
        row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    project = _project_dict(row)
    project["state"] = dict(EMPTY_STATE)
    return project


@router.put("/projects/{project_id}")
def update_project(project_id: str, payload: ProjectInput) -> dict:
    with connection() as db:
        existing = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="项目不存在")
        db.execute(
            "UPDATE projects SET name = ?, folder_path = ?, planned_start = ?, planned_end = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (
                payload.name,
                payload.folder_path,
                payload.planned_start.isoformat(),
                payload.planned_end.isoformat(),
                project_id,
            ),
        )
        row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return _project_dict(row)


@router.put("/projects/{project_id}/archive")
def set_archived(project_id: str, archived: bool) -> dict:
    with connection() as db:
        cursor = db.execute(
            "UPDATE projects SET archived = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (int(archived), project_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="项目不存在")
        row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return _project_dict(row)


@router.get("/projects/{project_id}")
def get_project(project_id: str) -> dict:
    with connection() as db:
        row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    project = _project_dict(row)
    project["state"] = _state_summaries().get(project_id, dict(EMPTY_STATE))
    return project


@router.get("/projects/{project_id}/detail")
def get_project_detail(project_id: str) -> dict:
    detail = service.project_detail(project_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    if detail["state"] is not None:
        detail["state"]["candidate_testing"] = bool(detail["state"]["candidate_testing"])
    return detail


@router.post("/projects/{project_id}/open-folder")
def open_project_folder(project_id: str) -> dict:
    with connection() as db:
        row = db.execute("SELECT folder_path FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    try:
        return system.open_folder(row["folder_path"])
    except system.OpenFolderError as error:
        raise HTTPException(status_code=400, detail=str(error))


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------


@router.post("/scan")
def trigger_scan(
    project_ids: Optional[List[str]] = Query(default=None),
    use_model: Optional[bool] = Query(default=None),
) -> dict:
    if not _scan_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="已有巡检正在进行，请稍候")
    try:
        return service.scan_all(project_ids, use_model=use_model)
    finally:
        _scan_lock.release()


@router.get("/scan/latest")
def get_latest_scan() -> dict:
    run = service.latest_run()
    return {"run": run}


# ---------------------------------------------------------------------------
# Model provider
# ---------------------------------------------------------------------------


def _provider_payload(payload: Optional[ProviderInput], saved: Dict) -> Dict:
    """Merge unsaved form values over the stored configuration for a test call."""
    merged = dict(saved)
    merged["effective_base_url"] = saved.get("effective_base_url") or ""
    if payload is None:
        return merged

    provider = (payload.provider or saved["provider"]).strip().lower()
    if provider not in config_store.PROVIDERS:
        raise HTTPException(status_code=400, detail="未知的模型服务商")
    merged["provider"] = provider

    base_url = payload.base_url if payload.base_url is not None else saved["base_url"]
    base_url = (base_url or "").strip().rstrip("/")
    if base_url:
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise HTTPException(status_code=400, detail="接口地址需要以 http:// 或 https:// 开头")
    merged["base_url"] = base_url
    merged["effective_base_url"] = base_url or config_store.PROVIDERS[provider]["default_base_url"]

    merged["model"] = (payload.model if payload.model is not None else saved["model"]).strip()
    if payload.json_mode is not None:
        merged["json_mode"] = payload.json_mode
    if payload.api_key:
        merged["transient_key"] = payload.api_key.strip()
    return merged


@router.get("/provider")
def get_provider() -> dict:
    return config_store.get_settings()


@router.put("/provider")
def put_provider(payload: ProviderInput) -> dict:
    try:
        return config_store.save_settings(payload.dict(exclude_unset=True))
    except config_store.ConfigError as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.post("/provider/test")
def test_provider(payload: Optional[ProviderInput] = None) -> dict:
    saved = config_store.get_settings()
    merged = _provider_payload(payload, saved)
    if not merged.get("model"):
        raise HTTPException(status_code=400, detail="请先填写模型名再测试连接")
    if not (merged.get("transient_key") or saved.get("api_key_set")):
        raise HTTPException(status_code=400, detail="请先填写 API 密钥再测试连接")

    ok, message, elapsed = client.ping(merged)
    # Only remember the result when the tested values are the stored ones.
    if (
        merged["provider"] == saved["provider"]
        and merged["model"] == saved["model"]
        and (merged.get("base_url") or "") == (saved.get("base_url") or "")
    ):
        config_store.record_test(ok, message)
    return {
        "ok": ok,
        "message": message,
        "latency_ms": elapsed,
        "provider": merged["provider"],
        "model": merged["model"],
        "endpoint_host": urlparse(merged.get("effective_base_url") or "").hostname or "",
    }


# ---------------------------------------------------------------------------
# Pending confirmations
# ---------------------------------------------------------------------------


@router.post("/pending/{pending_id}/decision")
def decide(pending_id: int, payload: DecisionInput) -> dict:
    try:
        return service.decide_pending(pending_id, payload.decision)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error))


# ---------------------------------------------------------------------------
# System, login startup, and the daily automatic scan
# ---------------------------------------------------------------------------


@router.get("/system")
def get_system() -> dict:
    return {
        "version": APP_VERSION,
        "platform": system.platform_id(),
        "platform_label": system.platform_label(),
        "startup": system.startup_status(),
        "daily": daily.status(),
        "paths": {
            "data": str(data_directory()),
            "log": str(log_path()),
        },
        "frontend_ready": (system.repository_directory() / "dist" / "index.html").is_file(),
    }


@router.post("/startup")
def set_startup(payload: StartupInput) -> dict:
    try:
        if payload.enabled:
            return system.enable_startup()
        return system.disable_startup()
    except system.StartupError as error:
        raise HTTPException(status_code=400, detail=str(error))
