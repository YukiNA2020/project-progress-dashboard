"""Anthropic Messages API adapter."""

from __future__ import annotations

from typing import Any, Dict

DEFAULT_BASE_URL = "https://api.anthropic.com/v1"
SUFFIX = "messages"
API_VERSION = "2023-06-01"


def endpoint(base_url: str) -> str:
    base = (base_url or DEFAULT_BASE_URL).strip().rstrip("/")
    if base.endswith("/" + SUFFIX):
        return base
    if base.endswith("/v1"):
        return base + "/" + SUFFIX
    return base + "/v1/" + SUFFIX


def headers(api_key: str) -> Dict[str, str]:
    return {"x-api-key": api_key, "anthropic-version": API_VERSION}


def build_payload(model: str, system_prompt: str, user_prompt: str, json_mode: bool = True) -> Dict[str, Any]:
    # Anthropic has no JSON response mode; the prompt carries the contract and
    # the response is validated the same way as OpenAI's.
    _ = json_mode
    return {
        "model": model,
        "max_tokens": 1200,
        "temperature": 0,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }


def extract_text(data: Dict[str, Any]) -> str:
    blocks = data.get("content")
    if not isinstance(blocks, list) or not blocks:
        raise KeyError("content")
    parts = []
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
            parts.append(block["text"])
    if not parts:
        raise KeyError("text")
    return "\n".join(parts)
