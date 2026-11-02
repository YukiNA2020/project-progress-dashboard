"""SQLite access and schema.

The schema only ever grows: new tables use ``CREATE TABLE IF NOT EXISTS`` and
new columns are added by :func:`_ensure_column` when an older database is
opened. An existing Phase 1 or Phase 2 database therefore keeps working.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from .settings import database_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    folder_path TEXT NOT NULL,
    planned_start TEXT NOT NULL,
    planned_end TEXT NOT NULL,
    color TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS project_state (
    project_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'unknown',
    reason TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    summary_source TEXT NOT NULL DEFAULT '',
    accepted_phase TEXT,
    accepted_phase_ordinal INTEGER,
    accepted_phase_start TEXT,
    accepted_phase_end TEXT,
    candidate_phase TEXT,
    candidate_phase_ordinal INTEGER,
    candidate_phase_start TEXT,
    candidate_phase_end TEXT,
    current_basis TEXT NOT NULL DEFAULT 'none',
    candidate_testing INTEGER NOT NULL DEFAULT 0,
    newest_record_date TEXT,
    newest_record_claim TEXT,
    newest_record_source TEXT,
    files_scanned INTEGER NOT NULL DEFAULT 0,
    evidence_count INTEGER NOT NULL DEFAULT 0,
    scan_error TEXT,
    notes TEXT NOT NULL DEFAULT '[]',
    scanned_at TEXT,
    last_success_at TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS project_phases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    start_date TEXT,
    end_date TEXT,
    testing INTEGER NOT NULL DEFAULT 0,
    source_path TEXT NOT NULL,
    source_heading TEXT NOT NULL DEFAULT '',
    scanned_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_project_phases ON project_phases (project_id, ordinal);

CREATE TABLE IF NOT EXISTS project_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    source_path TEXT NOT NULL,
    heading TEXT NOT NULL DEFAULT '',
    record_date TEXT,
    claim TEXT NOT NULL DEFAULT '',
    excerpt TEXT NOT NULL DEFAULT '',
    is_newest INTEGER NOT NULL DEFAULT 0,
    scanned_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_project_evidence ON project_evidence (project_id, kind);

CREATE TABLE IF NOT EXISTS pending_confirmations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    dedupe_key TEXT NOT NULL,
    field TEXT NOT NULL DEFAULT '',
    previous_value TEXT NOT NULL DEFAULT '',
    candidate_value TEXT NOT NULL DEFAULT '',
    source_path TEXT NOT NULL DEFAULT '',
    evidence TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    decided_at TEXT,
    UNIQUE (project_id, dedupe_key)
);

CREATE TABLE IF NOT EXISTS scan_runs (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    result TEXT NOT NULL,
    projects_total INTEGER NOT NULL DEFAULT 0,
    projects_ok INTEGER NOT NULL DEFAULT 0,
    projects_needing_confirmation INTEGER NOT NULL DEFAULT 0,
    projects_unknown INTEGER NOT NULL DEFAULT 0,
    projects_failed INTEGER NOT NULL DEFAULT 0,
    schedule_proposals INTEGER NOT NULL DEFAULT 0,
    changes TEXT NOT NULL DEFAULT '[]',
    message TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS provider_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    enabled INTEGER NOT NULL DEFAULT 0,
    provider TEXT NOT NULL DEFAULT 'openai',
    base_url TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    json_mode INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_test_at TEXT,
    last_test_ok INTEGER,
    last_test_message TEXT NOT NULL DEFAULT ''
);
"""

# Columns added after their table first shipped. ``ALTER TABLE ... ADD COLUMN``
# is applied only when the column is missing, so opening an older database is
# safe and repeatable.
ADDED_COLUMNS = {
    "project_state": {
        "model_status": "TEXT NOT NULL DEFAULT 'disabled'",
        "model_provider": "TEXT",
        "model_name": "TEXT",
        "model_confidence": "TEXT",
        "model_summary": "TEXT",
        "model_citations": "TEXT NOT NULL DEFAULT '[]'",
        "model_error": "TEXT",
        "model_checked_at": "TEXT",
    },
    "scan_runs": {
        "model_ok": "INTEGER NOT NULL DEFAULT 0",
        "model_failed": "INTEGER NOT NULL DEFAULT 0",
        "model_enabled": "INTEGER NOT NULL DEFAULT 0",
    },
}


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    db = sqlite3.connect(database_path())
    db.row_factory = sqlite3.Row
    try:
        yield db
        db.commit()
    finally:
        db.close()


def _ensure_column(db: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    existing = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def initialize_database() -> None:
    with connection() as db:
        db.executescript(SCHEMA)
        for table, columns in ADDED_COLUMNS.items():
            for column, definition in columns.items():
                _ensure_column(db, table, column, definition)
