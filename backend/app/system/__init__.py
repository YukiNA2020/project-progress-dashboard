"""Operating-system integration for the dashboard.

Two capabilities live here and nowhere else:

* opening a registered project folder in the OS file manager;
* registering the dashboard as a login-startup item.

Both are isolated behind this package so the rest of the backend never branches
on the operating system. Module-level hooks (``registry_module``,
``home_override``, ``launchctl_runner``, ``python_executable``) exist so that
verification can run every branch without touching the real machine.
"""

from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path
from typing import List, Optional

from . import macos_startup, windows_startup
from .opener import OpenFolderError, open_folder, resolve_folder

__all__ = [
    "OpenFolderError",
    "StartupError",
    "backend_directory",
    "disable_startup",
    "enable_startup",
    "launcher_arguments",
    "open_folder",
    "platform_id",
    "platform_label",
    "resolve_folder",
    "startup_status",
]

# Verification overrides. ``None`` means "use the real thing".
registry_module = None
home_override: Optional[Path] = None
launchctl_runner = None
python_executable: Optional[str] = None


class StartupError(Exception):
    """Login startup is not available on this platform."""


def platform_id() -> str:
    if os.name == "nt":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def platform_label() -> str:
    return {"windows": "Windows", "macos": "macOS", "linux": "Linux"}.get(platform_id(), platform_id())


def backend_directory() -> Path:
    # .../backend/app/system/__init__.py -> .../backend
    return Path(__file__).resolve().parents[2]


def repository_directory() -> Path:
    return backend_directory().parent


def _log_path() -> Path:
    from ..settings import log_path

    return log_path()


def _startup_python() -> str:
    if python_executable:
        return python_executable
    return sys.executable


def launcher_arguments() -> List[str]:
    """The exact command the login-startup entry runs."""
    if platform_id() == "windows":
        # 一些受管 Windows 计算机会按策略禁止 pythonw.exe；用隐藏启动器
        # 拉起 python.exe，同样不会出现控制台窗口。
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        return [
            str(system_root / "System32" / "wscript.exe"),
            str(backend_directory() / "launch_hidden.vbs"),
        ]
    return [str(_startup_python()), str(backend_directory() / "run.py"), "serve", "--open-browser"]


def _display(command: List[str], platform: str) -> str:
    if platform == "windows":
        return windows_startup.command_line(command)
    return shlex.join(command)


def _status(
    platform: str,
    supported: bool,
    enabled: bool,
    command: str,
    location: str,
    note: str,
    manual_step: str = "",
) -> dict:
    return {
        "platform": platform,
        "platform_label": platform_label(),
        "supported": supported,
        "enabled": enabled,
        "command": command,
        "location": location,
        "note": note,
        "manual_step": manual_step,
    }


WINDOWS_NOTE = "登录时通过当前用户的启动项注册表键拉起本地服务；可在任务管理器的“启动”标签里关闭。"
MACOS_NOTE = "登录时通过当前用户的 LaunchAgent 拉起本地服务；关闭后不会自行重启。"
UNSUPPORTED_NOTE = "当前系统暂不支持登录时自动启动；仍可手动运行启动命令。"


def startup_status() -> dict:
    platform = platform_id()
    command = launcher_arguments()

    if platform == "windows":
        line = windows_startup.command_line(command)
        return _status(
            platform,
            True,
            windows_startup.is_registered(line, registry_module),
            line,
            windows_startup.location(),
            WINDOWS_NOTE,
        )

    if platform == "macos":
        target = macos_startup.plist_path(home_override)
        display = str(target)
        home = str(home_override) if home_override is not None else str(Path.home())
        if display.startswith(home):
            display = "~" + display[len(home):]
        return _status(
            platform,
            True,
            macos_startup.is_present(home_override),
            _display(command, platform),
            display,
            MACOS_NOTE,
        )

    return _status(platform, False, False, _display(command, platform), "", UNSUPPORTED_NOTE)


def enable_startup() -> dict:
    platform = platform_id()
    command = launcher_arguments()

    if platform == "windows":
        windows_startup.write_command(windows_startup.command_line(command), registry_module)
        return startup_status()

    if platform == "macos":
        target = macos_startup.write(
            command,
            str(_log_path()),
            working_directory=str(backend_directory()),
            home=home_override,
        )
        ok, output = macos_startup.bootstrap(target, launchctl_runner)
        status = startup_status()
        if not ok:
            status["manual_step"] = f'launchctl bootstrap gui/$(id -u) "{target}"'
            status["note"] = (
                "启动项文件已写入，但 launchctl 没有接受它。请手动执行下面的命令，或重新登录后再试。"
            ) + (f"（{output[:160]}）" if output else "")
        return status

    raise StartupError("当前系统暂不支持登录时自动启动")


def disable_startup() -> dict:
    platform = platform_id()

    if platform == "windows":
        windows_startup.remove(registry_module)
        return startup_status()

    if platform == "macos":
        target = macos_startup.plist_path(home_override)
        if target.exists():
            macos_startup.bootout(target, launchctl_runner)
        macos_startup.remove(home_override)
        return startup_status()

    raise StartupError("当前系统没有可移除的启动项")
