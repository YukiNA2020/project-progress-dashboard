"""Date recognition.

Only dates with an explicit year are recognised. Partial dates such as
"11月5日" or "next Friday" are ignored on purpose: the year cannot be
established without guessing, and the product rules forbid inference.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple

_FULL_PATTERNS = (
    re.compile(r"(?<!\d)(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)"),
    re.compile(r"(?<!\d)(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]"),
)

MIN_YEAR = 1990
MAX_YEAR = 2100


@dataclass(frozen=True)
class DateHit:
    value: date
    start: int
    end: int


def iter_dates(text: str) -> List[DateHit]:
    hits: List[DateHit] = []
    for pattern in _FULL_PATTERNS:
        for match in pattern.finditer(text):
            try:
                value = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                continue
            if value.year < MIN_YEAR or value.year > MAX_YEAR:
                continue
            hits.append(DateHit(value=value, start=match.start(), end=match.end()))
    hits.sort(key=lambda hit: hit.start)
    deduped: List[DateHit] = []
    for hit in hits:
        if deduped and hit.start < deduped[-1].end:
            continue
        deduped.append(hit)
    return deduped


def first_date(text: str) -> Optional[date]:
    hits = iter_dates(text)
    return hits[0].value if hits else None


def strip_leading_date(text: str) -> Tuple[Optional[DateHit], str]:
    """Return a date that starts the line plus the remainder, if any."""
    for pattern in _FULL_PATTERNS:
        match = pattern.match(text)
        if not match:
            continue
        try:
            value = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None, text
        if value.year < MIN_YEAR or value.year > MAX_YEAR:
            return None, text
        remainder = text[match.end():]
        if re.match(r"(?i)^[t\s]?\d{1,2}:\d{2}", remainder) and not remainder.startswith((" ", "\t")):
            # Timestamp such as 2026-10-29T09:30, not a dated progress entry.
            return None, text
        return DateHit(value=value, start=0, end=match.end()), remainder
    return None, text


SEPARATOR_CHARS = ":：—–-－,，。.;；)）]】|/、"


def strip_separators(text: str) -> str:
    return text.lstrip(" \t" + SEPARATOR_CHARS)
