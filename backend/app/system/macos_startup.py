"""macOS login startup through a per-user LaunchAgent.

The plist lives in ``~/Library/LaunchAgents`` and only affects the current
user. ``RunAtLoad`` starts the dashboard at login; ``KeepAlive`` is off so
quitting the app does not resurrect it. ``launchctl`` is called through an
injectable helper so verification never touches the real launchd database.
"""

from __future__ import annotations

import plistlib
import subprocess
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

LABEL = "com.projectprogressdashboard.dashboard"


def current_home() -> Path:
    return Path.home()


def plist_path(home: Optional[Path] = None) -> Path:
    root = Path(home) if home is not None else current_home()
    return root / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def build_plist(
    arguments: Sequence[str],
    log_path: str,
    working_directory: str = "",
) -> bytes:
    payload = {
        "Label": LABEL,
        "ProgramArguments": [str(item) for item in arguments],
        "RunAtLoad": True,
        "KeepAlive": False,
        "ProcessType": "Interactive",
        "StandardOutPath": str(log_path),
        "StandardErrorPath": str(log_path),
    }
    if working_directory:
        payload["WorkingDirectory"] = str(working_directory)
    return plistlib.dumps(payload, sort_keys=False)


def write(
    arguments: Sequence[str],
    log_path: str,
    working_directory: str = "",
    home: Optional[Path] = None,
) -> Path:
    target = plist_path(home)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(build_plist(arguments, log_path, working_directory))
    return target


def remove(home: Optional[Path] = None) -> bool:
    target = plist_path(home)
    if not target.exists():
        return False
    target.unlink()
    return True


def is_present(home: Optional[Path] = None) -> bool:
    return plist_path(home).is_file()


def read(arguments: Sequence[str], home: Optional[Path] = None) -> dict:
    target = plist_path(home)
    if not target.is_file():
        return {}
    try:
        data = plistlib.loads(target.read_bytes())
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _run_launchctl(arguments: List[str]) -> Tuple[int, str]:
    try:
        completed = subprocess.run(
            ["launchctl", *arguments],
            capture_output=True,
            text=True,
            timeout=10,
            shell=False,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return 1, str(error)
    return completed.returncode, (completed.stderr or completed.stdout or "").strip()


def domain() -> str:
    return f"gui/{_uid()}"


def _uid() -> int:
    import os

    return os.getuid()


def bootstrap(target: Path, runner=None) -> Tuple[bool, str]:
    run = runner or _run_launchctl
    # Bootout first so an already-loaded or stale job does not make the
    # bootstrap fail with "service already loaded".
    run(["bootout", domain(), str(target)])
    code, output = run(["bootstrap", domain(), str(target)])
    return code == 0, output


def bootout(target: Path, runner=None) -> bool:
    run = runner or _run_launchctl
    code, _output = run(["bootout", domain(), str(target)])
    return code == 0
