"""Turn extracted evidence into one candidate project state.

This module owns the trust rules:

* The newest *explicitly dated* progress record decides freshness. File
  modification times are never consulted.
* A phase counts as "current" only when the documents say so: an explicit
  in-progress marker, an explicit "entered Phase N" statement, or (as a clearly
  labelled fallback) a completed prefix in the phase list.
* Any disagreement between sources becomes a "needs confirmation" outcome with
  the reasons spelled out. Nothing is guessed and nothing is silently replaced.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .discovery import Discovery
from .extract import (
    ProgressRecord,
    ScheduleProposal,
    extract_phases,
    extract_progress,
    extract_schedule_from_lines,
    extract_schedule_from_records,
    extract_summary,
    phase_mention,
    testing_in_claim,
)
from .markdown_doc import Document

MAX_EVIDENCE = 40

FORWARD_PHASE_RE = re.compile(
    r"(?i)(?:进入|转入|开始|启动|推进到|推进至|现在在|目前处于|处于|当前)\s*(?:第\s*)?(?:phase|阶段)?[^\n]{0,4}$"
    r"|(?:entered|entering|started|starting|moved to|now in|working on|kicked off|in progress on)\s*$"
)
BACKWARD_PHASE_RE = re.compile(r"(?i)(?:完成|已完成|completed?|finished|wrapped up)\s*$")


@dataclass
class Phase:
    ordinal: int
    name: str
    status: str
    start: Optional[date] = None
    end: Optional[date] = None
    testing: bool = False
    source_path: str = ""
    source_heading: str = ""
    status_raw: str = ""


@dataclass
class EvidenceItem:
    kind: str
    source_path: str
    heading: str
    record_date: Optional[date]
    claim: str
    excerpt: str
    is_newest: bool = False


@dataclass
class Candidate:
    status: str
    reason: str
    summary: str
    summary_source: str
    phases: List[Phase]
    current: Optional[Phase]
    basis: str
    testing: bool
    newest: Optional[ProgressRecord]
    evidence: List[EvidenceItem]
    proposals: List[ScheduleProposal]
    notes: List[str] = field(default_factory=list)
    files_scanned: int = 0


def _document_priority(document: Document) -> tuple:
    """Root README first, then shallow READMEs, then everything else."""
    name = document.relative_path.rsplit("/", 1)[-1].lower()
    depth = document.relative_path.count("/")
    return (0 if name.startswith("readme") else 1, depth, document.relative_path.lower())


def merge_phases(documents: Sequence[Document]) -> Tuple[List[Phase], List[str]]:
    merged: Dict[int, dict] = {}
    conflicts: List[str] = []

    for document in documents:
        for candidate in extract_phases(document):
            entry = merged.get(candidate.ordinal)
            if entry is None:
                entry = {
                    "ordinal": candidate.ordinal,
                    "name": "",
                    "statuses": [],
                    "start": None,
                    "end": None,
                    "testing": False,
                    "source_path": candidate.source_path,
                    "source_heading": candidate.heading,
                    "status_raw": candidate.status_raw,
                }
                merged[candidate.ordinal] = entry
            if not entry["name"] and candidate.name:
                entry["name"] = candidate.name
            status = candidate.status
            if status not in ("unknown", "conflict"):
                entry["statuses"].append(status)
            if candidate.start and entry["start"] is None:
                entry["start"] = candidate.start
            elif candidate.start and entry["start"] and candidate.start != entry["start"]:
                conflicts.append(
                    f"阶段 {candidate.ordinal} 的开始日期在不同文档中不一致（{entry['start']} / {candidate.start}）"
                )
            if candidate.end and entry["end"] is None:
                entry["end"] = candidate.end
            elif candidate.end and entry["end"] and candidate.end != entry["end"]:
                conflicts.append(
                    f"阶段 {candidate.ordinal} 的结束日期在不同文档中不一致（{entry['end']} / {candidate.end}）"
                )
            if candidate.testing:
                entry["testing"] = True
            if candidate.status_raw and not entry["status_raw"]:
                entry["status_raw"] = candidate.status_raw

    phases: List[Phase] = []
    for ordinal in sorted(merged):
        entry = merged[ordinal]
        statuses = set(entry["statuses"])
        if len(statuses) == 1:
            status = statuses.pop()
        elif len(statuses) > 1:
            status = "conflict"
            conflicts.append(f"阶段 {ordinal} 在两个文档中的状态互相矛盾（{' / '.join(sorted(statuses))}）")
        else:
            status = "unknown"
        phases.append(
            Phase(
                ordinal=ordinal,
                name=entry["name"] or f"Phase {ordinal}",
                status=status,
                start=entry["start"],
                end=entry["end"],
                testing=entry["testing"],
                source_path=entry["source_path"],
                source_heading=entry["source_heading"],
                status_raw=entry["status_raw"],
            )
        )
    return phases, conflicts


def _phase_forward_mention(claim: str) -> Optional[int]:
    """Return the phase the record says it *entered*, not one it finished."""
    hits: List[Tuple[int, int]] = []
    for match in re.finditer(
        r"(?i)phase\s*(\d{1,2})|第\s*([0-9一二三四五六七八九十]{1,3})\s*(?:阶段|步)|阶段\s*(\d{1,2}|[一二三四五六七八九十]{1,3})",
        claim,
    ):
        ordinal, _ = phase_mention(match.group(0))
        if ordinal is None:
            continue
        hits.append((match.start(), ordinal))

    chosen: Optional[int] = None
    for start, ordinal in hits:
        prefix = claim[max(0, start - 24):start]
        if FORWARD_PHASE_RE.search(prefix) and not BACKWARD_PHASE_RE.search(prefix):
            chosen = ordinal
    return chosen


def _newest_records(records: Sequence[ProgressRecord], today: date) -> Tuple[Optional[ProgressRecord], List[ProgressRecord]]:
    eligible = [record for record in records if not record.planned and record.record_date <= today]
    if not eligible:
        return None, []
    newest_date = max(record.record_date for record in eligible)
    at_date = [record for record in eligible if record.record_date == newest_date]
    return at_date[0], at_date


def _resolve_current(
    phases: List[Phase],
    explicit_currents: List[Phase],
    record_ordinals: List[int],
    conflicts: List[str],
    notes: List[str],
) -> Tuple[Optional[Phase], str]:
    by_ordinal = {phase.ordinal: phase for phase in phases}

    if record_ordinals:
        unique = sorted(set(record_ordinals))
        if len(unique) > 1:
            conflicts.append(
                "同一最新进展日期下出现了多个当前阶段（"
                + "、".join(f"Phase {item}" for item in unique)
                + "）"
            )
            return None, "conflict"
        ordinal = unique[0]
        phase = by_ordinal.get(ordinal)
        if phase is None:
            phase = Phase(
                ordinal=ordinal,
                name=f"Phase {ordinal}",
                status="current",
                source_path=phases[0].source_path if phases else "",
                status_raw="仅在进展记录中出现",
            )
            phases.append(phase)
            phases.sort(key=lambda item: item.ordinal)
            notes.append(f"最新进展提到 Phase {ordinal}，但阶段清单中没有该阶段的定义，已按进展记录补充")
        return phase, "newest_record"

    if explicit_currents:
        if len(explicit_currents) > 1:
            conflicts.append(
                "多个阶段被同时标记为进行中（"
                + "、".join(f"Phase {item.ordinal}" for item in explicit_currents)
                + "）"
            )
            return None, "conflict"
        return explicit_currents[0], "explicit"

    completed = sorted(phase.ordinal for phase in phases if phase.status == "completed")
    if not completed:
        return None, "none"
    if len(completed) == len(phases):
        notes.append("所有阶段都标记为已完成，当前阶段按最后一个已完成阶段展示")
        return by_ordinal[max(completed)], "all_completed"

    candidates = [phase for phase in phases if phase.ordinal > max(completed)]
    if not candidates:
        return None, "none"
    first_candidate = min(candidates, key=lambda item: item.ordinal)
    noted = [
        phase
        for phase in phases
        if phase.status != "completed" and phase.ordinal < first_candidate.ordinal
    ]
    if noted:
        notes.append("阶段状态互相矛盾（后续阶段已完成但前序阶段未标记），需要人工核对")
        return None, "inconsistent"
    notes.append("当前阶段由“已完成”标记推定，文档中没有明确的进行中标记")
    return first_candidate, "derived_completed_prefix"


def _pick_proposals(
    proposals: Sequence[ScheduleProposal], project: dict
) -> Tuple[List[ScheduleProposal], List[str]]:
    notes: List[str] = []
    latest: Dict[str, ScheduleProposal] = {}
    for proposal in proposals:
        current = latest.get(proposal.field)
        if current is None:
            latest[proposal.field] = proposal
            continue
        current_key = (current.record_date or date.min, current.candidate)
        new_key = (proposal.record_date or date.min, proposal.candidate)
        if new_key >= current_key:
            latest[proposal.field] = proposal

    selected: List[ScheduleProposal] = []
    for field_name, proposal in latest.items():
        previous = project.get(field_name)
        if previous == proposal.candidate.isoformat():
            continue
        selected.append(proposal)
    return selected, notes


def build_candidate(project: dict, discovery: Discovery, documents: Sequence[Document], today: date) -> Candidate:
    conflicts: List[str] = []
    notes: List[str] = []

    progress: List[ProgressRecord] = []
    for document in documents:
        progress.extend(extract_progress(document))

    phases, phase_conflicts = merge_phases(documents)
    conflicts.extend(phase_conflicts)

    newest, same_day = _newest_records(progress, today)
    if newest is None:
        notes.append("没有找到带明确日期的进展记录，无法判断进展新旧（未使用文件修改时间）")

    record_ordinals: List[int] = []
    for record in same_day:
        ordinal = _phase_forward_mention(record.claim)
        if ordinal is not None:
            record_ordinals.append(ordinal)

    explicit_currents = [phase for phase in phases if phase.status == "current"]
    current, basis = _resolve_current(phases, explicit_currents, record_ordinals, conflicts, notes)

    testing = bool(current and current.testing)
    if not testing and newest is not None and testing_in_claim(newest.claim):
        testing = True
        notes.append("测试状态来自最新进展记录的文字描述")

    summary = ""
    summary_source = ""
    ordered = sorted(documents, key=_document_priority)
    for document in ordered:
        value = extract_summary(document)
        if value:
            summary = value
            summary_source = document.relative_path
            break

    proposals = extract_schedule_from_records(progress) + extract_schedule_from_lines_docs(documents)
    selected_proposals, proposal_notes = _pick_proposals(proposals, project)
    notes.extend(proposal_notes)

    evidence: List[EvidenceItem] = []
    for record in sorted(progress, key=lambda item: item.record_date, reverse=True):
        evidence.append(
            EvidenceItem(
                kind="progress",
                source_path=record.source_path,
                heading=record.heading,
                record_date=record.record_date,
                claim=record.claim,
                excerpt=record.excerpt,
                is_newest=bool(newest and record.record_date == newest.record_date and record is newest),
            )
        )
    for phase in phases:
        if not phase.status_raw:
            continue
        evidence.append(
            EvidenceItem(
                kind="phase_status",
                source_path=phase.source_path,
                heading=phase.source_heading,
                record_date=phase.end or phase.start,
                claim=f"Phase {phase.ordinal} · {phase.status}",
                excerpt=phase.status_raw,
            )
        )
    for proposal in selected_proposals:
        evidence.append(
            EvidenceItem(
                kind="schedule",
                source_path=proposal.source_path,
                heading="",
                record_date=proposal.record_date,
                claim=proposal.claim,
                excerpt=proposal.excerpt,
            )
        )
    if summary:
        evidence.append(
            EvidenceItem(
                kind="summary",
                source_path=summary_source,
                heading="",
                record_date=None,
                claim=summary,
                excerpt=summary,
            )
        )

    status = "ok"
    reason = ""
    if conflicts:
        status = "needs_confirmation"
        reason = conflicts[0]
        notes.extend(conflicts[1:])
    elif current is None:
        status = "unknown"
        if not phases:
            reason = "项目中没有任何 Markdown 文档标注了阶段结构"
        elif basis == "inconsistent":
            reason = "阶段状态互相矛盾，无法确定当前阶段"
        else:
            reason = "文档中没有标注任何阶段状态，无法确定当前阶段"

    if not discovery.files:
        status = "unknown"
        reason = "项目文件夹中没有可读取的 Markdown 文件"

    return Candidate(
        status=status,
        reason=reason,
        summary=summary,
        summary_source=summary_source,
        phases=phases,
        current=current,
        basis=basis,
        testing=testing,
        newest=newest,
        evidence=evidence[:MAX_EVIDENCE],
        proposals=selected_proposals,
        notes=_dedupe(notes),
        files_scanned=len(discovery.files),
    )


def extract_schedule_from_lines_docs(documents: Sequence[Document]) -> List[ScheduleProposal]:
    proposals: List[ScheduleProposal] = []
    for document in documents:
        proposals.extend(extract_schedule_from_lines(document))
    return proposals


def _dedupe(values: Iterable[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
