"""Scan orchestration and persistence.

A scan reads registered folders, builds a candidate state per project, then
optionally asks the configured model to cross-check that candidate. Two
guarantees matter most:

* A failed path, a failed provider, or an unusable answer never erases the last
  accepted state.
* Nothing in a project folder is opened for writing. The scanner only ever
  reads bytes and parses them.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import traceback
from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple
from uuid import uuid4

from . import config_store
from .db import connection
from .providers.analyze import ModelOutcome, analyze
from .reconcile import Decision, decide
from .scanner.discovery import discover_markdown_files, resolve_project_root
from .scanner.markdown_doc import parse_document
from .scanner.state import Candidate, build_candidate
from .settings import now_iso

ERROR_MESSAGES = {
    "path_empty": "项目文件夹路径为空",
    "path_not_found": "项目文件夹不存在或当前电脑无法访问",
    "path_not_directory": "登记的路径不是文件夹",
    "path_unresolved": "项目文件夹路径无法解析",
}

ACCEPTABLE_SCHEDULE_FIELDS = ("planned_start", "planned_end")


def active_projects(project_ids: Optional[Sequence[str]] = None) -> List[sqlite3.Row]:
    with connection() as db:
        rows = db.execute("SELECT * FROM projects WHERE archived = 0 ORDER BY planned_start, name").fetchall()
    if project_ids:
        allowed = set(project_ids)
        return [row for row in rows if row["id"] in allowed]
    return rows


def _safe_json(value: str, default):
    try:
        return json.loads(value) if value else default
    except (TypeError, ValueError):
        return default


def state_for(project_id: str) -> Optional[dict]:
    with connection() as db:
        row = db.execute("SELECT * FROM project_state WHERE project_id = ?", (project_id,)).fetchone()
    if row is None:
        return None
    data = dict(row)
    data["notes"] = _safe_json(data.get("notes") or "[]", [])
    data["model_citations"] = _safe_json(data.get("model_citations") or "[]", [])
    data["candidate_testing"] = bool(data.get("candidate_testing"))
    return data


def phases_for(project_id: str) -> List[dict]:
    with connection() as db:
        rows = db.execute(
            "SELECT * FROM project_phases WHERE project_id = ? ORDER BY ordinal", (project_id,)
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["testing"] = bool(item["testing"])
        result.append(item)
    return result


def evidence_for(project_id: str) -> List[dict]:
    with connection() as db:
        rows = db.execute(
            """SELECT * FROM project_evidence WHERE project_id = ?
               ORDER BY COALESCE(record_date, '') DESC, id DESC LIMIT 60""",
            (project_id,),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["is_newest"] = bool(item["is_newest"])
        result.append(item)
    return result


def pending_for(project_id: str, include_decided: bool = False) -> List[dict]:
    query = "SELECT * FROM pending_confirmations WHERE project_id = ?"
    if not include_decided:
        query += " AND status = 'pending'"
    query += " ORDER BY id"
    with connection() as db:
        rows = db.execute(query, (project_id,)).fetchall()
    return [dict(row) for row in rows]


def latest_run() -> Optional[dict]:
    with connection() as db:
        row = db.execute("SELECT * FROM scan_runs ORDER BY started_at DESC, rowid DESC LIMIT 1").fetchone()
    if row is None:
        return None
    data = dict(row)
    data["changes"] = _safe_json(data.get("changes") or "[]", [])
    data["model_enabled"] = bool(data.get("model_enabled"))
    return data


def _phase_diff(previous: Optional[dict], decision: Decision, candidate: Candidate, project: dict) -> List[dict]:
    if previous is None:
        return []
    changes: List[dict] = []
    previous_phase = previous.get("candidate_phase")
    current_phase = decision.phase.name if decision.phase else None
    if current_phase and current_phase != previous_phase:
        changes.append(
            {
                "project_id": project["id"],
                "project_name": project["name"],
                "kind": "phase",
                "previous": previous_phase,
                "current": current_phase,
            }
        )
    previous_date = previous.get("newest_record_date")
    newest = candidate.newest.record_date.isoformat() if candidate.newest else None
    if newest and newest != previous_date:
        changes.append(
            {
                "project_id": project["id"],
                "project_name": project["name"],
                "kind": "record",
                "previous": previous_date,
                "current": newest,
            }
        )
    if previous.get("status") != decision.status:
        changes.append(
            {
                "project_id": project["id"],
                "project_name": project["name"],
                "kind": "status",
                "previous": previous.get("status"),
                "current": decision.status,
            }
        )
    return changes


def _citation_payload(decision: Decision) -> str:
    return json.dumps(
        [
            {
                "evidence_id": citation.evidence_id,
                "quote": citation.quote,
                "supports": citation.supports,
                "source": citation.source,
            }
            for citation in decision.citations
        ],
        ensure_ascii=False,
    )


def _store_success(
    project: dict,
    candidate: Candidate,
    decision: Decision,
    previous: Optional[dict],
) -> List[dict]:
    stamp = now_iso()
    current = decision.phase
    changes = _phase_diff(previous, decision, candidate, project)

    accepted_phase = previous.get("accepted_phase") if previous else None
    accepted_ordinal = previous.get("accepted_phase_ordinal") if previous else None
    accepted_start = previous.get("accepted_phase_start") if previous else None
    accepted_end = previous.get("accepted_phase_end") if previous else None
    if decision.status == "ok" and current is not None:
        accepted_phase = current.name
        accepted_ordinal = current.ordinal
        accepted_start = current.start.isoformat() if current.start else None
        accepted_end = current.end.isoformat() if current.end else None

    model_status = decision.model_status
    model_checked_at = None if model_status == "disabled" else stamp

    with connection() as db:
        db.execute("DELETE FROM project_phases WHERE project_id = ?", (project["id"],))
        db.execute("DELETE FROM project_evidence WHERE project_id = ?", (project["id"],))
        db.executemany(
            """INSERT INTO project_phases
               (project_id, ordinal, name, status, start_date, end_date, testing, source_path, source_heading, scanned_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    project["id"],
                    phase.ordinal,
                    phase.name,
                    phase.status,
                    phase.start.isoformat() if phase.start else None,
                    phase.end.isoformat() if phase.end else None,
                    int(phase.testing),
                    phase.source_path,
                    phase.source_heading,
                    stamp,
                )
                for phase in candidate.phases
            ],
        )
        db.executemany(
            """INSERT INTO project_evidence
               (project_id, kind, source_path, heading, record_date, claim, excerpt, is_newest, scanned_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    project["id"],
                    item.kind,
                    item.source_path,
                    item.heading,
                    item.record_date.isoformat() if item.record_date else None,
                    item.claim,
                    item.excerpt,
                    int(item.is_newest),
                    stamp,
                )
                for item in candidate.evidence
            ],
        )
        db.execute(
            """INSERT OR REPLACE INTO project_state (
                   project_id, status, reason, summary, summary_source,
                   accepted_phase, accepted_phase_ordinal, accepted_phase_start, accepted_phase_end,
                   candidate_phase, candidate_phase_ordinal, candidate_phase_start, candidate_phase_end,
                   current_basis, candidate_testing, newest_record_date, newest_record_claim,
                   newest_record_source, files_scanned, evidence_count, scan_error, notes,
                   model_status, model_provider, model_name, model_confidence, model_summary,
                   model_citations, model_error, model_checked_at,
                   last_failure_at, scanned_at, last_success_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                project["id"],
                decision.status,
                decision.reason,
                decision.summary,
                decision.summary_source,
                accepted_phase,
                accepted_ordinal,
                accepted_start,
                accepted_end,
                candidate.current.name if candidate.current else None,
                candidate.current.ordinal if candidate.current else None,
                candidate.current.start.isoformat() if candidate.current and candidate.current.start else None,
                candidate.current.end.isoformat() if candidate.current and candidate.current.end else None,
                decision.basis,
                int(decision.testing),
                candidate.newest.record_date.isoformat() if candidate.newest else None,
                candidate.newest.claim if candidate.newest else None,
                candidate.newest.source_path if candidate.newest else None,
                candidate.files_scanned,
                len(candidate.evidence),
                None,
                json.dumps(decision.notes, ensure_ascii=False),
                model_status,
                decision.model_provider or None,
                decision.model_name or None,
                decision.model_confidence or None,
                decision.model_summary or None,
                _citation_payload(decision),
                decision.model_error or None,
                model_checked_at,
                previous.get("last_failure_at") if previous else None,
                stamp,
                stamp,
                stamp,
            ),
        )
        _refresh_pending(db, project, decision, stamp)
    return changes


