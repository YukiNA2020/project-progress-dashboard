"""Open a registered project folder in the operating system file manager.

Only paths that are already stored in the project registry reach this module;
there is no API that opens an arbitrary path. The folder must exist and be a
directory, and the command is run without a shell so the path can never be
interpreted as shell syntax.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, List, Optional

TIMEOUT_SECONDS = 10


class OpenFolderError(Exception):
    """A user-readable reason why the folder could not be opened."""


def current_platform() -> str:
    if os.name == "nt":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def resolve_folder(raw_path: str) -> Path:
    text = (raw_path or "").strip()
    if not text:
        raise OpenFolderError("项目文件夹路径为空")
    path = Path(text).expanduser()
    try:
        exists = path.exists()
    except OSError:
        raise OpenFolderError("项目文件夹路径无法解析")
    if not exists:
        raise OpenFolderError("项目文件夹不存在，或当前电脑无法访问这个路径")
    if not path.is_dir():
        raise OpenFolderError("登记的路径不是文件夹")
    return path.resolve()


def command_for(platform: str, path: Path) -> List[str]:
    if platform == "windows":
        return ["explorer", str(path)]
    if platform == "macos":
        return ["open", str(path)]
    return ["xdg-open", str(path)]


def _run(command: List[str]) -> int:
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
        shell=False,
        check=False,
    )
    return completed.returncode


def open_folder(
    raw_path: str,
    platform: Optional[str] = None,
    runner: Optional[Callable[[List[str]], int]] = None,
) -> dict:
    path = resolve_folder(raw_path)
    target = platform or current_platform()
    if target not in ("windows", "macos", "linux"):
        raise OpenFolderError(f"暂不支持在当前系统（{target}）上自动打开文件夹")

    command = command_for(target, path)
    exit_code = (runner or _run)(command)

    # explorer.exe returns a non-zero code even when it opens the folder, so a
    # non-zero code only counts as a failure on the other platforms.
    if target != "windows" and exit_code != 0:
        raise OpenFolderError(f"系统没有成功打开文件夹（退出码 {exit_code}）")

    return {"opened": True, "path": str(path), "handler": command[0]}
