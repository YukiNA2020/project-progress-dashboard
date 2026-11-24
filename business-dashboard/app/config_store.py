"""Model provider settings.

Kept in the ``settings`` table rather than a config file so that everything the
app owns lives in one database that can be copied as a unit.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from . import secrets_store
from .db import connection
from .settings import now_iso

KEY = "provider"

PROVIDERS = {
    "openai": {
        "label": "OpenAI 兼容接口",
        "default_base_url": "https://api.openai.com/v1",
    },
    "anthropic": {
        "label": "Anthropic",
        "default_base_url": "https://api.anthropic.com/v1",
    },
}

DEFAULTS = {
    "enabled": False,
    "provider": "openai",
    "base_url": "",
    "model": "",
    "json_mode": True,
}


class ConfigError(Exception):
    pass


def _load() -> Dict[str, Any]:
    with connection() as db:
        row = db.execute("SELECT value FROM settings WHERE key = ?", (KEY,)).fetchone()
    if row is None:
        return dict(DEFAULTS)
    try:
        stored = json.loads(row["value"])
    except ValueError:
        return dict(DEFAULTS)
    if not isinstance(stored, dict):
        return dict(DEFAULTS)
    merged = dict(DEFAULTS)
    merged.update({k: v for k, v in stored.items() if k in DEFAULTS or k.startswith("last_test")})
    return merged


def _save(values: Dict[str, Any]) -> None:
    with connection() as db:
        db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (KEY, json.dumps(values, ensure_ascii=False)),
        )


def get_settings() -> Dict[str, Any]:
    stored = _load()
    provider = stored.get("provider") or "openai"
    if provider not in PROVIDERS:
        provider = "openai"
    key_set, hint = secrets_store.describe(provider)
    base_url = (stored.get("base_url") or "").strip()
    effective = base_url or PROVIDERS[provider]["default_base_url"]

    return {
        "enabled": bool(stored.get("enabled")),
        "provider": provider,
        "base_url": base_url,
        "model": stored.get("model") or "",
        "json_mode": bool(stored.get("json_mode", True)),
        "api_key_set": key_set,
        "key_hint": hint,
        "key_storage": secrets_store.storage_kind(),
        "providers": [
            {"id": key, "label": value["label"],
             "default_base_url": value["default_base_url"]}
            for key, value in PROVIDERS.items()
        ],
        "effective_base_url": effective,
        "endpoint_host": urlparse(effective).hostname or "",
        "last_test_at": stored.get("last_test_at"),
        "last_test_ok": stored.get("last_test_ok"),
        "last_test_message": stored.get("last_test_message") or "",
    }


def save_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    stored = _load()

    if "provider" in payload and payload["provider"] is not None:
        provider = str(payload["provider"]).strip().lower()
        if provider not in PROVIDERS:
            raise ConfigError("未知的模型服务商")
        stored["provider"] = provider

    if payload.get("base_url") is not None:
        base_url = str(payload["base_url"]).strip().rstrip("/")
        if base_url:
            parsed = urlparse(base_url)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                raise ConfigError("接口地址需要以 http:// 或 https:// 开头")
        stored["base_url"] = base_url

    if payload.get("model") is not None:
        stored["model"] = str(payload["model"]).strip()

    if payload.get("enabled") is not None:
        stored["enabled"] = bool(payload["enabled"])

    if payload.get("json_mode") is not None:
        stored["json_mode"] = bool(payload["json_mode"])

    provider = stored.get("provider", "openai")
    if payload.get("api_key"):
        secrets_store.set_secret(provider, str(payload["api_key"]).strip())
    elif "api_key" in payload and payload["api_key"] == "":
        secrets_store.clear_secret(provider)

    _save(stored)
    return get_settings()


def runtime() -> Dict[str, Any]:
    """The settings a call needs, with the key resolved server-side only."""
    stored = _load()
    provider = stored.get("provider") or "openai"
    return {
        "enabled": bool(stored.get("enabled")),
        "provider": provider,
        "base_url": stored.get("base_url") or "",
        "effective_base_url": (stored.get("base_url") or "").strip()
        or PROVIDERS.get(provider, PROVIDERS["openai"])["default_base_url"],
        "model": stored.get("model") or "",
        "json_mode": bool(stored.get("json_mode", True)),
        "api_key_set": bool(secrets_store.get_secret(provider)),
    }


def remember_test(ok: bool, message: str) -> None:
    stored = _load()
    stored["last_test_at"] = now_iso()
    stored["last_test_ok"] = bool(ok)
    stored["last_test_message"] = message
    _save(stored)
