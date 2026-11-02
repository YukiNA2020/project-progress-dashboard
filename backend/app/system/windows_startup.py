"""Windows login startup through the per-user Run key.

``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run`` needs no
administrator rights, survives restarts, and is visible in Task Manager's
startup tab, so a user can disable the entry without this app. The value stores
one command line; :mod:`app.system` builds it from the current interpreter and
``backend/run.py``.

The registry module is passed in explicitly so the logic can be exercised on a
machine that is not running Windows.
"""

from __future__ import annotations

import subprocess
from typing import List

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "ProjectProgressDashboard"


def _default_module():
    import winreg  # noqa: PLC0415 - Windows only

    return winreg


def command_line(arguments: List[str]) -> str:
    # list2cmdline implements the Windows quoting rules used by CreateProcess.
    return subprocess.list2cmdline([str(item) for item in arguments])


def read_command(module=None) -> str:
    registry = module or _default_module()
    try:
        key = registry.OpenKey(registry.HKEY_CURRENT_USER, RUN_KEY, 0, registry.KEY_READ)
    except FileNotFoundError:
        return ""
    except OSError:
        return ""
    try:
        value, _kind = registry.QueryValueEx(key, VALUE_NAME)
    except FileNotFoundError:
        return ""
    except OSError:
        return ""
    finally:
        registry.CloseKey(key)
    return str(value or "")


def write_command(command: str, module=None) -> None:
    registry = module or _default_module()
    key = registry.CreateKeyEx(registry.HKEY_CURRENT_USER, RUN_KEY, 0, registry.KEY_WRITE)
    try:
        registry.SetValueEx(key, VALUE_NAME, 0, registry.REG_SZ, command)
    finally:
        registry.CloseKey(key)


def remove(module=None) -> bool:
    registry = module or _default_module()
    try:
        key = registry.OpenKey(registry.HKEY_CURRENT_USER, RUN_KEY, 0, registry.KEY_WRITE)
    except FileNotFoundError:
        return False
    except OSError:
        return False
    try:
        registry.DeleteValue(key, VALUE_NAME)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False
    finally:
        registry.CloseKey(key)


def is_registered(command: str, module=None) -> bool:
    saved = read_command(module)
    if not saved:
        return False
    return saved.strip().casefold() == command.strip().casefold()


def location() -> str:
    return f"HKEY_CURRENT_USER\\{RUN_KEY}\\{VALUE_NAME}"
