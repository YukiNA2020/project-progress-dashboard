"""Model provider configuration.

Only the backend reads this. The browser receives the provider name, endpoint
host, model name, and a masked key hint; it never receives the key itself.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import urlparse

from . import secrets_store
from .db import connection
from .settings import now_iso

PROVIDERS = {
    "openai": {
        "label": "OpenAI 兼容接口",
        "default_base_url": "https://api.openai.com/v1",
        "key_placeholder": "sk-…",
    },
    "anthropic": {
        "label": "Anthropic 接口",
        "default_base_url": "https://api.anthropic.com/v1",
        "key_placeholder": "sk-ant-…",
    },
}

DEFAULTS: Dict[str, Any] = {
    "enabled": False,
    "provider": "openai",
    "base_url": "",
    "model": "",
    "json_mode": True,
}

MAX_BASE_URL = 500
MAX_MODEL = 120


class ConfigError(ValueError):
    pass


def _row() -> Dict[str, Any]:
    with connection() as db:
        row = db.execute("SELECT * FROM provider_settings WHERE id = 1").fetchone()
    if row is None:
        with connection() as db:
            db.execute(
                """INSERT OR IGNORE INTO provider_settings
                   (id, enabled, provider, base_url, model, json_mode, updated_at)
                   VALUES (1, 0, 'openai', '', '', 1, ?)""",
                (now_iso(),),
            )
            row = db.execute("SELECT * FROM provider_settings WHERE id = 1").fetchone()
    data = dict(row)
    data["enabled"] = bool(data["enabled"])
    data["json_mode"] = bool(data["json_mode"])
    return data


def get_settings() -> Dict[str, Any]:
    data = _row()
    has_key, hint = secrets_store.describe(data["provider"])
    provider = data["provider"] if data["provider"] in PROVIDERS else "openai"
    base_url = data["base_url"] or PROVIDERS[provider]["default_base_url"]
    return {
        "enabled": data["enabled"],
        "provider": provider,
        "base_url": data["base_url"],
        "effective_base_url": base_url,
        "endpoint_host": urlparse(base_url).hostname or "",
        "model": data["model"],
        "json_mode": data["json_mode"],
        "api_key_set": has_key,
        "key_hint": hint,
        "key_storage": secrets_store.storage_kind(),
        "last_test_at": data["last_test_at"],
        "last_test_ok": None if data["last_test_ok"] is None else bool(data["last_test_ok"]),
        "last_test_message": data["last_test_message"],
        "ready": bool(data["enabled"] and data["model"].strip() and has_key),
        "providers": [
            {"id": key, "label": value["label"], "default_base_url": value["default_base_url"]}
            for key, value in PROVIDERS.items()
        ],
    }


def save_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    current = _row()
    provider = str(payload.get("provider") or current["provider"]).strip().lower()
    if provider not in PROVIDERS:
        raise ConfigError("未知的模型服务商")

    base_url = payload.get("base_url")
    base_url = current["base_url"] if base_url is None else str(base_url)
    base_url = base_url.strip().rstrip("/")
    if len(base_url) > MAX_BASE_URL:
        raise ConfigError("接口地址过长")
    if base_url:
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ConfigError("接口地址需要以 http:// 或 https:// 开头")

    model_value = payload.get("model")
    model = (current["model"] if model_value is None else str(model_value)).strip()
    if len(model) > MAX_MODEL:
        raise ConfigError("模型名过长")

    enabled = bool(payload.get("enabled", current["enabled"]))
    json_mode = bool(payload.get("json_mode", current["json_mode"]))
    if enabled and not model:
        raise ConfigError("启用模型抽取前需要填写模型名")

    # api_key omitted (None) keeps the stored key; an empty string clears it.
    api_key = payload.get("api_key", None)
    if api_key is not None:
        api_key = str(api_key).strip()
        if len(api_key) > 400:
            raise ConfigError("密钥过长")
        # Keys are stored per provider, so switching providers never carries a
        # key over to a different service.
        if api_key:
            secrets_store.set_secret(provider, api_key)
        else:
            secrets_store.clear_secret(provider)

    has_key, _ = secrets_store.describe(provider)
    if enabled and not has_key:
        raise ConfigError("启用模型抽取前需要填写 API 密钥")

    with connection() as db:
        db.execute(
            """UPDATE provider_settings
               SET enabled = ?, provider = ?, base_url = ?, model = ?, json_mode = ?, updated_at = ?
               WHERE id = 1""",
            (int(enabled), provider, base_url, model, int(json_mode), now_iso()),
        )
    return get_settings()


def record_test(ok: bool, message: str) -> None:
    with connection() as db:
        db.execute(
            "UPDATE provider_settings SET last_test_at = ?, last_test_ok = ?, last_test_message = ? WHERE id = 1",
            (now_iso(), int(ok), message[:500]),
        )


def ready_settings() -> Optional[Dict[str, Any]]:
    """Return settings only when a scan may call the provider."""
    data = get_settings()
    if not data["ready"]:
        return None
    return data
