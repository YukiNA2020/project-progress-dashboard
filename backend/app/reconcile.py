"""Reconcile the deterministic rule result with the model's structured answer.

The rules own dates and freshness; the model may confirm, name, or enrich.
They can only *agree* into an accepted state:

* both agree on the current phase -> accepted, labelled ``rules_and_model``;
* anything else (disagreement, model conflict, low-confidence-only guess,
  malformed output, provider failure) -> visible problem, accepted state kept.

A schedule date is never applied here. It becomes a pending proposal that the
user must accept.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .providers.analyze import ModelOutcome
from .providers.schema import Citation, ModelResult
from .scanner.extract import ScheduleProposal
from .scanner.state import Candidate, Phase

FIELD_LABELS = {"planned_start": "计划开始日期", "planned_end": "计划结束日期"}


@dataclass
class Decision:
    status: str
    reason: str
    phase: Optional[Phase]
    basis: str
    testing: bool
    summary: str
    summary_source: str
    proposals: List[ScheduleProposal]
    notes: List[str] = field(default_factory=list)
    model_status: str = "disabled"
    model_error: str = ""
    model_confidence: str = ""
    model_summary: str = ""
    citations: List[Citation] = field(default_factory=list)
    model_provider: str = ""
    model_name: str = ""


def _merge_proposals(
    rule_proposals: List[ScheduleProposal], result: ModelResult, project: Dict[str, Any]
) -> tuple:
    merged: Dict[str, ScheduleProposal] = {}
    for proposal in rule_proposals:
        if proposal.candidate.isoformat() == str(project.get(proposal.field) or ""):
            continue
        merged[proposal.field] = proposal

    problems: List[str] = []
    for claim in result.schedule_changes:
        if claim.target.isoformat() == str(project.get(claim.field) or ""):
            continue
        existing = merged.get(claim.field)
        label = FIELD_LABELS.get(claim.field, claim.field)
        if existing is not None and existing.candidate != claim.target:
            problems.append(
                f"{label}出现两个不同的候选日期（规则读到 {existing.candidate.isoformat()}，"
                f"模型读到 {claim.target.isoformat()}），需要你核对原文"
            )
            merged.pop(claim.field, None)
            continue
        if existing is not None:
            continue
        citation = result.citation_for("schedule")
        merged[claim.field] = ScheduleProposal(
            source_path=citation.source if citation else "",
            field=claim.field,
            candidate=claim.target,
            record_date=None,
            claim=claim.reason or "模型从证据中读到的排期日期",
            excerpt=citation.quote if citation else "",
        )
    return list(merged.values()), problems


def _base(candidate: Candidate) -> Decision:
    return Decision(
        status=candidate.status,
        reason=candidate.reason,
        phase=candidate.current,
        basis=candidate.basis,
        testing=candidate.testing,
        summary=candidate.summary,
        summary_source=candidate.summary_source,
        proposals=list(candidate.proposals),
        notes=list(candidate.notes),
    )


def decide(candidate: Candidate, outcome: Optional[ModelOutcome], project: Dict[str, Any]) -> Decision:
    decision = _base(candidate)
    if outcome is None:
        return decision

    decision.model_status = outcome.status
    decision.model_provider = outcome.provider
    decision.model_name = outcome.model
    decision.model_confidence = outcome.confidence
    if outcome.result is not None:
        decision.model_summary = outcome.result.summary
        decision.citations = list(outcome.result.citations)

    if outcome.status == "skipped":
        if outcome.error:
            decision.notes.append(f"本次未调用模型：{outcome.error}")
        return decision

    if outcome.status in ("failed", "invalid"):
        decision.status = "model_error"
        decision.model_error = outcome.error
        if outcome.status == "failed":
            decision.reason = f"模型调用失败，未推进已接受状态：{outcome.error}"
        else:
            decision.reason = f"模型返回的结果未通过校验，未推进已接受状态：{outcome.error}"
        decision.phase = None
        decision.notes.append("本次保留上次已接受的状态；可修正配置或来源文档后重新巡检")
        return decision

    result = outcome.result
    assert result is not None  # status == "ok" always carries a result

    decision.notes.append(
        f"模型只收到 {outcome.item_count} 条证据（约 {outcome.bundle_chars} 字符），未发送整份文档"
    )

    proposals, proposal_problems = _merge_proposals(candidate.proposals, result, project)
    decision.proposals = proposals

    decision.testing = bool(candidate.testing or result.testing)
    if result.testing and not candidate.testing:
        decision.notes.append("测试状态由模型从证据文字中判定，规则未识别到测试标记")

    if result.summary and len(result.summary) >= 12:
        citation = result.citation_for("summary")
        decision.summary = result.summary
        decision.summary_source = citation.source if citation else candidate.summary_source

    if candidate.status == "needs_confirmation":
        # A rule-level conflict already blocks promotion; the model cannot override it.
        decision.status = "needs_confirmation"
        decision.reason = candidate.reason
        decision.phase = None
        return decision

    if result.conflicts:
        decision.status = "needs_confirmation"
        decision.reason = result.conflicts[0]
        decision.phase = None
        for extra in result.conflicts[1:]:
            decision.notes.append(extra)
        return decision

    if proposal_problems:
        decision.status = "needs_confirmation"
        decision.reason = proposal_problems[0]
        decision.phase = None
        for extra in proposal_problems[1:]:
            decision.notes.append(extra)
        return decision

    rule_ordinal = candidate.current.ordinal if candidate.current else None
    model_ordinal = result.ordinal

    if rule_ordinal is None and model_ordinal is None:
        decision.status = "unknown"
        decision.reason = "规则与模型都没有从文档中确认当前阶段"
        decision.phase = None
        return decision

    if rule_ordinal is None and model_ordinal is not None:
        decision.status = "needs_confirmation"
        decision.reason = (
            f"模型判断当前处于 Phase {model_ordinal}，但文档里的阶段状态不足以核对，需要你确认"
        )
        decision.phase = None
        return decision

    if model_ordinal is None:
        decision.status = "needs_confirmation"
        decision.reason = f"规则从文档判断当前为 Phase {rule_ordinal}，模型未能确认这一判断"
        decision.phase = None
        return decision

    if model_ordinal != rule_ordinal:
        decision.status = "needs_confirmation"
        decision.reason = (
            f"当前阶段出现分歧（规则：Phase {rule_ordinal}，模型：Phase {model_ordinal}），需要你核对原文"
        )
        decision.phase = None
        return decision

    if (
        result.phase_name
        and candidate.current is not None
        and candidate.current.name.strip() == f"Phase {candidate.current.ordinal}"
        and len(result.phase_name) >= 2
    ):
        candidate.current.name = result.phase_name
        decision.notes.append(f"阶段名称由模型从证据中补充为“{result.phase_name}”")

    decision.status = "ok"
    decision.reason = ""
    decision.phase = candidate.current
    decision.basis = "rules_and_model" if candidate.basis in ("newest_record", "explicit") else candidate.basis
    if result.confidence == "low":
        decision.notes.append("模型自评置信度为 low；规则与模型结论一致，仍按已核对的结果展示")
    return decision
