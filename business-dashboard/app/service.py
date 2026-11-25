"""Business logic.

Routes stay thin: they validate and serialise, everything that touches tables
lives here so the same code backs both the granular CRUD endpoints and the
whole-state replace used by the browser.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional
from uuid import uuid4

from .db import connection
from .settings import today_str

ID_PREFIX = {
    "project": "p_",
    "customer": "c_",
    "phase": "ph_",
    "milestone": "m_",
    "capture": "cap_",
    "order": "o_",
}


def new_id(kind: str) -> str:
    # A millisecond timestamp alone repeats when a loop creates several rows.
    stamp = datetime.now().strftime("%y%m%d%H%M%S")
    return "%s%s%s" % (ID_PREFIX.get(kind, "x_"), stamp, uuid4().hex[:6])


# ---------------------------------------------------------------------------
# change log
# ---------------------------------------------------------------------------

def log_change(db: sqlite3.Connection, entity: str, entity_id: str, action: str,
               before: Optional[Dict] = None, after: Optional[Dict] = None) -> None:
    db.execute(
        "INSERT INTO change_log (entity, entity_id, action, before_json, after_json, at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (
            entity,
            entity_id,
            action,
            json.dumps(before, ensure_ascii=False) if before is not None else None,
            json.dumps(after, ensure_ascii=False) if after is not None else None,
            datetime.now().replace(microsecond=0).isoformat(),
        ),
    )


# ---------------------------------------------------------------------------
# read
# ---------------------------------------------------------------------------

def _phase_map(db: sqlite3.Connection) -> Dict[str, str]:
    return {row["id"]: row["name"] for row in db.execute("SELECT id, name FROM phases")}


def _phase_id_map(db: sqlite3.Connection) -> Dict[str, str]:
    return {row["name"]: row["id"] for row in db.execute("SELECT id, name FROM phases")}


def _customer_map(db: sqlite3.Connection) -> Dict[str, str]:
    return {row["id"]: row["name"] for row in db.execute("SELECT id, name FROM customers")}


def _projects_payload(db: sqlite3.Connection, include_archived: bool = False) -> List[Dict]:
    sql = "SELECT * FROM projects"
    if not include_archived:
        sql += " WHERE archived = 0"
    sql += " ORDER BY created_at, name"
    rows = db.execute(sql).fetchall()
    if not rows:
        return []

    ids = [row["id"] for row in rows]
    marks = ",".join("?" * len(ids))

    done: Dict[str, List[str]] = {}
    for row in db.execute(
        "SELECT project_id, phase_name FROM done_phases WHERE project_id IN (%s)" % marks, ids
    ):
        done.setdefault(row["project_id"], []).append(row["phase_name"])

    milestones: Dict[str, List[Dict]] = {}
    for row in db.execute(
        "SELECT id, project_id, date, label, done FROM milestones"
        " WHERE project_id IN (%s) ORDER BY date" % marks, ids
    ):
        milestones.setdefault(row["project_id"], []).append({
            "id": row["id"], "date": row["date"], "label": row["label"],
            "done": bool(row["done"]),
        })

    unsure: Dict[str, List[str]] = {}
    for row in db.execute(
        "SELECT project_id, field FROM field_flags WHERE project_id IN (%s)" % marks, ids
    ):
        unsure.setdefault(row["project_id"], []).append(row["field"])

    phases = _phase_map(db)
    return [_project_dict(row, phases, done, milestones, unsure) for row in rows]


# Keys that live in their own column. Everything else a project carries
# (threads, the progress log, derived dates) is kept as JSON in payload_json,
# so the frontend can grow new fields without a migration.
COLUMN_KEYS = {
    "id", "name", "model", "customer", "phase", "orderId", "round", "start",
    "end", "color", "contact", "dept", "deptType", "contactWay", "means",
    "channel", "note", "next", "updated", "unsure", "done", "milestones",
}


def _project_dict(row, phases: Dict[str, str], done: Dict, milestones: Dict,
                  unsure: Dict) -> Dict:
    try:
        extra = json.loads(row["payload_json"] or "{}")
    except (ValueError, TypeError):
        extra = {}
    if not isinstance(extra, dict):
        extra = {}

    base = {
        "id": row["id"],
        "name": row["name"],
        "model": row["model"] or "",
        "customer": row["customer_id"] or "",
        "phase": phases.get(row["phase_id"] or "", ""),
        "orderId": row["order_id"] or "",
        "round": int(row["round"] or 1),
        "start": row["start_date"] or "",
        "end": row["end_date"] or "",
        "color": row["color"],
        "contact": row["contact"],
        "dept": row["dept"],
        "deptType": row["dept_type"],
        "contactWay": row["contact_way"],
        "means": row["means"],
        "channel": row["channel"],
        "note": row["note"],
        "next": row["next_action"],
        "updated": row["updated_at"][:10] if row["updated_at"] else "",
        "unsure": unsure.get(row["id"], []),
        "done": done.get(row["id"], []),
        "milestones": milestones.get(row["id"], []),
    }
    for key, value in extra.items():
        if key not in base:
            base[key] = value
    return base


def bootstrap() -> Dict[str, Any]:
    with connection() as db:
        customers = [
            {
                "id": row["id"], "name": row["name"], "alias": row["alias"],
                "contact": row["contact"], "channel": row["channel"],
            }
            for row in db.execute(
                "SELECT * FROM customers WHERE archived = 0 ORDER BY name"
            )
        ]
        phases = [
            {"id": row["id"], "name": row["name"], "color": row["color"],
             "ordinal": row["ordinal"]}
            for row in db.execute("SELECT * FROM phases ORDER BY ordinal, rowid")
        ]
        orders = [
            {"id": row["id"], "customer": row["customer_id"] or "",
             "code": row["code"], "note": row["note"]}
            for row in db.execute(
                "SELECT * FROM orders WHERE archived = 0 ORDER BY code, rowid"
            )
        ]
        projects = _projects_payload(db)
        counts = {
            "projects": len(projects),
            "customers": len(customers),
            "phases": len(phases),
            "orders": len(orders),
        }
    return {"customers": customers, "projects": projects, "phases": phases,
            "orders": orders, "counts": counts}


# ---------------------------------------------------------------------------
# whole-state replace (the browser's save())
# ---------------------------------------------------------------------------

def replace_state(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Replace customers/phases/projects in one transaction.

    The browser keeps the whole dataset in memory and persists on every edit.
    Sending everything back is far simpler than diffing, and at this size
    (a few hundred rows) it costs nothing. Captures and the change log are
    untouched: they are history, not state.
    """
    customers = payload.get("customers") or []
    phases = payload.get("phases") or []
    projects = payload.get("projects") or []
    orders = payload.get("orders") or []

    with connection() as db:
        before = _snapshot(db)

        db.execute("DELETE FROM milestones")
        db.execute("DELETE FROM done_phases")
        db.execute("DELETE FROM field_flags")
        db.execute("DELETE FROM projects")
        db.execute("DELETE FROM orders")
        db.execute("DELETE FROM customers")
        db.execute("DELETE FROM phases")

        phase_ids: Dict[str, str] = {}
        for ordinal, phase in enumerate(phases):
            name = (phase.get("name") or "").strip()
            if not name:
                continue
            pid = phase.get("id") or new_id("phase")
            if name in phase_ids:
                continue
            phase_ids[name] = pid
            db.execute(
                "INSERT INTO phases (id, name, color, ordinal) VALUES (?, ?, ?, ?)",
                (pid, name, phase.get("color") or "#8a94a5", ordinal),
            )

        customer_ids = set()
        for customer in customers:
            name = (customer.get("name") or "").strip()
            if not name:
                continue
            cid = customer.get("id") or new_id("customer")
            if cid in customer_ids:
                continue
            customer_ids.add(cid)
            db.execute(
                "INSERT INTO customers (id, name, alias, contact, channel, archived,"
                " created_at, updated_at) VALUES (?, ?, ?, ?, ?, 0, ?, ?)",
                (cid, name, customer.get("alias") or "", customer.get("contact") or "",
                 customer.get("channel") or "", today_str(), today_str()),
            )

        order_ids = set()
        for order in orders:
            oid = order.get("id") or new_id("order")
            if oid in order_ids:
                continue
            order_ids.add(oid)
            cid = order.get("customer") or ""
            if cid and cid not in customer_ids:
                cid = ""
            db.execute(
                "INSERT INTO orders (id, customer_id, code, note, archived)"
                " VALUES (?, ?, ?, ?, 0)",
                (oid, cid or None, order.get("code") or "", order.get("note") or ""),
            )

        for project in projects:
            pid = project.get("id") or new_id("project")
            cid = project.get("customer") or ""
            if cid and cid not in customer_ids:
                cid = ""
            oid = project.get("orderId") or ""
            if oid and oid not in order_ids:
                oid = ""
            phase_name = project.get("phase") or ""
            extra = {k: v for k, v in project.items() if k not in COLUMN_KEYS}
            db.execute(
                "INSERT INTO projects (id, name, model, customer_id, phase_id,"
                " order_id, round, start_date, end_date, color, contact, dept,"
                " dept_type, contact_way, means, channel, note, next_action,"
                " payload_json, archived, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    pid,
                    (project.get("name") or "未命名项目").strip(),
                    project.get("model") or "",
                    cid or None,
                    phase_ids.get(phase_name),
                    oid or None,
                    int(project.get("round") or 1),
                    project.get("start") or None,
                    project.get("end") or None,
                    project.get("color") or "#465ed8",
                    project.get("contact") or "",
                    project.get("dept") or "",
                    project.get("deptType") or "",
                    project.get("contactWay") or "",
                    project.get("means") or "",
                    project.get("channel") or "",
                    project.get("note") or "",
                    project.get("next") or "",
                    json.dumps(extra, ensure_ascii=False),
                    0,
                    project.get("updated") or today_str(),
                    project.get("updated") or today_str(),
                ),
            )
            for name in project.get("done") or []:
                if name in phase_ids:
                    db.execute(
                        "INSERT OR IGNORE INTO done_phases (project_id, phase_name)"
                        " VALUES (?, ?)", (pid, name),
                    )
            for field in project.get("unsure") or []:
                db.execute(
                    "INSERT OR IGNORE INTO field_flags (project_id, field, reason)"
                    " VALUES (?, ?, ?)", (pid, field, "解析置信度低，待人工确认"),
                )
            for item in project.get("milestones") or []:
                if not item.get("date"):
                    continue
                db.execute(
                    "INSERT INTO milestones (id, project_id, date, label, done)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (item.get("id") or new_id("milestone"), pid, item["date"],
                     item.get("label") or "", 1 if item.get("done") else 0),
                )

        after = _snapshot(db)
        if before != after:
            log_change(db, "state", "all", "replace", before, after)

    # Read back only after the transaction is committed. bootstrap() opens its
    # own connection, and a second connection cannot see uncommitted rows —
    # calling it inside the block silently returned the previous state.
    return bootstrap()


