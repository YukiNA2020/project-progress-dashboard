"""Optional model-assisted extraction.

Off by default. When the user turns it on, the text and the customer names are
sent to the endpoint they configured — which is why the browser warns before
enabling and why every failure falls back to the local rules instead of
blocking the capture.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from ..providers import client
from ..providers.transport import ProviderError
from . import local_rules

SYSTEM = """你是项目信息抽取器。只依据用户给出的一句话抽取，不许推测，不许补全。
只输出一个 JSON 对象，不要代码块、不要解释。

结构：
{"name":"","customer":"","phase":"","start":"","end":"","contact":"","dept":"",
 "deptType":"内部或外部或空","contactWay":"","means":"","channel":"","note":"","next":"",
 "milestones":[{"date":"YYYY-MM-DD","label":""}]}

规则：
1. 日期一律 YYYY-MM-DD；只有月日时按今天推断最近的一个未来日期。
2. customer 只能从给定候选里选，不要自造。
3. phase 只能从给定阶段里选。
4. 没提到的字段返回空字符串，不要编。
5. note 写卡点或当前进展；next 写下一个具体动作。"""


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?|```$", "", cleaned, flags=re.MULTILINE).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(cleaned[start:end + 1])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _customer_id(value: str, customers: List[Dict[str, Any]]) -> Tuple[str, str]:
    needle = (value or "").strip()
    if not needle:
        return "", ""
    for customer in customers:
        name = customer.get("name") or ""
        if name and (name == needle or name in needle or needle in name):
            return customer.get("id", ""), name
    return "", needle


def parse_with_model(text: str, customers: List[Dict[str, Any]],
                     phases: List[Dict[str, Any]], settings: Dict[str, Any],
                     today: Optional[date] = None) -> Dict[str, Any]:
    today = today or date.today()
    phase_names = [item.get("name") for item in phases if item.get("name")]
    customer_names = [item.get("name") for item in customers if item.get("name")]

    prompt = "\n".join([
        "今天：%s" % today.isoformat(),
        "可选客户：%s" % ("、".join(customer_names) or "（无）"),
        "可选阶段：%s" % ("、".join(phase_names) or "（无）"),
        "",
        "用户输入：",
        text,
    ])

    try:
        raw = client.complete(settings, SYSTEM, prompt)
    except ProviderError as error:
        result = local_rules.parse(text, customers, phases, today)
        result["warnings"].append("模型抽取失败（%s），已改用本地规则" % error)
        return result

    data = _extract_json(raw)
    if data is None:
        result = local_rules.parse(text, customers, phases, today)
        result["warnings"].append("模型没有返回可用的 JSON，已改用本地规则")
        return result

    fields: Dict[str, Dict[str, Any]] = {}

    def put(key: str, value: Any, confidence: float = 0.85) -> None:
        fields[key] = {"value": value or "", "confidence": confidence if value else 0,
                       "evidence": "模型抽取"}

    customer_id, suggested = _customer_id(str(data.get("customer") or ""), customers)
    for key in ("name", "phase", "start", "end", "contact", "dept", "deptType",
                "contactWay", "means", "channel", "note", "next"):
        put(key, data.get(key))
    if customer_id:
        fields["customer"] = {"value": customer_id, "confidence": 0.8,
                              "evidence": "模型抽取", "is_new": False,
                              "suggest_name": suggested}
    else:
        fields["customer"] = {"value": "", "confidence": 0, "evidence": "",
                              "is_new": bool(suggested), "suggest_name": suggested}
    put("updated", today.isoformat(), 1.0)

    milestones = []
    for item in data.get("milestones") or []:
        if isinstance(item, dict) and item.get("date"):
            milestones.append({
                "date": str(item["date"])[:10],
                "label": str(item.get("label") or "关键时间点"),
                "confidence": 0.8,
                "evidence": "模型抽取",
            })

    unresolved = [key for key in local_rules.FIELDS
                  if fields.get(key, {}).get("confidence", 0) < 0.7]
    phase_value = fields.get("phase", {}).get("value") or ""
    done = []
    ordered = sorted(phases, key=lambda item: item.get("ordinal", 0))
    for item in ordered:
        if item.get("name") == phase_value:
            break
        done.append(item.get("name"))

    return {
        "parser": "模型抽取",
        "text": text,
        "fields": fields,
        "milestones": milestones,
        "done_phases": done,
        "is_range": False,
        "unresolved": unresolved,
        "warnings": [],
    }
