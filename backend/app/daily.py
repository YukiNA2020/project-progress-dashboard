"""At most one automatic scan per local calendar day.

The claim is a primary-key insert into ``daily_scans``. SQLite serialises it, so
two copies of the app starting at the same moment cannot both win: the second
``INSERT OR IGNORE`` reports zero changed rows. A failed automatic scan still
consumes the day — retrying is an explicit user action, not a background loop.
"""

from __future__ import annotations

import threading
from datetime import date
from typing import Callable, Optional

from .db import connection
from .settings import now_iso

# Guard within one process; the database claim is what protects across processes.
_run_lock = threading.Lock()


def local_day(value: Optional[str] = None) -> str:
    return value or date.today().isoformat()


def claim(day: Optional[str] = None) -> bool:
    """Reserve today's automatic scan. True only for the first caller."""
    stamp = now_iso()
    with connection() as db:
        cursor = db.execute(
            """INSERT OR IGNORE INTO daily_scans (scan_date, result, started_at)
               VALUES (?, 'running', ?)""",
            (local_day(day), stamp),
        )
        return cursor.rowcount == 1


def _finish(day: str, result: str, run_id: Optional[str], message: str = "") -> None:
    with connection() as db:
        db.execute(
            """UPDATE daily_scans
               SET result = ?, run_id = ?, message = ?, finished_at = ?
               WHERE scan_date = ?""",
            (result, run_id, message, now_iso(), day),
        )


def run_if_due(
    day: Optional[str] = None,
    scanner: Optional[Callable[..., dict]] = None,
) -> dict:
    """Run the daily scan when this is the first start of the local day."""
    target_day = local_day(day)
    scan = scanner
    if scan is None:
        from . import service

        scan = service.scan_all

    with _run_lock:
        if not claim(target_day):
            return {
                "ran": False,
                "reason": "already_ran_today",
                "date": target_day,
                "run": None,
            }
        try:
            run = scan(trigger="auto")
        except Exception as error:
            _finish(target_day, "failed", None, f"自动巡检出错（{type(error).__name__}）")
            raise
        _finish(target_day, run.get("result", "unknown"), run.get("id"), run.get("message", ""))
        return {
            "ran": True,
            "reason": "first_start_of_day",
            "date": target_day,
            "run": run,
        }


def status() -> dict:
    today = local_day()
    with connection() as db:
        today_row = db.execute("SELECT * FROM daily_scans WHERE scan_date = ?", (today,)).fetchone()
        last_row = db.execute(
            "SELECT * FROM daily_scans ORDER BY scan_date DESC LIMIT 1"
        ).fetchone()
    today_data = dict(today_row) if today_row is not None else {}
    last_data = dict(last_row) if last_row is not None else {}
    return {
        "today": today,
        "ran_today": today_row is not None,
        "today_result": today_data.get("result"),
        "today_started_at": today_data.get("started_at"),
        "today_finished_at": today_data.get("finished_at"),
        "last_date": last_data.get("scan_date"),
        "last_result": last_data.get("result"),
        "last_run_id": last_data.get("run_id"),
        "last_finished_at": last_data.get("finished_at"),
    }
