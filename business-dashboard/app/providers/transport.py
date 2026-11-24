"""HTTP transport for model calls.

Standard library only: the app has to install on a locked-down Windows machine
where pulling extra wheels may not be an option.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Any, Dict, Tuple

MAX_RESPONSE_BYTES = 512 * 1024
DEFAULT_TIMEOUT = 30.0


class ProviderError(Exception):
    """A failure whose message is safe to show and to store."""


class ProviderTimeout(ProviderError):
    pass


class ProviderUnavailable(ProviderError):
    pass


class ProviderHttpError(ProviderError):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _short(text: str, limit: int = 240) -> str:
    return " ".join((text or "").split())[:limit]


def post_json(url: str, payload: Dict[str, Any], headers: Dict[str, str],
              timeout: float = DEFAULT_TIMEOUT) -> Tuple[int, Dict[str, Any]]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request_headers = {"Content-Type": "application/json"}
    request_headers.update(headers)
    request = urllib.request.Request(url, data=body, headers=request_headers, method="POST")

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES)
            status = response.status
    except urllib.error.HTTPError as error:
        try:
            detail = error.read(4096).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 - the status matters more than the body
            detail = ""
        raise ProviderHttpError(error.code, _short(detail) or str(error.reason))
    except socket.timeout:
        raise ProviderTimeout("接口响应超时（%d 秒）" % int(timeout))
    except urllib.error.URLError as error:
        reason = getattr(error, "reason", error)
        if isinstance(reason, socket.timeout):
            raise ProviderTimeout("接口响应超时（%d 秒）" % int(timeout))
        raise ProviderUnavailable("连不上接口：%s" % _short(str(reason), 120))

    try:
        return status, json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        raise ProviderUnavailable("接口返回的不是 JSON，可能被代理或登录页拦截了")
