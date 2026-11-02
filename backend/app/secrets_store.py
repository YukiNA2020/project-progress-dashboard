"""API key storage that never touches the repository or the browser.

Priority order:

1. The operating system credential store, when the optional ``keyring``
   package is importable.
2. A ``credentials.json`` file inside the per-user application data directory,
   created with ``0600`` permissions.

Either way the key lives outside this repository, is never logged, and is
never returned to the frontend: the API only exposes a masked hint. The file
fallback exists because the MVP must run without extra dependencies; the
keyring path is used automatically when available.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Optional, Tuple

from .settings import data_directory

SERVICE_NAME = "project-progress-dashboard"
FILE_NAME = "credentials.json"

KNOWN_PROVIDERS = ("openai", "anthropic")


def _keyring():
    try:
        import keyring  # type: ignore
        from keyring.errors import KeyringError  # type: ignore
    except Exception:  # noqa: BLE001 - optional dependency must never break startup
        return None, None
    return keyring, KeyringError


def _credentials_path() -> Path:
    return data_directory() / FILE_NAME


def _read_file() -> Dict[str, str]:
    path = _credentials_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items() if isinstance(value, str)}


def _write_file(values: Dict[str, str]) -> None:
    path = _credentials_path()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(temporary, 0o600)
    except OSError:
        pass
    os.replace(temporary, path)
    try:
        os.chmod(path, 0o600)
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
        except Exception:  # noqa: BLE001 - fall back to the local file
            pass
    return _read_file().get(provider, "")


def set_secret(provider: str, value: str) -> None:
    if value:
        keyring, _ = _keyring()
        if keyring is not None:
            try:
                keyring.set_password(SERVICE_NAME, provider, value)
                _remove_from_file(provider)
                return
            except Exception:  # noqa: BLE001 - fall back to the local file
                pass
        values = _read_file()
        values[provider] = value
        _write_file(values)
        return
    clear_secret(provider)


def clear_secret(provider: str) -> None:
    keyring, _ = _keyring()
    if keyring is not None:
        try:
            keyring.delete_password(SERVICE_NAME, provider)
        except Exception:  # noqa: BLE001 - nothing stored there
            pass
    _remove_from_file(provider)


def _remove_from_file(provider: str) -> None:
    values = _read_file()
    if provider not in values:
        return
    values.pop(provider, None)
    if values:
        _write_file(values)
        return
    path = _credentials_path()
    try:
        path.unlink()
    except OSError:
        pass


def mask(value: str) -> str:
    """A hint the user can recognise without exposing the key."""
    if not value:
        return ""
    if len(value) <= 8:
        return "已保存"
    return f"{value[:3]}…{value[-4:]}"


def describe(provider: str) -> Tuple[bool, str]:
    value = get_secret(provider)
    return bool(value), mask(value)


def redact(text: str, secret: Optional[str] = None) -> str:
    """Strip anything that looks like a credential from a safe error message."""
    if not text:
        return ""
    cleaned = text
    if secret:
        cleaned = cleaned.replace(secret, "***")
    import re

    cleaned = re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "sk-***", cleaned)
    cleaned = re.sub(r"(?i)(api[-_ ]?key|authorization|x-api-key)\s*[:=]\s*\S+", r"\1: ***", cleaned)
    return cleaned
