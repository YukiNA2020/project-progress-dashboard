"""Parse and capture endpoints."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from .. import config_store, service
from ..parsing import llm, local_rules
from ..schemas import CaptureInput, ParseInput, as_dict

router = APIRouter(prefix="/api")


@router.post("/parse")
def parse(payload: ParseInput) -> Dict[str, Any]:
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="没有可解析的文本")

    state = service.bootstrap()
    runtime = config_store.runtime()

    if runtime.get("enabled") and runtime.get("api_key_set") and runtime.get("model"):
        return llm.parse_with_model(text, state["customers"], state["phases"], runtime)

    return local_rules.parse(text, state["customers"], state["phases"])


@router.post("/captures")
def capture(payload: CaptureInput) -> Dict[str, Any]:
    """Store what was typed, what the parser produced, and what the user kept."""
    data = as_dict(payload)
    applied = data.get("applied") or {}
    project_id = data.get("project_id")

    if project_id:
        try:
            service.patch_project(project_id, applied)
        except KeyError:
            raise HTTPException(status_code=404, detail="项目不存在")

    capture_id = service.record_capture(
        raw_text=data.get("raw_text") or "",
        project_id=project_id,
        parser=data.get("parser") or "local",
        parsed=data.get("parsed") or {},
        applied=applied,
    )
    return {"capture_id": capture_id, "project_id": project_id}


@router.get("/captures")
def list_captures(project_id: str = "", limit: int = 50) -> Dict[str, Any]:
    from ..db import connection
    import json

    with connection() as db:
        if project_id:
            rows = db.execute(
                "SELECT id, raw_text, project_id, parser, created_at FROM captures"
                " WHERE project_id = ? ORDER BY created_at DESC LIMIT ?",
                (project_id, limit)).fetchall()
        else:
            rows = db.execute(
                "SELECT id, raw_text, project_id, parser, created_at FROM captures"
                " ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return {"items": [dict(row) for row in rows]}
