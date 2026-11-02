"""HTTP transport for provider calls.

Uses the Python standard library so the MVP needs no extra runtime
dependency. Every failure is converted into a short, credential-free message
that is safe to store and show in the UI.
"""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from typing import Any, Dict, Tuple

MAX_RESPONSE_BYTES = 512 * 1024
DEFAULT_TIMEOUT = 30.0


class ProviderError(Exception):
    """A provider failure with a message that is safe to display."""


class ProviderTimeout(ProviderError):
    pass


class ProviderUnavailable(ProviderError):
    pass


class ProviderHttpError(ProviderError):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def timeout_seconds() -> float:
    raw = os.environ.get("PROJECT_PROGRESS_DASHBOARD_PROVIDER_TIMEOUT")
    if not raw:
        return DEFAULT_TIMEOUT
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_TIMEOUT
    return value if value > 0 else DEFAULT_TIMEOUT


def _short(text: str, limit: int = 240) -> str:
    cleaned = " ".join((text or "").split())
    return cleaned[:limit]


def post_json(
    url: str,
    payload: Dict[str, Any],
    headers: Dict[str, str],
    timeout: float = None,
) -> Tuple[int, Dict[str, Any]]:
    """POST JSON and return ``(status, parsed_body)``.

    Raises :class:`ProviderError` subclasses on network, timeout, HTTP, or
    JSON failures. Callers must assume the message may be shown to the user,
    so it never includes request headers.
    """
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("Accept", "application/json")
    for key, value in headers.items():
        request.add_header(key, value)

    effective_timeout = timeout if timeout is not None else timeout_seconds()
    try:
        with urllib.request.urlopen(request, timeout=effective_timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES)
            status = response.status
    except urllib.error.HTTPError as error:
        try:
            detail = error.read(MAX_RESPONSE_BYTES).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 - body may be unreadable
            detail = ""
        raise ProviderHttpError(
            error.code, f"接口返回 HTTP {error.code}：{_short(detail) or error.reason}"
        )
    except urllib.error.URLError as error:
        reason = getattr(error, "reason", error)
        if isinstance(reason, socket.timeout) or isinstance(reason, TimeoutError):
            raise ProviderTimeout(f"接口在 {effective_timeout:.0f} 秒内没有响应")
        raise ProviderUnavailable(f"无法连接接口：{_short(str(reason))}")
    except (socket.timeout, TimeoutError):
        raise ProviderTimeout(f"接口在 {effective_timeout:.0f} 秒内没有响应")
    except OSError as error:
        raise ProviderUnavailable(f"网络请求失败：{_short(str(error))}")

    try:
        parsed = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        raise ProviderUnavailable("接口响应不是合法 JSON")
    if not isinstance(parsed, dict):
        raise ProviderUnavailable("接口响应结构无法识别")
    return status, parsed
