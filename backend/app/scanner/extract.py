"""Deterministic evidence extraction from Markdown documents.

Everything in this module is rule-based and repeatable. No model is called and
no document is modified. Each extracted fact keeps its source path, heading,
line number, and a short excerpt so a user can verify it.

Deliberate limitations:

* Only dates that include a year are accepted.
* A line that reads like a plan ("计划", "预计", "target", "ETA") is treated as
  a schedule statement, not as a progress record. Plan statements never make a
  project look fresher than it is.
* "Testing" is only recognised from a phase heading, a status line, or a
  dedicated testing label, never from prose that merely mentions the word. This
  keeps a roadmap line such as "testing labels" from being read as a test run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple

from .dates import first_date, iter_dates, strip_leading_date, strip_separators
from .markdown_doc import Document, Section, section_block

# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
EMPHASIS_RE = re.compile(r"(\*\*|__|\*|_|`)")
INLINE_CODE_RE = re.compile(r"`([^`]*)`")
LIST_MARKER_RE = re.compile(r"^(?:[-*+]|\d+[.)])\s+")
CHECKBOX_RE = re.compile(r"^\s*[-*+]\s+\[(?P<mark>[ xX])\]\s+(?P<inner>.+?)\s*$")
MULTISPACE_RE = re.compile(r"\s+")


def clean_inline(text: str) -> str:
    value = IMAGE_RE.sub(r"\1", text)
    value = LINK_RE.sub(r"\1", value)
    value = INLINE_CODE_RE.sub(r"\1", value)
    value = EMPHASIS_RE.sub("", value)
    value = value.replace("&nbsp;", " ")
    return MULTISPACE_RE.sub(" ", value).strip()


def strip_line_marker(text: str) -> str:
    value = text.strip()
    if value.startswith("|"):
        value = value.strip("|")
    value = LIST_MARKER_RE.sub("", value)
    value = re.sub(r"^(?:>\s*)+", "", value)
    return value.strip()


def shorten(text: str, limit: int) -> str:
    value = MULTISPACE_RE.sub(" ", text).strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

PLAN_MARKERS_RE = re.compile(
    r"(?i)\b(?:plan|planned|planning|schedule[sd]?|scheduled|expected|target|targeted|eta|forecast|will|due)\b"
    r"|计划|预计|目标|排期|待定|拟定|预计完成"
)

CHANGE_MARKERS_RE = re.compile(
    r"(?i)\b(?:delay(?:ed|s)?|postpon\w*|reschedul\w*|moved|pushed|slipped|advanced|new target|revised)\b"
    r"|延期|推迟|提前|顺延|调整为|改为|改到|延至|改期"
)

PROJECT_SCHEDULE_RE = re.compile(
    r"(?i)\b(?:planned (?:start|end)|delivery date|release date|deadline|go-live date|launch date)\b"
    r"|计划(?:开始|结束|完成)(?:日期|时间)?|交付日期|上线日期|发布(?:日期|时间)|排期"
)

START_HINTS = (
    "start",
    "starts",
    "kickoff",
    "kick-off",
    "begins",
    "begin",
    "开始",
    "启动",
)
END_HINTS = (
    "end",
    "ends",
    "finish",
    "finishes",
    "delivery",
    "deliver",
    "release",
    "launch",
    "go-live",
    "deadline",
    "due",
    "ship",
    "结束",
    "完成日期",
    "交付",
    "上线",
    "发布",
    "投产",
    "截止",
)

TESTING_LABEL_RE = re.compile(
    r"(?i)(?:\b(?:testing|in testing|qa|uat|smoke test|under test)\b|测试中|测试阶段|转入测试)"
)
TESTING_CLAIM_RE = re.compile(
    r"(?i)(?:\bin testing\b|\bstarted qa\b|\bqa in progress\b|\btesting phase\b"
    r"|测试中|进入测试|开始测试|转入测试|联调测试)"
)

COMPLETED_RE = re.compile(
    r"(?i)\b(?:completed|complete|done|finished|shipped|released|delivered|implemented|landed|closed)\b"
    r"|已完成|完成|已结束|已交付|已实现|✅|✔"
)
CURRENT_RE = re.compile(
    r"(?i)\b(?:in progress|in-progress|ongoing|current|wip|active|started)\b|进行中|当前|正在进行|🚧|⏳"
)
UPCOMING_RE = re.compile(
    r"(?i)\b(?:not started|not-started|planned|upcoming|pending|todo|queued|next)\b|待开始|未开始|计划中|后续|⬜"
)
NOT_STARTED_RE = re.compile(
    r"(?i)\bnot(?:-|\s)?(?:yet\s)?started\b|未开始|尚未开始|还没开始|待开始"
)
NEGATED_RE = re.compile(r"(?i)not completed|incomplete|未完成|尚未完成")

PHASE_MENTION_RE = re.compile(
    r"(?i)phase\s*(?P<pnum>\d{1,2})"
    r"|第\s*(?P<cnum>[0-9一二三四五六七八九十]{1,3})\s*(?:阶段|步)"
    r"|阶段\s*(?P<anum>\d{1,2}|[一二三四五六七八九十]{1,3})"
)

PHASE_HEADING_RE = re.compile(
    r"^(?:phase|milestone|阶段|里程碑)\s*(?P<num>\d{1,2}|[一二三四五六七八九十]{1,3})"
    r"\s*[—–\-:：.、)]*\s*(?P<title>.*)$",
    re.I,
)

STATUS_KV_RE = re.compile(r"^\**\s*(?:status|state|progress|状态|进展)\s*\**\s*[:：]\s*(?P<value>.+)$", re.I)
START_KV_RE = re.compile(
    r"^\**\s*(?:start(?:ed)?|start date|begin(?:s)?|开始|起始)\s*\**\s*[:：]\s*(?P<value>.+)$", re.I
)
END_KV_RE = re.compile(
    r"^\**\s*(?:end(?:ed)?|end date|finish(?:ed)?|complete(?:d)?|结束|完成于|截止)\s*\**\s*[:：]\s*(?P<value>.+)$",
    re.I,
)
TESTING_KV_RE = re.compile(r"^\**\s*(?:testing|test status|测试|测试状态)\s*\**\s*[:：]\s*(?P<value>.+)$", re.I)
KV_DATE_RE = re.compile(
    r"^\**\s*(?:date|record(?:ed)?|updated|更新时间|日期|记录日期|时间)\s*\**\s*[:：]\s*(?P<value>.+)$", re.I
)

CN_NUMBERS = {
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

SCHEDULE_SECTION_RE = re.compile(r"(?i)schedule|timeline|milestone|排期|时间线|里程碑|计划")


def to_int(token: str) -> Optional[int]:
    if not token:
        return None
    token = token.strip()
    if token.isdigit():
        value = int(token)
    elif token in CN_NUMBERS:
        value = CN_NUMBERS[token]
    else:
        return None
    return value if 0 <= value <= 60 else None


def phase_mention(text: str) -> Tuple[Optional[int], str]:
    match = PHASE_MENTION_RE.search(text)
    if not match:
        return None, ""
    ordinal = to_int(match.group("pnum") or match.group("cnum") or match.group("anum") or "")
    return ordinal, clean_inline(match.group(0))


def classify_status(text: str) -> str:
    value = text.strip()
    if not value:
        return "unknown"
    if NEGATED_RE.search(value):
        return "unknown"
    if COMPLETED_RE.search(value):
        return "completed"
    # "Not started" contains "started"; check the negation before "current".
    if NOT_STARTED_RE.search(value):
        return "upcoming"
    if CURRENT_RE.search(value):
        return "current"
    if UPCOMING_RE.search(value):
        return "upcoming"
    return "unknown"


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass
class ProgressRecord:
    source_path: str
    line: int
    record_date: date
    claim: str
    heading: str
    excerpt: str
    planned: bool
    phase_ordinal: Optional[int] = None
    phase_raw: str = ""


@dataclass
class PhaseCandidate:
    source_path: str
    heading: str
    order: int
    ordinal: int
    name: str
    status: str
    start: Optional[date]
    end: Optional[date]
    testing: bool
    status_raw: str
    status_values: List[str]


@dataclass
class ScheduleProposal:
    source_path: str
    field: str
    candidate: date
    record_date: Optional[date]
    claim: str
    excerpt: str


def _progress_from_line(text: str, section: Section, source_path: str, line: int) -> Optional[ProgressRecord]:
    body = strip_line_marker(text)
    if not body:
        return None

    record_date: Optional[date] = None
    remainder = ""

    kv = KV_DATE_RE.match(body)
    if kv:
        hit = iter_dates(kv.group("value"))
        if hit:
            record_date = hit[0].value
            remainder = kv.group("value")[hit[0].end:]

    if record_date is None:
        hit, rest = strip_leading_date(body)
        if hit is None:
            return None
        record_date = hit.value
        remainder = rest

    claim = strip_separators(clean_inline(remainder)).strip(" .,;；。")
    planned = bool(PLAN_MARKERS_RE.search(claim))
    ordinal, raw = phase_mention(claim)
    heading = " / ".join(section.path)

    return ProgressRecord(
        source_path=source_path,
        line=line,
        record_date=record_date,
        claim=shorten(claim, 300),
        heading=heading,
        excerpt=shorten(clean_inline(text), 220),
        planned=planned,
        phase_ordinal=ordinal,
        phase_raw=raw,
    )


def extract_progress(document: Document) -> List[ProgressRecord]:
    records: List[ProgressRecord] = []
    for index, section in enumerate(document.sections):
        if section.heading and section.level >= 2:
            heading_body = strip_line_marker(section.heading)
            hit, rest = strip_leading_date(heading_body)
            if hit is not None:
                heading_claim = strip_separators(clean_inline(rest)).strip(" .,;；。")
                # A dated heading usually introduces several bullets. Each bullet
                # is kept as its own record so two contradictory statements on the
                # same day stay visible instead of being merged away.
                entries: List[str] = []
                for _, line in section.lines:
                    if not line.strip() or line.strip().startswith("|"):
                        continue
                    text = clean_inline(strip_line_marker(line))
                    if text and text not in entries:
                        entries.append(text)
                    if len(entries) >= 8:
                        break
                if not entries:
                    entries = [heading_claim] if heading_claim else []
                for entry in entries:
                    ordinal, raw = phase_mention(entry)
                    records.append(
                        ProgressRecord(
                            source_path=document.relative_path,
                            line=0,
                            record_date=hit.value,
                            claim=shorten(entry, 300),
                            heading=" / ".join(section.path),
                            excerpt=shorten(clean_inline(section.heading), 220),
                            planned=bool(PLAN_MARKERS_RE.search(entry)),
                            phase_ordinal=ordinal,
                            phase_raw=raw,
                        )
                    )

        for position, (line_number, raw) in enumerate(section.lines):
            record = _progress_from_line(raw, section, document.relative_path, line_number)
            if record is None:
                continue
            if not record.claim:
                for _, following in section.lines[position + 1:]:
                    if following.strip():
                        record.claim = shorten(clean_inline(strip_line_marker(following)), 300)
                        record.planned = bool(PLAN_MARKERS_RE.search(record.claim))
                        break
            if not record.claim:
                continue
            records.append(record)

    seen = set()
    unique: List[ProgressRecord] = []
    for record in records:
        key = (record.source_path, record.line, record.record_date, record.claim)
        if key in seen:
            continue
        seen.add(key)
        unique.append(record)
    return unique


# ---------------------------------------------------------------------------
# Phases
# ---------------------------------------------------------------------------


def _clean_phase_name(title: str) -> str:
    value = clean_inline(title)
    value = re.sub(
        r"[（(][^）)]*(?:completed|complete|完成|in progress|进行中|done|已)[^）)]*[）)]\s*$", "", value, flags=re.I
    )
    value = re.sub(r"(?:status|状态)\s*[:：].*$", "", value, flags=re.I)
    return value.strip(" —–-:：.、|")


def _phase_from_heading(
    match: "re.Match", section: Section, block: List[tuple], source_path: str, order: int
) -> Optional[PhaseCandidate]:
    ordinal = to_int(match.group("num"))
    if ordinal is None:
        return None
    raw_title = match.group("title") or ""
    name = _clean_phase_name(raw_title)

    status_values: List[str] = []
    start: Optional[date] = None
    end: Optional[date] = None
    testing = bool(TESTING_LABEL_RE.search(clean_inline(raw_title)))

    for _, raw in block:
        text = strip_line_marker(raw)
        if not text:
            continue
        status_kv = STATUS_KV_RE.match(text)
        if status_kv:
            value = clean_inline(status_kv.group("value"))
            status_values.append(value)
            if TESTING_LABEL_RE.search(value):
                testing = True
            dates = iter_dates(value)
            status = classify_status(value)
            if len(dates) >= 2:
                start = start or dates[0].value
                end = end or dates[1].value
            elif len(dates) == 1:
                # A single date only maps to a known field when the status says
                # which one it is. An "upcoming" phase with a target date keeps
                # unknown dates instead of guessing a start.
                if status == "completed":
                    end = end or dates[0].value
                elif status == "current":
                    start = start or dates[0].value
            continue

        start_kv = START_KV_RE.match(text)
        if start_kv:
            value = first_date(start_kv.group("value"))
            if value:
                start = start or value
            continue

        end_kv = END_KV_RE.match(text)
        if end_kv:
            value = first_date(end_kv.group("value"))
            if value:
                end = end or value
            continue

        testing_kv = TESTING_KV_RE.match(text)
        if testing_kv:
            if re.search(r"(?i)\b(?:yes|true|in progress|ongoing)\b|是|在测试|测试中", testing_kv.group("value")):
                testing = True

    heading_status = classify_status(clean_inline(raw_title))
    explicit = {classify_status(value) for value in status_values} - {"unknown"}
    if len(explicit) == 1:
        status = explicit.pop()
    elif len(explicit) > 1:
        status = "conflict"
    else:
        status = heading_status

    heading_dates = iter_dates(clean_inline(raw_title))
    if len(heading_dates) >= 2 and start is None and end is None:
        start, end = heading_dates[0].value, heading_dates[1].value

    return PhaseCandidate(
        source_path=source_path,
        heading=section.heading,
        order=order,
        ordinal=ordinal,
        name=name or f"Phase {ordinal}",
        status=status,
        start=start,
        end=end,
        testing=testing,
        status_raw="；".join(status_values[:2]),
        status_values=status_values,
    )


def extract_phases(document: Document) -> List[PhaseCandidate]:
    candidates: List[PhaseCandidate] = []
    order = 0
    for index, section in enumerate(document.sections):
        if section.heading:
            match = PHASE_HEADING_RE.match(strip_line_marker(section.heading))
            if match:
                block = section_block(document.sections, index)
                candidate = _phase_from_heading(match, section, block, document.relative_path, order)
                order += 1
                if candidate:
                    candidates.append(candidate)

        for _, raw in section.lines:
            checkbox = CHECKBOX_RE.match(raw)
            if not checkbox:
                continue
            match = PHASE_HEADING_RE.match(clean_inline(checkbox.group("inner")))
            if not match:
                continue
            ordinal = to_int(match.group("num"))
            if ordinal is None:
                continue
            done = checkbox.group("mark").lower() == "x"
            candidates.append(
                PhaseCandidate(
                    source_path=document.relative_path,
                    heading=section.heading,
                    order=order,
                    ordinal=ordinal,
                    name=_clean_phase_name(match.group("title") or "") or f"Phase {ordinal}",
                    status="completed" if done else "upcoming",
                    start=None,
                    end=None,
                    testing=bool(TESTING_LABEL_RE.search(checkbox.group("inner"))),
                    status_raw=checkbox.group("inner"),
                    status_values=[checkbox.group("inner")],
                )
            )
            order += 1
    return candidates


# ---------------------------------------------------------------------------
# Summary and schedule statements
# ---------------------------------------------------------------------------

SUMMARY_LIMIT = 420
SKIP_PARAGRAPH_PREFIXES = ("#", "|", "-", "*", "+", ">", "!", "<", "```", "~~~", "---", "===")


def extract_summary(document: Document) -> str:
    sections = document.sections
    primary = [section for section in sections if section.level == 1] or sections
    for section in primary:
        paragraph: List[str] = []
        for _, raw in section.lines:
            text = raw.strip()
            if not text:
                if paragraph:
                    candidate = clean_inline(" ".join(paragraph))
                    if len(candidate) >= 30:
                        return shorten(candidate, SUMMARY_LIMIT)
                    paragraph = []
                continue
            if text.startswith(SKIP_PARAGRAPH_PREFIXES):
                continue
            paragraph.append(text)
        if paragraph:
            candidate = clean_inline(" ".join(paragraph))
            if len(candidate) >= 30:
                return shorten(candidate, SUMMARY_LIMIT)
    return ""


def _schedule_field(claim: str) -> Optional[str]:
    lowered = claim.lower()
    has_start = any(hint in lowered for hint in START_HINTS)
    has_end = any(hint in lowered for hint in END_HINTS)
    if has_start and has_end:
        return None
    if has_start:
        return "planned_start"
    if has_end:
        return "planned_end"
    if CHANGE_MARKERS_RE.search(lowered):
        return "planned_end"
    return None


def extract_schedule_from_records(records: List[ProgressRecord]) -> List[ScheduleProposal]:
    proposals: List[ScheduleProposal] = []
    for record in records:
        # A schedule proposal is only created when the text actually talks about
        # the project's own schedule or about a delay. A roadmap line such as
        # "plan to start Phase 3 in 2026-11" is a phase plan, not a schedule
        # change, and must not become a pending confirmation.
        if not (PROJECT_SCHEDULE_RE.search(record.claim) or CHANGE_MARKERS_RE.search(record.claim)):
            continue
        dates = iter_dates(record.claim)
        if not dates:
            continue
        field = _schedule_field(record.claim)
        if field is None:
            continue
        for hit in dates:
            proposals.append(
                ScheduleProposal(
                    source_path=record.source_path,
                    field=field,
                    candidate=hit.value,
                    record_date=record.record_date,
                    claim=record.claim,
                    excerpt=record.excerpt,
                )
            )
    return proposals


def extract_schedule_from_lines(document: Document) -> List[ScheduleProposal]:
    proposals: List[ScheduleProposal] = []
    for index, section in enumerate(document.sections):
        if not section.heading or not SCHEDULE_SECTION_RE.search(section.heading):
            continue
        for _, raw in section_block(document.sections, index):
            text = clean_inline(strip_line_marker(raw))
            if not text or not CHANGE_MARKERS_RE.search(text):
                continue
            field = _schedule_field(text)
            if field is None:
                continue
            for hit in iter_dates(text):
                proposals.append(
                    ScheduleProposal(
                        source_path=document.relative_path,
                        field=field,
                        candidate=hit.value,
                        record_date=None,
                        claim=shorten(text, 300),
                        excerpt=shorten(text, 220),
                    )
                )
    return proposals


def testing_in_claim(claim: str) -> bool:
    return bool(TESTING_CLAIM_RE.search(claim))
