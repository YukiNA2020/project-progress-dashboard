"""OpenAI-compatible chat completions.

The base URL is user-configurable, so any endpoint that speaks the same shape
(official API, a company gateway, a local proxy) works without code changes.
"""

from __future__ import annotations

from typing import Any, Dict

DEFAULT_BASE_URL = "https://api.openai.com/v1"
SUFFIX = "chat/completions"
LABEL = "OpenAI 兼容接口"


def endpoint(base_url: str) -> str:
    base = (base_url or DEFAULT_BASE_URL).strip().rstrip("/")
    if base.endswith("/" + SUFFIX):
        return base
    if base.endswith("/v1"):
        return base + "/" + SUFFIX
    return base + "/v1/" + SUFFIX


def headers(api_key: str) -> Dict[str, str]:
    return {"Authorization": "Bearer %s" % api_key}


def build_payload(model: str, system_prompt: str, user_prompt: str,
                  json_mode: bool = True) -> Dict[str, Any]:
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 1200,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    return payload


def extract_text(data: Dict[str, Any]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise KeyError("choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise KeyError("message")
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [block["text"] for block in content
                 if isinstance(block, dict) and isinstance(block.get("text"), str)]
        if parts:
            return "\n".join(parts)
    raise KeyError("content")