def _snapshot(db: sqlite3.Connection) -> Dict[str, Any]:
    return {
        "customers": [
            {"id": r["id"], "name": r["name"]} for r in db.execute("SELECT id, name FROM customers")
        ],
        "projects": [
            {"id": r["id"], "name": r["name"], "phase": r["phase_id"]}
            for r in db.execute("SELECT id, name, phase_id FROM projects")
        ],
        "phases": [r["name"] for r in db.execute("SELECT name FROM phases ORDER BY ordinal")],
        "orders": [r["code"] for r in db.execute("SELECT code FROM orders ORDER BY rowid")],
    }


# ---------------------------------------------------------------------------
# granular writes (used by import, scripts and the smoke test)
# ---------------------------------------------------------------------------

def patch_project(project_id: str, data: Dict[str, Any]) -> Dict:
    column_for = {
        "name": "name", "model": "model", "round": "round",
        "start": "start_date", "end": "end_date", "color": "color",
        "contact": "contact", "dept": "dept", "deptType": "dept_type",
        "contactWay": "contact_way", "means": "means", "channel": "channel",
        "note": "note", "next": "next_action", "updated": "updated_at",
        "orderId": "order_id",
    }
    with connection() as db:
        row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise KeyError(project_id)
        before = _project_dict(row, _phase_map(db), {}, {}, {})

        for key, column in column_for.items():
            if key in data and data[key] is not None:
                db.execute("UPDATE projects SET %s = ? WHERE id = ?" % column,
                           (data[key], project_id))

        if "customer" in data:
            db.execute("UPDATE projects SET customer_id = ? WHERE id = ?",
                       (data["customer"] or None, project_id))
        if "phase" in data:
            pid = _phase_id_map(db).get(data["phase"] or "")
            db.execute("UPDATE projects SET phase_id = ? WHERE id = ?", (pid, project_id))
        if "done" in data:
            db.execute("DELETE FROM done_phases WHERE project_id = ?", (project_id,))
            valid = set(_phase_id_map(db))
            for name in data["done"] or []:
                if name in valid:
                    db.execute(
                        "INSERT OR IGNORE INTO done_phases (project_id, phase_name)"
                        " VALUES (?, ?)", (project_id, name))
        if "unsure" in data:
            db.execute("DELETE FROM field_flags WHERE project_id = ?", (project_id,))
            for field in data["unsure"] or []:
                db.execute(
                    "INSERT OR IGNORE INTO field_flags (project_id, field, reason)"
                    " VALUES (?, ?, ?)", (project_id, field, "待人工确认"))
        if "milestones" in data:
            db.execute("DELETE FROM milestones WHERE project_id = ?", (project_id,))
            for item in data["milestones"] or []:
                if not item.get("date"):
                    continue
                db.execute(
                    "INSERT INTO milestones (id, project_id, date, label, done)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (item.get("id") or new_id("milestone"), project_id, item["date"],
                     item.get("label") or "", 1 if item.get("done") else 0))

        if isinstance(data.get("payload"), dict):
            try:
                merged = json.loads(row["payload_json"] or "{}")
            except (ValueError, TypeError):
                merged = {}
            if not isinstance(merged, dict):
                merged = {}
            merged.update(data["payload"])
            db.execute("UPDATE projects SET payload_json = ? WHERE id = ?",
                       (json.dumps(merged, ensure_ascii=False), project_id))

        db.execute("UPDATE projects SET updated_at = ? WHERE id = ?",
                   (data.get("updated") or today_str(), project_id))
        row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        after = _projects_for_ids(db, [project_id])[0]
        log_change(db, "project", project_id, "update", before, after)
    return after


