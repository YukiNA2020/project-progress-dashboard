"""One model call: select evidence, ask, parse, validate."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, Optional

from . import client
from .bundle import Bundle, build_bundle
from .prompt import SYSTEM_PROMPT, build_prompt
from .schema import ModelResult, ModelValidationError, parse_object, validate
from .transport import ProviderError


@dataclass
class ModelOutcome:
    status: str  # ok | invalid | failed | skipped
    result: Optional[ModelResult] = None
    error: str = ""
    provider: str = ""
    model: str = ""
    confidence: str = ""
    item_count: int = 0
    bundle_chars: int = 0
    citations: list = field(default_factory=list)


def analyze(candidate: Any, project: Dict[str, Any], settings: Dict[str, Any], today: date) -> ModelOutcome:
    provider = settings.get("provider", "")
    model = settings.get("model", "")
    bundle: Bundle = build_bundle(candidate)
    if bundle.is_empty():
        return ModelOutcome(
            status="skipped",
            error="没有可发送给模型的证据",
            provider=provider,
            model=model,
        )

    prompt = build_prompt(bundle, project, today)
    try:
        text = client.complete(settings, SYSTEM_PROMPT, prompt)
    except ProviderError as error:
        return ModelOutcome(
            status="failed",
            error=str(error),
            provider=provider,
            model=model,
            item_count=len(bundle.items),
            bundle_chars=len(prompt),
        )
    except Exception as error:  # noqa: BLE001 - provider bugs must stay contained
        return ModelOutcome(
            status="failed",
            error=f"调用模型时出现未预期的错误（{type(error).__name__}）",
            provider=provider,
            model=model,
            item_count=len(bundle.items),
            bundle_chars=len(prompt),
        )

    try:
        payload = parse_object(text)
        result = validate(payload, bundle)
    except ModelValidationError as error:
        return ModelOutcome(
            status="invalid",
            error=str(error),
            provider=provider,
            model=model,
            item_count=len(bundle.items),
            bundle_chars=len(prompt),
        )

    return ModelOutcome(
        status="ok",
        result=result,
        provider=provider,
        model=model,
        confidence=result.confidence,
        item_count=len(bundle.items),
        bundle_chars=len(prompt),
        citations=result.citations,
    )
