"""Structured-output contract and validation.

The model's answer is untrusted input. Before anything is stored, this module
checks that:

* the response parses as a JSON object;
* every citation points at an evidence id that was actually sent;
* every quote appears verbatim in that evidence item;
* a claimed phase number is present in its own citation;
* a claimed schedule date appears in the evidence it cites;
* each conclusion carries the citation kind it requires.

Any failure raises :class:`ModelValidationError` with a message precise enough
for the user to fix the prompt, the model, or the source document.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional

from .bundle import Bundle

ALLOWED_ZONE = re.compile(r"[`*_#>~]+")
WHITESPACE = re.compile(r"\s+")
FENCE = re.compile(r"^```[A-Za-z0-9_-]*\s*|\s*```$")

ALLOWED_SUPPORTS = {
    "current_phase",
    "testing",
    "summary",
    "schedule",
    "conflict",
    "phase_status",
}
ALLOWED_FIELDS = {"planned_start", "planned_end"}
ALLOWED_PHASE_STATUS = {"completed", "in_progress", "upcoming", "unknown"}
ALLOWED_CONFIDENCE = {"high", "medium", "low"}

CHINESE_DIGITS = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


class ModelValidationError(ValueError):
    """The provider answered, but not in a form that can be trusted."""


@dataclass
class Citation:
    evidence_id: str
    quote: str
    supports: str
    source: str


@dataclass
class ScheduleClaim:
    field: str
    target: date
    reason: str


@dataclass
class ModelResult:
    ordinal: Optional[int]
    phase_name: Optional[str]
    phase_status: str
    testing: bool
    summary: str
    schedule_changes: List[ScheduleClaim]
    conflicts: List[str]
    citations: List[Citation]
    confidence: str = "low"

    def citation_for(self, supports: str) -> Optional[Citation]:
        for citation in self.citations:
            if citation.supports == supports:
                return citation
        return None


def _normalize(text: str) -> str:
    """Compare quotes ignoring whitespace, case, and Markdown emphasis."""
    cleaned = text.replace("\u3000", " ")
    cleaned = ALLOWED_ZONE.sub("", cleaned)
    cleaned = WHITESPACE.sub("", cleaned)
    return cleaned.lower()


def _strip_fence(text: str) -> str:
    value = text.strip()
    value = FENCE.sub("", value).strip()
    if value.startswith("```"):
        value = re.sub(r"^```[A-Za-z0-9_-]*", "", value).strip()
    if value.endswith("```"):
        value = value[:-3].strip()
    return value


def parse_object(text: str) -> Dict[str, Any]:
    if not text or not text.strip():
        raise ModelValidationError("模型返回了空内容")
    cleaned = _strip_fence(text)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ModelValidationError("模型响应不是 JSON 对象（未找到花括号）")
    snippet = cleaned[start : end + 1]
    try:
        payload = json.loads(snippet)
    except ValueError as error:
        raise ModelValidationError(f"模型响应不是合法 JSON（{error.msg}）")
    if not isinstance(payload, dict):
        raise ModelValidationError("模型响应的顶层不是 JSON 对象")
    return payload


def _as_optional_int(value: Any, label: str) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ModelValidationError(f"{label} 不能是布尔值")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    raise ModelValidationError(f"{label} 不是整数")


def _as_text(value: Any, limit: int = 0) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ModelValidationError("文本字段类型不正确")
    result = " ".join(value.split())
    return result[:limit] if limit else result


def _as_list(value: Any, label: str) -> List[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ModelValidationError(f"{label} 需要是数组")
    return value


def ordinal_in_text(text: str, ordinal: int) -> bool:
    if re.search(r"(?<!\d)%d(?!\d)" % ordinal, text):
        return True
    for character, value in CHINESE_DIGITS.items():
        if value == ordinal and character in text:
            return True
    return False


def date_appears_in(text: str, target: date) -> bool:
    compact = WHITESPACE.sub("", text)
    year, month, day = target.year, target.month, target.day
    candidates = [
        f"{year}-{month:02d}-{day:02d}",
        f"{year}/{month:02d}/{day:02d}",
        f"{year}/{month}/{day}",
        f"{year}.{month:02d}.{day:02d}",
        f"{year}.{month}.{day}",
        f"{year}年{month}月{day}日",
        f"{year}年{month:02d}月{day:02d}日",
    ]
    return any(candidate in compact for candidate in candidates)


def validate(payload: Dict[str, Any], bundle: Bundle) -> ModelResult:
    items = bundle.by_id()

    citations: List[Citation] = []
    raw_citations = _as_list(payload.get("citations"), "citations")
    for raw in raw_citations:
        if not isinstance(raw, dict):
            raise ModelValidationError("citations 中的条目需要是对象")
        evidence_id = _as_text(raw.get("evidence_id"), 20)
        if not evidence_id or evidence_id not in items:
            raise ModelValidationError(f"引用 {evidence_id or '(空)'} 不在发送给模型的证据中")
        item = items[evidence_id]
        quote = _as_text(raw.get("quote"), 400)
        if len(_normalize(quote)) < 4:
            raise ModelValidationError(f"引用 {evidence_id} 的引文过短，无法核对")
        if _normalize(quote) not in _normalize(item.text):
            raise ModelValidationError(f"引用 {evidence_id} 的引文在证据原文中找不到：{quote[:36]}")
        supports = _as_text(raw.get("supports"), 30)
        if supports not in ALLOWED_SUPPORTS:
            raise ModelValidationError(f"引用 {evidence_id} 的 supports 取值无法识别：{supports or '(空)'}")
        citations.append(Citation(evidence_id=evidence_id, quote=quote, supports=supports, source=item.source))

    ordinal = _as_optional_int(payload.get("current_phase_ordinal"), "current_phase_ordinal")
    if ordinal is not None:
        if ordinal < 1 or ordinal > 99:
            raise ModelValidationError("current_phase_ordinal 超出合理范围")
        current_citations = [item for item in citations if item.supports == "current_phase"]
        if not current_citations:
            raise ModelValidationError("结论给出当前阶段，但没有 supports=\"current_phase\" 的证据引用")
        if not any(ordinal_in_text(citation.quote, ordinal) or ordinal_in_text(items[citation.evidence_id].text, ordinal)
                   for citation in current_citations):
            raise ModelValidationError(f"引用的证据里没有出现阶段编号 {ordinal}")

    phase_name = _as_text(payload.get("current_phase_name"), 120) or None

    phase_status = _as_text(payload.get("phase_status"), 30) or "unknown"
    if phase_status not in ALLOWED_PHASE_STATUS:
        phase_status = "unknown"

    testing_raw = payload.get("testing")
    if testing_raw is None:
        testing = False
    elif isinstance(testing_raw, bool):
        testing = testing_raw
    else:
        raise ModelValidationError("testing 需要是布尔值")
    if testing and not any(item.supports == "testing" for item in citations):
        raise ModelValidationError("判定为测试中，但没有 supports=\"testing\" 的证据引用")

    summary = _as_text(payload.get("summary"), 600)
    if summary and not any(item.supports == "summary" for item in citations):
        raise ModelValidationError("给出了项目简介，但没有 supports=\"summary\" 的证据引用")

    schedule_changes: List[ScheduleClaim] = []
    schedule_citations = [item for item in citations if item.supports == "schedule"]
    for raw in _as_list(payload.get("schedule_changes"), "schedule_changes"):
        if not isinstance(raw, dict):
            raise ModelValidationError("schedule_changes 中的条目需要是对象")
        field_name = _as_text(raw.get("field"), 30)
        if field_name not in ALLOWED_FIELDS:
            raise ModelValidationError(f"排期字段无法识别：{field_name or '(空)'}")
        raw_date = _as_text(raw.get("date"), 20)
        try:
            target = date.fromisoformat(raw_date)
        except ValueError:
            raise ModelValidationError(f"排期日期不是 YYYY-MM-DD：{raw_date or '(空)'}")
        if target.year < 1990 or target.year > 2100:
            raise ModelValidationError("排期日期超出合理范围")
        if not schedule_citations:
            raise ModelValidationError("提出了排期变更，但没有 supports=\"schedule\" 的证据引用")
        if not any(date_appears_in(items[item.evidence_id].text, target) for item in schedule_citations):
            raise ModelValidationError(f"排期日期 {target.isoformat()} 在引用的证据原文中没有出现")
        schedule_changes.append(
            ScheduleClaim(field=field_name, target=target, reason=_as_text(raw.get("reason"), 300))
        )

    conflicts = []
    for raw in _as_list(payload.get("conflicts"), "conflicts"):
        text = _as_text(raw, 300)
        if text:
            conflicts.append(text)
    if conflicts and not any(item.supports == "conflict" for item in citations):
        raise ModelValidationError("列出了证据冲突，但没有 supports=\"conflict\" 的证据引用")

    confidence = _as_text(payload.get("confidence"), 20) or "low"
    if confidence not in ALLOWED_CONFIDENCE:
        confidence = "low"

    return ModelResult(
        ordinal=ordinal,
        phase_name=phase_name,
        phase_status=phase_status,
        testing=testing,
        summary=summary,
        schedule_changes=schedule_changes,
        conflicts=conflicts,
        citations=citations,
        confidence=confidence,
    )