def _projects_for_ids(db: sqlite3.Connection, ids: Iterable[str]) -> List[Dict]:
    ids = list(ids)
    if not ids:
        return []
    marks = ",".join("?" * len(ids))
    rows = {row["id"]: row for row in db.execute(
        "SELECT * FROM projects WHERE id IN (%s)" % marks, ids)}
    done: Dict[str, List[str]] = {}
    for row in db.execute(
        "SELECT project_id, phase_name FROM done_phases WHERE project_id IN (%s)" % marks, ids
    ):
        done.setdefault(row["project_id"], []).append(row["phase_name"])
    milestones: Dict[str, List[Dict]] = {}
    for row in db.execute(
        "SELECT id, project_id, date, label, done FROM milestones"
        " WHERE project_id IN (%s) ORDER BY date" % marks, ids
    ):
        milestones.setdefault(row["project_id"], []).append({
            "id": row["id"], "date": row["date"], "label": row["label"],
            "done": bool(row["done"])})
    unsure: Dict[str, List[str]] = {}
    for row in db.execute(
        "SELECT project_id, field FROM field_flags WHERE project_id IN (%s)" % marks, ids
    ):
        unsure.setdefault(row["project_id"], []).append(row["field"])
    phases = _phase_map(db)
    return [_project_dict(rows[i], phases, done, milestones, unsure)
            for i in ids if i in rows]


