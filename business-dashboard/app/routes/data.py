"""Project / customer / phase endpoints."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from .. import service
from ..db import connection
from ..schemas import CustomerInput, PhasesInput, ProjectPatch, StateInput, as_dict

router = APIRouter(prefix="/api")


@router.get("/bootstrap")
def bootstrap() -> Dict[str, Any]:
    return service.bootstrap()


@router.post("/state")
def replace_state(payload: StateInput) -> Dict[str, Any]:
    return service.replace_state(as_dict(payload))


@router.post("/customers")
def create_customer(payload: CustomerInput) -> Dict[str, Any]:
    data = as_dict(payload)
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="客户名不能为空")
    cid = service.new_id("customer")
    from ..settings import today_str

    with connection() as db:
        db.execute(
            "INSERT INTO customers (id, name, alias, contact, channel, archived,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, 0, ?, ?)",
            (cid, name, data.get("alias") or "", data.get("contact") or "",
             data.get("channel") or "", today_str(), today_str()),
        )
        service.log_change(db, "customer", cid, "create", None, {"name": name})
    return {"id": cid, "name": name, "alias": data.get("alias") or "",
            "contact": data.get("contact") or "", "channel": data.get("channel") or ""}


@router.patch("/customers/{customer_id}")
def update_customer(customer_id: str, payload: CustomerInput) -> Dict[str, Any]:
    data = as_dict(payload)
    with connection() as db:
        row = db.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="客户不存在")
        for key in ("name", "alias", "contact", "channel"):
            if key in data and data[key] is not None:
                db.execute("UPDATE customers SET %s = ? WHERE id = ?" % key,
                           (data[key], customer_id))
        db.execute("UPDATE customers SET updated_at = datetime('now') WHERE id = ?",
                   (customer_id,))
        service.log_change(db, "customer", customer_id, "update",
                           dict(row), {"name": data.get("name")})
    return {"id": customer_id}


@router.delete("/customers/{customer_id}")
def delete_customer(customer_id: str) -> Dict[str, Any]:
    """Soft delete, and detach projects so nothing points at a ghost."""
    with connection() as db:
        row = db.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="客户不存在")
        db.execute("UPDATE customers SET archived = 1 WHERE id = ?", (customer_id,))
        db.execute("UPDATE projects SET customer_id = NULL WHERE customer_id = ?",
                   (customer_id,))
        service.log_change(db, "customer", customer_id, "delete",
                           {"name": row["name"]}, None)
    return {"id": customer_id, "detached_projects": True}


@router.patch("/projects/{project_id}")
def patch_project(project_id: str, payload: ProjectPatch) -> Dict[str, Any]:
    try:
        return service.patch_project(project_id, as_dict(payload))
    except KeyError:
        raise HTTPException(status_code=404, detail="项目不存在")


@router.delete("/projects/{project_id}")
def delete_project(project_id: str) -> Dict[str, Any]:
    if not service.delete_project(project_id):
        raise HTTPException(status_code=404, detail="项目不存在")
    return {"id": project_id, "archived": True}


@router.put("/phases")
def replace_phases(payload: PhasesInput) -> Dict[str, Any]:
    return service.replace_phases(as_dict(payload).get("phases") or [])
