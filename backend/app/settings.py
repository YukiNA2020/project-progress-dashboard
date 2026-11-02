"""Runtime locations for the local dashboard.

User data always lives outside the source repository. The environment override
exists so that verification runs (and portable installs) can point at a
throwaway directory. It is read on every call so tests never depend on import
order.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def data_directory() -> Path:
    override = os.environ.get("PROJECT_PROGRESS_DASHBOARD_DATA_DIR")
    if override:
        target = Path(override).expanduser()
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        target = base / "ProjectProgressDashboard"
    elif sys.platform == "darwin":
        target = Path.home() / "Library" / "Application Support" / "ProjectProgressDashboard"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
        target = base / "ProjectProgressDashboard"
    target.mkdir(parents=True, exist_ok=True)
    return target


def database_path() -> Path:
    return data_directory() / "dashboard.sqlite3"


def now_iso() -> str:
    from datetime import datetime

    return datetime.now().replace(microsecond=0).isoformat()