def _refresh_pending(db: sqlite3.Connection, project: dict, decision: Decision, stamp: str) -> None:
    # Pending rows describe the current scan result. Superseded ones are removed;
    # decisions already taken (accepted / dismissed) are kept so a dismissed
    # proposal does not reappear on every scan.
    db.execute(
        "DELETE FROM pending_confirmations WHERE project_id = ? AND status = 'pending'",
        (project["id"],),
    )

    for proposal in decision.proposals:
        previous = project.get(proposal.field) or ""
        dedupe = f"schedule:{proposal.field}:{proposal.candidate.isoformat()}"
        db.execute(
            """INSERT OR IGNORE INTO pending_confirmations
               (project_id, kind, dedupe_key, field, previous_value, candidate_value, source_path, evidence, status, created_at)
               VALUES (?, 'schedule_change', ?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (
                project["id"],
                dedupe,
                proposal.field,
                previous,
                proposal.candidate.isoformat(),
                proposal.source_path,
                proposal.claim,
                stamp,
            ),
        )

    if decision.status == "needs_confirmation":
        digest = hashlib.sha1(decision.reason.encode("utf-8")).hexdigest()[:12]
        db.execute(
            """INSERT OR IGNORE INTO pending_confirmations
               (project_id, kind, dedupe_key, field, previous_value, candidate_value, source_path, evidence, status, created_at)
               VALUES (?, 'ambiguous_state', ?, '', ?, ?, ?, ?, 'pending', ?)""",
            (
                project["id"],
                f"ambiguous:{digest}",
                decision.reason,
                decision.phase.name if decision.phase else "",
                decision.citations[0].source if decision.citations else "",
                decision.reason,
                stamp,
            ),
        )

    if decision.status == "model_error":
        digest = hashlib.sha1(decision.model_error.encode("utf-8")).hexdigest()[:12]
        db.execute(
            """INSERT OR IGNORE INTO pending_confirmations
               (project_id, kind, dedupe_key, field, previous_value, candidate_value, source_path, evidence, status, created_at)
               VALUES (?, 'model_issue', ?, '', ?, ?, ?, ?, 'pending', ?)""",
            (
                project["id"],
                f"model:{digest}",
                decision.model_error,
                decision.model_status,
                decision.model_provider or "",
                decision.model_error,
                stamp,
            ),
        )


def _store_failure(project: dict, message: str) -> None:
    stamp = now_iso()
    with connection() as db:
        existing = db.execute(
            "SELECT project_id FROM project_state WHERE project_id = ?", (project["id"],)
        ).fetchone()
        if existing is None:
            db.execute(
                """INSERT INTO project_state
                       (project_id, status, reason, scan_error, last_failure_at, scanned_at, updated_at)
                   VALUES (?, 'unknown', ?, ?, ?, ?, ?)""",
                (project["id"], message, message, stamp, stamp, stamp),
            )
        else:
            # Keep every previously accepted value; only record the failure.
            db.execute(
                """UPDATE project_state
                   SET scan_error = ?, last_failure_at = ?, scanned_at = ?, updated_at = ?
                   WHERE project_id = ?""",
                (message, stamp, stamp, stamp, project["id"]),
            )


def scan_project(
    project: dict, provider_settings: Optional[dict] = None
) -> Tuple[str, str, List[dict], str]:
    root, error = resolve_project_root(project["folder_path"])
    if root is None or error:
        message = ERROR_MESSAGES.get(error or "path_not_found", "项目文件夹不可访问")
        _store_failure(project, message)
        return "failed", message, [], "skipped"

    try:
        discovery = discover_markdown_files(root)
    except OSError:
        message = "读取项目文件夹时出错"
        _store_failure(project, message)
        return "failed", message, [], "skipped"

    documents = [parse_document(item.relative_path, item.text) for item in discovery.files]
    candidate = build_candidate(project, discovery, documents, date.today())
    previous = state_for(project["id"])

    outcome: Optional[ModelOutcome] = None
    if provider_settings is not None:
        try:
            outcome = analyze(candidate, project, provider_settings, date.today())
        except Exception as error:  # noqa: BLE001 - a provider bug must not break the scan
            outcome = ModelOutcome(
                status="failed",
                error=f"模型抽取出现未预期的错误（{type(error).__name__}）",
                provider=provider_settings.get("provider", ""),
                model=provider_settings.get("model", ""),
            )

    decision = decide(candidate, outcome, project)
    changes = _store_success(project, candidate, decision, previous)
    return decision.status, decision.reason, changes, decision.model_status


def _apply_schedule_change(project_id: str, field: str, candidate_value: str) -> bool:
    with connection() as db:
        row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            return False
        start = row["planned_start"]
        end = row["planned_end"]
        if field == "planned_start":
            start = candidate_value
        elif field == "planned_end":
            end = candidate_value
        else:
            return False
        if start > end:
            return False
        db.execute(
            "UPDATE projects SET planned_start = ?, planned_end = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (start, end, project_id),
        )
    return True


def decide_pending(pending_id: int, decision: str) -> dict:
    with connection() as db:
        row = db.execute("SELECT * FROM pending_confirmations WHERE id = ?", (pending_id,)).fetchone()
    if row is None:
        raise LookupError("待确认项不存在")
    item = dict(row)
    if item["status"] != "pending":
        raise ValueError("该待确认项已经处理过了")
    if decision not in ("accept", "dismiss"):
        raise ValueError("未知的处理方式")
    if decision == "accept":
        if item["kind"] != "schedule_change" or item["field"] not in ACCEPTABLE_SCHEDULE_FIELDS:
            raise ValueError("只有排期变更可以接受；阶段冲突需要先修正来源文档")
        if not _apply_schedule_change(item["project_id"], item["field"], item["candidate_value"]):
            raise ValueError("新的排期与另一条计划日期冲突，未做修改")
        status = "accepted"
    else:
        status = "dismissed"

    stamp = now_iso()
    with connection() as db:
        db.execute(
            "UPDATE pending_confirmations SET status = ?, decided_at = ? WHERE id = ?",
            (status, stamp, pending_id),
        )
    return {"id": pending_id, "status": status, "decided_at": stamp}


def project_detail(project_id: str) -> Optional[dict]:
    with connection() as db:
        row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        return None
    project = dict(row)
    project["archived"] = bool(project["archived"])
    return {
        "project": project,
        "state": state_for(project_id),
        "phases": phases_for(project_id),
        "evidence": evidence_for(project_id),
        "pending": pending_for(project_id),
        "scan": latest_run(),
    }


def scan_all(
    project_ids: Optional[Sequence[str]] = None,
    use_model: Optional[bool] = None,
    trigger: str = "manual",
) -> dict:
    run_id = str(uuid4())
    started = now_iso()
    projects = active_projects(project_ids)

    provider_settings: Optional[dict] = None
    if use_model is not False:
        provider_settings = config_store.ready_settings()

    results: List[dict] = []
    counts: Dict[str, int] = {
        "projects_ok": 0,
        "projects_needing_confirmation": 0,
        "projects_unknown": 0,
        "projects_failed": 0,
        "projects_model_error": 0,
        "schedule_proposals": 0,
        "model_ok": 0,
        "model_failed": 0,
    }
    changes: List[dict] = []

    for row in projects:
        project = dict(row)
        try:
            status, reason, project_changes, model_status = scan_project(project, provider_settings)
        except Exception as error:  # noqa: BLE001 - one project must never break a run
            traceback.print_exc()
            message = f"解析该项目文档时出错（{type(error).__name__}）"
            _store_failure(project, message)
            status, reason, project_changes, model_status = "failed", message, [], "skipped"
        results.append(
            {
                "project_id": project["id"],
                "name": project["name"],
                "status": status,
                "reason": reason,
                "model_status": model_status,
            }
        )
        changes.extend(project_changes)
        if status == "ok":
            counts["projects_ok"] += 1
        elif status == "needs_confirmation":
            counts["projects_needing_confirmation"] += 1
        elif status == "unknown":
            counts["projects_unknown"] += 1
        elif status == "model_error":
            counts["projects_model_error"] += 1
        else:
            counts["projects_failed"] += 1

        if model_status == "ok":
            counts["model_ok"] += 1
        elif model_status in ("failed", "invalid"):
            counts["model_failed"] += 1

        counts["schedule_proposals"] += len(
            [item for item in pending_for(project["id"]) if item["kind"] == "schedule_change"]
        )

    blocked = counts["projects_failed"] + counts["projects_model_error"]
    if not projects:
        result = "ok"
        message = "没有需要巡检的项目"
    elif blocked == len(projects):
        result = "failed"
        if counts["projects_failed"]:
            message = "全部项目巡检失败，已保留上次成功状态"
        else:
            message = "全部项目的模型抽取未成功，已保留上次成功状态"
    elif blocked:
        result = "partial"
        if counts["projects_failed"]:
            message = f"{counts['projects_failed']} 个项目巡检失败，已保留上次成功状态"
        else:
            message = f"{counts['projects_model_error']} 个项目的模型抽取未成功，已保留上次成功状态"
    else:
        result = "ok"
        message = "巡检完成"

    finished = now_iso()
    with connection() as db:
        db.execute(
            """INSERT INTO scan_runs (
                   id, started_at, finished_at, result, projects_total, projects_ok,
                   projects_needing_confirmation, projects_unknown, projects_failed,
                   schedule_proposals, changes, message, model_ok, model_failed, model_enabled, trigger
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                started,
                finished,
                result,
                len(projects),
                counts["projects_ok"],
                counts["projects_needing_confirmation"],
                counts["projects_unknown"],
                counts["projects_failed"],
                counts["schedule_proposals"],
                json.dumps(changes, ensure_ascii=False),
                message,
                counts["model_ok"],
                counts["model_failed"],
                int(provider_settings is not None),
                trigger if trigger in ("manual", "auto", "cli") else "manual",
            ),
        )

    return {
        "id": run_id,
        "started_at": started,
        "finished_at": finished,
        "result": result,
        "projects_total": len(projects),
        "projects_ok": counts["projects_ok"],
        "projects_needing_confirmation": counts["projects_needing_confirmation"],
        "projects_unknown": counts["projects_unknown"],
        "projects_failed": counts["projects_failed"],
        "projects_model_error": counts["projects_model_error"],
        "schedule_proposals": counts["schedule_proposals"],
        "model_ok": counts["model_ok"],
        "model_failed": counts["model_failed"],
        "model_enabled": provider_settings is not None,
        "trigger": trigger if trigger in ("manual", "auto", "cli") else "manual",
        "changes": changes,
        "message": message,
        "projects": results,
    }
