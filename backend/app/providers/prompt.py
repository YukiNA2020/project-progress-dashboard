"""Prompt construction.

The prompt is deliberately narrow: the model sees a numbered evidence list and
may only answer about it. Everything it says must cite an evidence id and quote
that evidence verbatim, which the validator checks before anything is stored.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict

from .bundle import Bundle

SYSTEM_PROMPT = """你是项目进度分析器。你只能依据 <evidence> 中的条目回答，不得使用外部知识，不得推测。

输出规则：
1. 只输出一个 JSON 对象，不要代码块、不要解释性文字。
2. 每条结论都必须在 citations 中给出证据编号和逐字引用；quote 必须是该条证据 text 里连续出现的一段原文（至少 4 个字符）。
3. 证据里没有明确写出的信息，字段返回 null 或空数组，不要补全。
4. 日期只使用证据中完整写出的、带年份的日期，格式 YYYY-MM-DD。
5. 如果证据互相矛盾，把矛盾写进 conflicts 并在 citations 用 supports="conflict" 引用两边；不要替用户选一个。
6. current_phase_ordinal 只能取证据里出现的阶段编号；无法判断时返回 null。

JSON 结构：
{
  "current_phase_ordinal": 整数或 null,
  "current_phase_name": 字符串或 null,
  "phase_status": "completed" | "in_progress" | "upcoming" | "unknown",
  "testing": true 或 false,
  "summary": 字符串，可为空字符串,
  "schedule_changes": [
    {"field": "planned_start" | "planned_end", "date": "YYYY-MM-DD", "reason": 字符串}
  ],
  "conflicts": [字符串],
  "citations": [
    {"evidence_id": "E1", "quote": "逐字原文", "supports": "current_phase" | "testing" | "summary" | "schedule" | "conflict" | "phase_status"}
  ],
  "confidence": "high" | "medium" | "low"
}

约束：
- current_phase_ordinal 非 null 时，citations 至少有一条 supports="current_phase"。
- testing 为 true 时，必须有一条 supports="testing" 的引用。
- summary 非空时，必须有一条 supports="summary" 的引用。
- 每条 schedule_changes 必须有一条 supports="schedule" 的引用，且 date 在该证据原文中出现。
- conflicts 非空时，至少有一条 supports="conflict" 的引用。
- confidence 表示你对 current_phase_ordinal 判断的把握；证据不足时用 "low"。
"""


def _plan_line(project: Dict[str, Any]) -> str:
    return f"{project.get('planned_start', '')} 至 {project.get('planned_end', '')}"


def build_prompt(bundle: Bundle, project: Dict[str, Any], today: date) -> str:
    evidence = {
        "today": today.isoformat(),
        "project": {
            "name": project.get("name", ""),
            "planned_range": _plan_line(project),
        },
        "evidence": bundle.as_payload(),
    }
    return (
        "请分析下面这个项目的进度。只使用 <evidence> 中的条目。\n\n"
        "<evidence>\n"
        + json.dumps(evidence, ensure_ascii=False, indent=2)
        + "\n</evidence>\n\n"
        "现在输出符合约定的 JSON 对象。"
    )
