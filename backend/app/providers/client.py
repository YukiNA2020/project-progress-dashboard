"""Provider dispatch.

The key is resolved here, on the server, and never travels to the browser.
Every raised error message has credentials redacted before it leaves this
module.
"""

from __future__ import annotations

import time
from typing import Dict, Tuple

from .. import secrets_store
from . import anthropic, openai
from .transport import ProviderError, ProviderHttpError, ProviderUnavailable, post_json

ADAPTERS = {
    "openai": openai,
    "anthropic": anthropic,
}

PING_SYSTEM = "你是一个连通性测试端点。只输出 JSON。"
PING_USER = '请只输出 {"ok": true} 这一个 JSON 对象，不要输出其他内容。'


def adapter_for(provider: str):
    return ADAPTERS.get(provider, openai)


def _send(settings: Dict, system_prompt: str, user_prompt: str, json_mode: bool) -> str:
    provider = settings["provider"]
    model = (settings.get("model") or "").strip()
    if not model:
        raise ProviderUnavailable("尚未配置模型名")

    key = settings.get("transient_key") or secrets_store.get_secret(provider)
    if not key:
        raise ProviderUnavailable("尚未保存该服务商的 API 密钥")

    adapter = adapter_for(provider)
    url = adapter.endpoint(settings.get("effective_base_url") or settings.get("base_url") or "")
    payload = adapter.build_payload(model, system_prompt, user_prompt, json_mode)
    headers = adapter.headers(key)

    try:
        _status, data = post_json(url, payload, headers)
    except ProviderHttpError as error:
        # Some OpenAI-compatible endpoints reject ``response_format``; retry once
        # without it so a stricter proxy does not block every scan.
        if json_mode and error.status in (400, 404, 422) and "response_format" in error.detail.lower():
            payload.pop("response_format", None)
            _status, data = post_json(url, payload, headers)
        else:
            raise

    try:
        return adapter.extract_text(data)
    except (KeyError, TypeError, IndexError):
        raise ProviderUnavailable("接口响应中找不到文本内容")


def complete(settings: Dict, system_prompt: str, user_prompt: str) -> str:
    json_mode = bool(settings.get("json_mode", True))
    try:
        return _send(settings, system_prompt, user_prompt, json_mode)
    except ProviderError as error:
        # Normalise the failure type so callers only deal with one shape, and
        # make sure no credential fragment survives in the message.
        raise ProviderUnavailable(secrets_store.redact(str(error)))


def ping(settings: Dict) -> Tuple[bool, str, int]:
    """Send a one-line request and report whether the endpoint answered."""
    started = time.monotonic()
    try:
        text = _send(settings, PING_SYSTEM, PING_USER, bool(settings.get("json_mode", True)))
    except ProviderError as error:
        elapsed = int((time.monotonic() - started) * 1000)
        return False, secrets_store.redact(str(error)), elapsed
    elapsed = int((time.monotonic() - started) * 1000)
    if not text.strip():
        return False, "接口返回了空内容", elapsed
    return True, f"连接成功，返回 {len(text.strip())} 个字符", elapsed
