"""API key storage that never reaches the repository or the browser.

Order: the OS credential store when the optional ``keyring`` package happens to
be installed, otherwise a ``credentials.json`` inside the per-user data folder
with 0600 permissions. The frontend only ever sees a masked hint.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Dict, Optional, Tuple

from .settings import data_directory

SERVICE_NAME = "business-dashboard"
FILE_NAME = "credentials.json"


def _keyring():
    try:
        import keyring  # type: ignore
        from keyring.errors import KeyringError  # type: ignore
    except Exception:  # noqa: BLE001 - optional dependency must never break startup
        return None, None
    return keyring, KeyringError


def _path() -> Path:
    return data_directory() / FILE_NAME


def _read() -> Dict[str, str]:
    path = _path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if isinstance(v, str)}


def _write(values: Dict[str, str]) -> None:
    path = _path()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(str(temporary), 0o600)
    except OSError:
        pass
    os.replace(str(temporary), str(path))
    try:
        os.chmod(str(path), 0o600)
    except OSError:
        pass


def storage_kind() -> str:
    keyring, _ = _keyring()
    return "keyring" if keyring is not None else "file"


def get_secret(provider: str) -> str:
    keyring, _ = _keyring()
    if keyring is not None:
        try:
            value = keyring.get_password(SERVICE_NAME, provider)
            if value:
                return value
        except Exception:  # noqa: BLE001 - fall back to the file
            pass
    return _read().get(provider, "")


def set_secret(provider: str, value: str) -> None:
    if not value:
        clear_secret(provider)
        return
    keyring, _ = _keyring()
    if keyring is not None:
        try:
            keyring.set_password(SERVICE_NAME, provider, value)
            values = _read()
            values.pop(provider, None)
            if values:
                _write(values)
            else:
                _path().unlink(missing_ok=True)
            return
        except Exception:  # noqa: BLE001 - fall back to the file
            pass
    values = _read()
    values[provider] = value
    _write(values)


def clear_secret(provider: str) -> None:
    keyring, _ = _keyring()
    if keyring is not None:
        try:
            keyring.delete_password(SERVICE_NAME, provider)
        except Exception:  # noqa: BLE001 - nothing stored there
            pass
    values = _read()
    if provider in values:
        values.pop(provider, None)
        if values:
            _write(values)
        else:
            try:
                _path().unlink()
            except OSError:
                pass


def mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "已保存"
    return "%s…%s" % (value[:3], value[-4:])


def describe(provider: str) -> Tuple[bool, str]:
    value = get_secret(provider)
    return bool(value), mask(value)


def redact(text: str, secret: Optional[str] = None) -> str:
    if not text:
        return ""
    cleaned = text
    if secret:
        cleaned = cleaned.replace(secret, "***")
    cleaned = re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "sk-***", cleaned)
    cleaned = re.sub(r"(?i)(api[-_ ]?key|authorization|x-api-key)\s*[:=]\s*\S+",
                     r"\1: ***", cleaned)
    return cleaned
