"""Select the smallest useful evidence bundle for a model call.

Only short excerpts are sent, never whole documents, and every source is a
path relative to the registered project folder. The bundle is the single
thing the model is allowed to reason about, which also makes validation
precise: a citation must point at an item in this list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List

MAX_ITEMS = 14
MAX_ITEM_CHARS = 600
MAX_TOTAL_CHARS = 6000
MAX_PROGRESS = 6
MAX_PHASE_ITEMS = 6
MAX_SCHEDULE = 3

DATE_ONLY = re.compile(r"^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}$")


@dataclass
class BundleItem:
    id: str
    kind: str
    source: str
    heading: str
    date: str
    text: str

    def as_payload(self) -> Dict[str, str]:
        return {
            "id": self.id,
            "kind": self.kind,
            "source": self.source,
            "heading": self.heading,
            "date": self.date,
            "text": self.text,
        }


@dataclass
class Bundle:
    items: List[BundleItem] = field(default_factory=list)
    dropped: int = 0

    @property
    def char_count(self) -> int:
        return sum(len(item.text) + len(item.heading) + len(item.source) for item in self.items)

    def by_id(self) -> Dict[str, BundleItem]:
        return {item.id: item for item in self.items}

    def as_payload(self) -> List[Dict[str, str]]:
        return [item.as_payload() for item in self.items]

    def is_empty(self) -> bool:
        return not self.items


def _clean(value: Any, limit: int) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.split())
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text


def _take(items: Iterable[Any], limit: int, seen: set) -> List[Any]:
    picked = []
    for item in items:
        if len(picked) >= limit:
            break
        key = (item.kind, item.source_path, item.claim)
        if key in seen:
            continue
        if not (item.excerpt or item.claim):
            continue
        seen.add(key)
        picked.append(item)
    return picked


def _item_text(item: Any) -> str:
    """Pick the sentence the model should read, not just the date line.

    Progress evidence stores the heading date in ``excerpt`` and the actual
    sentence in ``claim``; sending only the date would give the model nothing
    to reason about. Phase evidence needs its heading because the status line
    alone does not name the phase.
    """
    claim = (item.claim or "").strip()
    excerpt = (item.excerpt or "").strip()
    if item.kind == "phase_status":
        body = excerpt or claim
        if item.heading and body:
            return f"{item.heading}｜{body}"
        return item.heading or body
    if item.kind in ("progress", "schedule"):
        if excerpt and excerpt not in claim and not DATE_ONLY.match(excerpt):
            return f"{claim}｜{excerpt}" if claim else excerpt
        return claim or excerpt
    return excerpt or claim


def build_bundle(candidate: Any) -> Bundle:
    """Pick summary, newest progress, phase labels, and schedule statements."""
    evidence = list(getattr(candidate, "evidence", []) or [])
    summary = [item for item in evidence if item.kind == "summary"]
    progress = [item for item in evidence if item.kind == "progress"]
    phase_items = [item for item in evidence if item.kind == "phase_status"]
    schedule = [item for item in evidence if item.kind == "schedule"]

    seen: set = set()
    ordered: List[Any] = []
    ordered.extend(_take(summary, 1, seen))
    ordered.extend(_take(progress, MAX_PROGRESS, seen))
    ordered.extend(_take(phase_items, MAX_PHASE_ITEMS, seen))
    ordered.extend(_take(schedule, MAX_SCHEDULE, seen))

    bundle = Bundle()
    total = 0
    for index, item in enumerate(ordered, start=1):
        if len(bundle.items) >= MAX_ITEMS:
            bundle.dropped += len(ordered) - index + 1
            break
        text = _clean(_item_text(item), MAX_ITEM_CHARS)
        if not text:
            continue
        if total + len(text) > MAX_TOTAL_CHARS:
            bundle.dropped += 1
            continue
        total += len(text)
        bundle.items.append(
            BundleItem(
                id=f"E{len(bundle.items) + 1}",
                kind=str(item.kind),
                source=_clean(item.source_path, 200),
                heading=_clean(item.heading, 120),
                date=item.record_date.isoformat() if item.record_date else "",
                text=text,
            )
        )
    return bundle
