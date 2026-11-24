"""Model provider configuration and connectivity test."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException

from .. import config_store, secrets_store
from ..providers import client
from ..schemas import ProviderInput, as_dict

router = APIRouter(prefix="/api")


def _merged_for_test(payload: Optional[ProviderInput]) -> Dict[str, Any]:
    runtime = config_store.runtime()
    if payload is None:
        return runtime
    data = as_dict(payload)
    provider = (data.get("provider") or runtime["provider"]).strip().lower()
    if provider not in config_store.PROVIDERS:
        raise HTTPException(status_code=400, detail="未知的模型服务商")
    runtime["provider"] = provider
    base_url = (data.get("base_url") if data.get("base_url") is not None
                else runtime.get("base_url") or "")
    base_url = (base_url or "").strip().rstrip("/")
    if base_url:
        from urllib.parse import urlparse
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise HTTPException(status_code=400,
                                detail="接口地址需要以 http:// 或 https:// 开头")
    runtime["base_url"] = base_url
    runtime["effective_base_url"] = base_url or \
        config_store.PROVIDERS[provider]["default_base_url"]
    if data.get("model") is not None:
        runtime["model"] = data["model"].strip()
    if data.get("json_mode") is not None:
        runtime["json_mode"] = bool(data["json_mode"])
    if data.get("api_key"):
        runtime["transient_key"] = data["api_key"].strip()
    return runtime


@router.get("/provider")
def get_provider() -> Dict[str, Any]:
    return config_store.get_settings()


@router.put("/provider")
def put_provider(payload: ProviderInput) -> Dict[str, Any]:
    try:
        return config_store.save_settings(as_dict(payload))
    except config_store.ConfigError as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.post("/provider/test")
def test_provider(payload: Optional[ProviderInput] = None) -> Dict[str, Any]:
    merged = _merged_for_test(payload)
    if not merged.get("model"):
        raise HTTPException(status_code=400, detail="先填模型名再测试连接")
    if not (merged.get("transient_key") or merged.get("api_key_set")):
        raise HTTPException(status_code=400, detail="先填 API 密钥再测试连接")

    ok, message, elapsed = client.ping(merged)
    if payload is None:
        config_store.remember_test(ok, message)
    return {
        "ok": ok,
        "message": secrets_store.redact(message),
        "latency_ms": elapsed,
        "model": merged.get("model", ""),
        "endpoint": merged.get("effective_base_url", ""),
    }
