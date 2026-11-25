"""SQLite access and schema.

The schema only ever grows. New tables use ``CREATE TABLE IF NOT EXISTS`` and
new columns are added by :func:`ensure_column`, so a database created by an
earlier build keeps opening after an update.
"""

from __future__ import annotations

import shutil
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .settings import database_path, now_iso

SCHEMA_VERSION = 2

# Columns added after the first release. They are appended with ALTER TABLE on
# an existing database, so a board created yesterday keeps opening today.
LATE_COLUMNS = (
    ("projects", "model", "TEXT NOT NULL DEFAULT ''"),
    ("projects", "order_id", "TEXT"),
    ("projects", "round", "INTEGER NOT NULL DEFAULT 1"),
    ("projects", "payload_json", "TEXT NOT NULL DEFAULT '{}'"),
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS customers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    alias TEXT NOT NULL DEFAULT '',
    contact TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL DEFAULT '',
    archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS phases (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    color TEXT NOT NULL,
    ordinal INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    customer_id TEXT,
    phase_id TEXT,
    order_id TEXT,
    round INTEGER NOT NULL DEFAULT 1,
    start_date TEXT,
    end_date TEXT,
    color TEXT NOT NULL,
    contact TEXT NOT NULL DEFAULT '',
    dept TEXT NOT NULL DEFAULT '',
    dept_type TEXT NOT NULL DEFAULT '',
    contact_way TEXT NOT NULL DEFAULT '',
    means TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    next_action TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_projects_customer ON projects(customer_id);
CREATE INDEX IF NOT EXISTS idx_projects_phase ON projects(phase_id);

CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    customer_id TEXT,
    code TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    archived INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS done_phases (
    project_id TEXT NOT NULL,
    phase_name TEXT NOT NULL,
    PRIMARY KEY (project_id, phase_name)
);

CREATE TABLE IF NOT EXISTS milestones (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    date TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    done INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_milestones_project ON milestones(project_id);
CREATE INDEX IF NOT EXISTS idx_milestones_date ON milestones(date);

CREATE TABLE IF NOT EXISTS field_flags (
    project_id TEXT NOT NULL,
    field TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (project_id, field)
);

CREATE TABLE IF NOT EXISTS captures (
    id TEXT PRIMARY KEY,
    raw_text TEXT NOT NULL,
    project_id TEXT,
    parser TEXT NOT NULL,
    parsed_json TEXT NOT NULL,
    applied_fields TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_captures_project ON captures(project_id, created_at);

CREATE TABLE IF NOT EXISTS change_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    before_json TEXT,
    after_json TEXT,
    at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    db = sqlite3.connect(str(database_path()), timeout=10.0)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA journal_mode = WAL")
    db.execute("PRAGMA synchronous = NORMAL")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def ensure_column(db: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    existing = {row["name"] for row in db.execute("PRAGMA table_info(%s)" % table)}
    if column not in existing:
        db.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, column, definition))


def _backup(path: Path, version: int) -> str:
    target = path.with_name(path.name + ".bak.v%d" % version)
    try:
        shutil.copy2(str(path), str(target))
        return str(target)
    except OSError:
        return ""


def _current_version(db: sqlite3.Connection) -> int:
    try:
        row = db.execute("SELECT version FROM schema_meta LIMIT 1").fetchone()
    except sqlite3.OperationalError:
        # Brand new database: the table has not been created yet.
        return 0
    return int(row["version"]) if row else 0


def _integrity_ok(db: sqlite3.Connection) -> bool:
    try:
        row = db.execute("PRAGMA integrity_check").fetchone()
        return bool(row) and str(row[0]).lower() == "ok"
    except sqlite3.DatabaseError:
        return False


def initialize_database() -> dict:
    """Create or upgrade the database. Returns a short report for /api/health."""
    path = database_path()
    report = {"path": str(path), "created": False, "backed_up": "", "recovered": False}

    db = sqlite3.connect(str(path), timeout=10.0)
    db.row_factory = sqlite3.Row
    try:
        if not _integrity_ok(db):
            db.close()
            broken = path.with_name(path.name + ".broken." + now_iso().replace(":", ""))
            try:
                path.replace(broken)
            except OSError:
                pass
            report["recovered"] = True
            db = sqlite3.connect(str(path), timeout=10.0)
            db.row_factory = sqlite3.Row

        report["created"] = _current_version(db) == 0
        if not report["created"]:
            report["backed_up"] = _backup(path, _current_version(db))

        db.execute("PRAGMA journal_mode = WAL")
        db.executescript(SCHEMA)
        for table, column, definition in LATE_COLUMNS:
            ensure_column(db, table, column, definition)
        row = db.execute("SELECT version FROM schema_meta LIMIT 1").fetchone()
        if row is None:
            db.execute("INSERT INTO schema_meta (version) VALUES (?)", (SCHEMA_VERSION,))
        elif int(row["version"]) < SCHEMA_VERSION:
            db.execute("UPDATE schema_meta SET version = ?", (SCHEMA_VERSION,))
        db.commit()
    finally:
        db.close()
    return report


def seed_defaults() -> None:
    """Give a brand new database the real overseas-project pipeline.

    These nine stages are the ones the business actually runs on: a quote is
    issued, the order is raised, development passes first-article and
    industrial samples, HR releases it for production, the rolling plan is
    submitted (a hard four-week gate), the factory produces, a third party
    inspects, the goods ship, and the model is finally on sale.

    Everything here is editable from the settings dialog, so this is a
    starting point rather than a constraint.
    """
    with connection() as db:
        count = db.execute("SELECT COUNT(*) AS n FROM phases").fetchone()["n"]
        if count:
            return
        defaults = [
            ("报价", "#8a94a5"),
            ("立项", "#7c8cf8"),
            ("开发", "#465ed8"),
            ("HR过号", "#c2417a"),
            ("滚动计划", "#d98324"),
            ("生产", "#e8a13a"),
            ("抽检", "#0f7b8a"),
            ("发运", "#1d9e75"),
            ("在售", "#2b8a3e"),
        ]
        for ordinal, (name, color) in enumerate(defaults):
            db.execute(
                "INSERT INTO phases (id, name, color, ordinal) VALUES (?, ?, ?, ?)",
                ("ph_%d" % (ordinal + 1), name, color, ordinal),
            )
