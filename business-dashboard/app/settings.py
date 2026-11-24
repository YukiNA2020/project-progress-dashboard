"""Runtime locations.

User data never lives inside the repository: the folder gets copied around,
synced, and version-controlled, none of which should touch the database.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

APP_DIR_NAME = "BusinessDashboard"
OVERRIDE_ENV = "BIZBOARD_DATA_DIR"


def data_directory() -> Path:
    override = os.environ.get(OVERRIDE_ENV)
    if override:
        target = Path(override).expanduser()
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        target = base / APP_DIR_NAME
    elif sys.platform == "darwin":
        target = Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
        target = base / APP_DIR_NAME
    target.mkdir(parents=True, exist_ok=True)
    return target


def database_path() -> Path:
    return data_directory() / "dashboard.sqlite3"


def log_path() -> Path:
    return data_directory() / "dashboard.log"


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")