def delete_project(project_id: str) -> bool:
    with connection() as db:
        row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            return False
        db.execute("UPDATE projects SET archived = 1 WHERE id = ?", (project_id,))
        log_change(db, "project", project_id, "delete",
                   {"name": row["name"]}, None)
    return True


def replace_phases(phases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Replace the phase list and clean up references that no longer exist."""
    with connection() as db:
        old = [r["name"] for r in db.execute("SELECT name FROM phases ORDER BY ordinal")]
        # Keep the id of a phase whose name survives. The settings dialog sends
        # back the ids it received, but an import or a script may not, and
        # projects must not lose their current stage because of that.
        reuse = {r["name"]: r["id"] for r in db.execute("SELECT id, name FROM phases")}
        db.execute("DELETE FROM phases")

        ids: Dict[str, str] = {}
        for ordinal, phase in enumerate(phases):
            name = (phase.get("name") or "").strip()
            if not name or name in ids:
                continue
            pid = phase.get("id") or reuse.get(name) or new_id("phase")
            if pid in ids.values():
                pid = new_id("phase")
            ids[name] = pid
            db.execute(
                "INSERT INTO phases (id, name, color, ordinal) VALUES (?, ?, ?, ?)",
                (pid, name, phase.get("color") or "#8a94a5", ordinal),
            )

        if ids:
            marks = ",".join("?" * len(ids))
            db.execute("DELETE FROM done_phases WHERE phase_name NOT IN (%s)" % marks,
                       list(ids))
            db.execute(
                "UPDATE projects SET phase_id = NULL"
                " WHERE phase_id IS NOT NULL AND phase_id NOT IN (%s)" % marks,
                list(ids.values()))
        else:
            db.execute("DELETE FROM done_phases")
            db.execute("UPDATE projects SET phase_id = NULL")

        log_change(db, "phase", "all", "replace",
                   {"names": old}, {"names": list(ids)})
    return bootstrap()


def record_capture(raw_text: str, project_id: Optional[str], parser: str,
                   parsed: Dict[str, Any], applied: Dict[str, Any]) -> str:
    capture_id = new_id("capture")
    with connection() as db:
        db.execute(
            "INSERT INTO captures (id, raw_text, project_id, parser, parsed_json,"
            " applied_fields, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (capture_id, raw_text, project_id, parser,
             json.dumps(parsed, ensure_ascii=False),
             json.dumps(applied, ensure_ascii=False),
             datetime.now().replace(microsecond=0).isoformat()),
        )
    return capture_id
