"""Provider dispatch.

The key is resolved here, on the server side, and never travels to the browser.
Every error message is scrubbed of credential-looking fragments before it is
returned or stored.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Tuple

from .. import secrets_store
from . import anthropic, openai
from .transport import (ProviderError, ProviderHttpError, ProviderTimeout,
                        ProviderUnavailable, post_json)

ADAPTERS = {"openai": openai, "anthropic": anthropic}

PING_SYSTEM = "你是一个连通性测试端点。只输出 JSON。"
PING_USER = '只输出 {"ok": true} 这一个 JSON 对象，不要输出其他内容。'


def adapter_for(provider: str):
    return ADAPTERS.get(provider, openai)


def _key(settings: Dict[str, Any]) -> str:
    return settings.get("transient_key") or secrets_store.get_secret(
        settings.get("provider", "openai"))


def _send(settings: Dict[str, Any], system_prompt: str, user_prompt: str,
          json_mode: bool) -> str:
    provider = settings.get("provider") or "openai"
    model = (settings.get("model") or "").strip()
    if not model:
        raise ProviderUnavailable("还没填模型名")

    key = _key(settings)
    if not key:
        raise ProviderUnavailable("还没保存 API 密钥")

    adapter = adapter_for(provider)
    url = adapter.endpoint(settings.get("effective_base_url")
                           or settings.get("base_url") or "")
    payload = adapter.build_payload(model, system_prompt, user_prompt, json_mode)
    headers = adapter.headers(key)

    try:
        _status, data = post_json(url, payload, headers)
    except ProviderHttpError as error:
        # Some OpenAI-compatible gateways reject response_format outright.
        # Retry once without it instead of failing the whole call.
        if json_mode and error.status in (400, 404, 422) and \
                "response_format" in (error.detail or "").lower():
            payload.pop("response_format", None)
            _status, data = post_json(url, payload, headers)
        else:
            raise
    try:
        return adapter.extract_text(data)
    except (KeyError, TypeError, IndexError):
        raise ProviderUnavailable("接口响应里找不到文本内容")


def complete(settings: Dict[str, Any], system_prompt: str, user_prompt: str) -> str:
    json_mode = bool(settings.get("json_mode", True))
    try:
        return _send(settings, system_prompt, user_prompt, json_mode)
    except ProviderTimeout as error:
        raise ProviderUnavailable(secrets_store.redact(str(error)))
    except ProviderError as error:
        raise ProviderUnavailable(secrets_store.redact(str(error)))
    except Exception as error:  # noqa: BLE001 - never leak a provider bug upward
        raise ProviderUnavailable(
            "调用模型时出现未预期的错误（%s）" % type(error).__name__)


def ping(settings: Dict[str, Any]) -> Tuple[bool, str, int]:
    started = time.monotonic()
    try:
        text = _send(settings, PING_SYSTEM, PING_USER, bool(settings.get("json_mode", True)))
    except ProviderError as error:
        elapsed = int((time.monotonic() - started) * 1000)
        return False, secrets_store.redact(str(error)), elapsed
    except Exception as error:  # noqa: BLE001
        elapsed = int((time.monotonic() - started) * 1000)
        return False, "未预期的错误（%s）" % type(error).__name__, elapsed
    elapsed = int((time.monotonic() - started) * 1000)
    if not text.strip():
        return False, "接口返回了空内容", elapsed
    return True, "连接成功，返回 %d 个字符" % len(text.strip()), elapsed
