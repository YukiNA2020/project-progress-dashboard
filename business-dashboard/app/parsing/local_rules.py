"""Local rule-based extraction.

Deliberately no network: the text people type here contains customer names,
project codes and delivery dates, none of which may leave the machine. Every
field comes back with a confidence and the exact substring it came from, so the
browser can highlight it and the user can judge whether to trust it.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

FIELDS = [
    "name", "customer", "phase", "start", "end", "contact", "dept",
    "deptType", "contactWay", "means", "channel", "note", "next", "updated",
]

# ---------------------------------------------------------------------------
# date parsing
# ---------------------------------------------------------------------------

DATE_RE = re.compile(
    r"(?P<abs>20\d{2}\s*[-/.年]\s*\d{1,2}\s*[-/.月]\s*\d{1,2}\s*[日号]?)"
    r"|(?P<cn>\d{1,2}\s*月\s*\d{1,2}\s*[日号])"
    r"|(?P<cnmonth>\d{1,2}\s*月(?:底|初|中))"
    r"|(?P<md>(?<![\d/.\-])\d{1,2}\s*[-/.]\s*\d{1,2}(?![\d/.\-]))"
    r"|(?P<week>(?:下|本|这)?周[一二三四五六日天])"
    r"|(?P<days>\d{1,3}\s*天(?:后|之后|以后|内|以内))"
    r"|(?P<month>(?:本|下)?月(?:底|初|中)|年底|年初)"
)

WEEKDAY = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}

RANGE_JOIN = re.compile(r"^\s*(?:到|至|~|—|–|-)\s*$")


def _last_day(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _safe_date(year: int, month: int, day: int) -> Optional[date]:
    if not (1 <= month <= 12):
        return None
    if not (1 <= day <= _last_day(year, month)):
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _infer_year(month: int, day: int, today: date) -> Tuple[date, bool]:
    """Pick the year that makes the date sit in the near future.

    Saying "12/5" in November means this year; saying "1/10" in November almost
    certainly means next year. Six months of look-back keeps both right.
    """
    candidate = _safe_date(today.year, month, day)
    if candidate is None:
        return today, True
    if candidate < today - timedelta(days=180):
        nxt = _safe_date(today.year + 1, month, day)
        if nxt is not None:
            return nxt, True
    return candidate, True


def find_dates(text: str, today: date) -> List[Dict[str, Any]]:
    found: List[Dict[str, Any]] = []
    for match in DATE_RE.finditer(text):
        raw = match.group(0).strip()
        value: Optional[date] = None
        inferred = False

        if match.group("abs"):
            digits = re.findall(r"\d+", raw)
            if len(digits) >= 3:
                value = _safe_date(int(digits[0]), int(digits[1]), int(digits[2]))
        elif match.group("cn"):
            digits = re.findall(r"\d+", raw)
            if len(digits) >= 2:
                value, inferred = _infer_year(int(digits[0]), int(digits[1]), today)
        elif match.group("cnmonth"):
            digits = re.findall(r"\d+", raw)
            month = int(digits[0]) if digits else today.month
            if "初" in raw:
                day = 1
            elif "底" in raw:
                day = _last_day(today.year, month)
            else:
                day = 15
            value = _safe_date(today.year, month, day)
            if value is not None and value < today - timedelta(days=180):
                value = _safe_date(today.year + 1, month, day)
            inferred = True
        elif match.group("md"):
            digits = re.findall(r"\d+", raw)
            if len(digits) >= 2:
                value, inferred = _infer_year(int(digits[0]), int(digits[1]), today)
        elif match.group("week"):
            label = raw[-1]
            weekday = WEEKDAY.get(label)
            if weekday is not None:
                monday = today - timedelta(days=today.weekday())
                target = monday + timedelta(days=weekday)
                if raw.startswith("下"):
                    target += timedelta(days=7)
                elif raw.startswith("本") or raw.startswith("这"):
                    pass
                elif target < today:
                    target += timedelta(days=7)
                value = target
        elif match.group("days"):
            digits = re.findall(r"\d+", raw)
            if digits:
                value = today + timedelta(days=int(digits[0]))
        elif match.group("month"):
            if raw.startswith("年底"):
                value = date(today.year, 12, 31)
            elif raw.startswith("年初"):
                value = date(today.year, 1, 1)
            elif raw.startswith("下月"):
                year = today.year + (1 if today.month == 12 else 0)
                month = 1 if today.month == 12 else today.month + 1
                value = date(year, month, 1 if raw.endswith("初") else _last_day(year, month))
            else:
                value = date(today.year, today.month,
                             1 if raw.endswith("初") else _last_day(today.year, today.month))

        if value is None:
            continue
        found.append({
            "iso": value.isoformat(),
            "raw": raw,
            "start": match.start(),
            "end": match.end(),
            "inferred_year": inferred,
            "precision": "day",
        })

    found.sort(key=lambda item: item["start"])
    return found


def find_range(text: str, dates: List[Dict[str, Any]]) -> Tuple[Optional[Dict], Optional[Dict], bool]:
    """Return (start, end, is_range) from the dates found in the text."""
    if not dates:
        return None, None, False

    for index in range(len(dates) - 1):
        left, right = dates[index], dates[index + 1]
        gap = text[left["end"]:right["start"]]
        if len(gap) <= 6 and RANGE_JOIN.match(gap):
            return left, right, True

    if len(dates) == 1:
        only = dates[0]
        before = text[max(0, only["start"] - 8):only["start"]]
        after = text[only["end"]:only["end"] + 4]
        if re.search(r"(从|自|开始于|计划)", before):
            return only, None, False
        if re.search(r"(到|至|截止|最晚|前|DDL|deadline)", before, re.IGNORECASE):
            return None, only, False
        # "下周三前" / "12/5 之前" read as a deadline, not a start.
        if re.match(r"^\s*(前|之前|以前|为止|截止)", after):
            return None, only, False
        # "12月初出货" is a delivery date even without an explicit 到.
        if re.search(r"(出货|交货|交期|上线|投产|完成|发运)", text[only["end"]:only["end"] + 20]):
            return None, only, False
        return only, None, False

    return dates[0], dates[-1], False


DDL_WORDS = ("ddl", "deadline", "截止", "最晚", "之前要", "必须交", "要交", "出货",
             "交货", "上线", "开模", "打样", "报价")
DDL_LABELS = (
    ("出货", "出货 DDL"), ("交货", "交货 DDL"), ("报价", "报价 DDL"),
    ("打样", "打样 DDL"), ("开模", "开模 DDL"), ("上线", "上线 DDL"),
    ("截止", "截止日"), ("最晚", "最晚期限"),
)


def find_milestones(text: str, dates: List[Dict[str, Any]],
                    used: List[int]) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    seen: set = set()
    for item in dates:
        if item["start"] in used or item["iso"] in seen:
            continue
        window = text[max(0, item["start"] - 12): min(len(text), item["end"] + 16)].lower()
        if not any(word in window for word in DDL_WORDS):
            continue
        label = "关键时间点"
        for word, name in DDL_LABELS:
            if word in window:
                label = name
                break
        seen.add(item["iso"])
        results.append({
            "date": item["iso"],
            "label": label,
            "confidence": 0.82 if item["inferred_year"] else 0.9,
            "evidence": text[item["start"]: min(len(text), item["end"] + 14)].strip(" ，,、"),
        })
    return results


# ---------------------------------------------------------------------------
# customer / phase matching
# ---------------------------------------------------------------------------

SUFFIX = re.compile(r"(有限公司|股份有限公司|集团|公司|工厂|厂)$")


def _normalise(value: str) -> str:
    value = re.sub(r"\s+", "", value or "").lower()
    return SUFFIX.sub("", value)


def match_customer(text: str, customers: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    best = None
    haystack = _normalise(text)
    for customer in customers:
        names = [customer.get("name") or ""]
        names += [part.strip() for part in (customer.get("alias") or "").split(",") if part.strip()]
        for name in names:
            if not name:
                continue
            exact = name in text
            normalised = _normalise(name)
            fuzzy = bool(normalised) and normalised in haystack
            if not (exact or fuzzy):
                continue
            score = 0.95 if exact else 0.82
            candidate = {
                "id": customer.get("id", ""),
                "name": customer.get("name", ""),
                "confidence": score,
                "evidence": name if exact else normalised,
            }
            if best is None or candidate["confidence"] > best["confidence"]:
                best = candidate
    return best


def match_phase(text: str, phases: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    ordered = sorted(phases, key=lambda item: len(item.get("name") or ""), reverse=True)
    taken: List[Tuple[int, int]] = []
    hits: List[Dict[str, Any]] = []

    for phase in ordered:
        name = phase.get("name") or ""
        if not name:
            continue
        start = 0
        while True:
            index = text.find(name, start)
            if index < 0:
                break
            span = (index, index + len(name))
            if not any(span[0] < t[1] and span[1] > t[0] for t in taken):
                taken.append(span)
                hits.append({
                    "name": name,
                    "confidence": 0.95,
                    "evidence": name,
                    "position": index,
                })
            start = index + 1

    if not hits:
        return None
    # People mention the latest state last: "打样完了，现在开发中".
    hits.sort(key=lambda item: item["position"])
    return hits[-1]


# ---------------------------------------------------------------------------
# people / departments
# ---------------------------------------------------------------------------

DEPARTMENTS = [
    ("研发", "内部"), ("开发", "内部"), ("采购", "内部"), ("品质", "内部"),
    ("生产", "内部"), ("计划", "内部"), ("工程", "内部"), ("模具", "内部"),
    ("财务", "内部"), ("物流", "内部"), ("仓库", "内部"), ("报关", "内部"),
    ("船务", "内部"), ("业务", "内部"), ("客户", "外部"), ("供应商", "外部"),
    ("货代", "外部"), ("第三方", "外部"),
]

CONTACT_RE = re.compile(
    r"(?:找|催|问|联系|让|跟(?!进)|和|叫|对接人)\s*([\u4e00-\u9fa5]{1,4})"
    r"|([\u4e00-\u9fa5]{1,3})?(经理|主管|总监|工程师|老师|姐|哥|总)"
)

# "客户采购部" alone is handled by the department table; these phrases catch
# the case where the text names a department but the person belongs outside:
# "客户那边的采购玛丽" is an external contact even though 采购 is internal.
EXTERNAL_HINT = re.compile(
    r"客户\s*(那边|方|的|采购|技术|品质|工程|质量)|供应商|货代|第三方|外部|对方")


def find_department(text: str) -> Optional[Dict[str, Any]]:
    for word, kind in DEPARTMENTS:
        index = text.find(word)
        while index >= 0:
            end = index + len(word)
            suffix = ""
            for candidate in ("部门", "部", "科", "组"):
                if text[end:end + len(candidate)] == candidate:
                    end += len(candidate)
                    suffix = candidate
                    break
            # "客户那边" is a party, not a department. Only accept 客户 when it
            # is followed by a real unit ("客户采购部").
            if word == "客户" and not suffix:
                index = text.find(word, index + 1)
                continue
            value = text[index:end]
            return {
                "value": value,
                "deptType": kind,
                "confidence": 0.72 if kind == "内部" else 0.8,
                "evidence": value,
            }
    return None


CONTACT_CUT = re.compile(r"(确认|说|给|发|看|做|要|问|回|把|的|帮|安排)")


def find_contact(text: str) -> Optional[Dict[str, Any]]:
    match = CONTACT_RE.search(text)
    if not match:
        return None
    if match.group(1):
        value = match.group(1)
        for word, _kind in DEPARTMENTS:
            if value.startswith(word) and len(value) > len(word):
                value = value[len(word):]
                break
        # "催老李确认图纸" grabs "老李确认"; keep the name only. If the match
        # starts with the verb ("跟客户确认"), there is no name to keep.
        cut = CONTACT_CUT.search(value)
        if cut:
            if cut.start() == 0:
                return None
            if cut.start() >= 2:
                value = value[:cut.start()]
        if value in ("客户", "他", "她", "那边", "对方"):
            return None
        return {"value": value, "confidence": 0.72, "evidence": match.group(0).strip()}
    value = (match.group(2) or "") + (match.group(3) or "")
    if len(value) < 2:
        return None
    return {"value": value, "confidence": 0.75, "evidence": match.group(0).strip()}


# ---------------------------------------------------------------------------
# actions / blockers
# ---------------------------------------------------------------------------

SENTENCE_SPLIT = re.compile(r"[。！？\n;；]+")
SEGMENT_SPLIT = re.compile(r"[。！？\n;；，,]+")

NEXT_TRIGGERS = ("下一步", "接下来", "然后", "后面", "回头", "得去", "准备", "安排",
                 "需要", "我要", "还得", "明天", "下周")

BLOCK_TRIGGERS = ("卡在", "卡住", "卡了", "堵在", "等客户", "等供应", "等确认",
                  "延迟", "延到", "延期", "要改", "问题", "风险", "还没", "缺",
                  "不过", "但是", "催")

MEANS_TRIGGERS = ("找", "要了", "拿到", "问了", "取了", "调了", "发给", "给了")


def _segments(text: str) -> List[str]:
    return [part.strip(" ，,、") for part in SEGMENT_SPLIT.split(text) if part.strip(" ，,、")]


def _pick(text: str, triggers: Tuple[str, ...], exclude: Tuple[str, ...] = ()) -> Optional[Dict[str, Any]]:
    """Join every comma-level segment that mentions a trigger.

    Splitting at commas rather than full stops is what turns the whole
    sentence "德国 Kalom 的洗碗机项目开发中，模具要改，计划 11/10 到 12/5"
    into just "模具要改" — which is the part the user wants in the card.
    """
    picked: List[str] = []
    evidence = ""
    for segment in _segments(text):
        if any(word in segment for word in exclude):
            continue
        hit = [word for word in triggers if word in segment]
        if not hit:
            continue
        value = segment
        # "Kalom 那个案子卡在模具" carries a lot of lead-in; start at the
        # first trigger so the card shows "卡在模具", not the whole clause.
        position = min(segment.find(word) for word in hit)
        if position > 0 and len(segment) > 8:
            value = segment[position:]
        picked.append(value)
        if not evidence:
            evidence = segment
    if not picked:
        return None
    return {"value": "，".join(picked)[:120], "confidence": 0.85, "evidence": evidence}


TIME_TRIGGERS = ("明天", "后天", "下周", "本周", "这周", "月底", "下月初", "下个月")


def _clean(sentence: str, triggers: Tuple[str, ...]) -> str:
    value = sentence.strip(" ，,、")
    for trigger in triggers:
        if not value.startswith(trigger):
            continue
        # "下周一开始改模" is a complete action; stripping 下周 leaves nonsense.
        if trigger in TIME_TRIGGERS:
            return value[:80]
        rest = value[len(trigger):].strip(" ，,、:：")
        # Never split a time word: "下周三前" minus "下周" is "三前".
        if rest[:1] in ("前", "后", "天", "底", "初", "中", "末", "个"):
            return value[:80]
        value = rest
        break
    return value[:80]


def find_next(text: str) -> Optional[Dict[str, Any]]:
    segments = _segments(text)
    for index, segment in enumerate(segments):
        if not any(trigger in segment for trigger in NEXT_TRIGGERS):
            continue
        value = _clean(segment, NEXT_TRIGGERS)
        # "下一步，催老李确认图纸" splits into two segments; take the next one.
        if len(value) < 3 and index + 1 < len(segments):
            value = segments[index + 1]
        if len(value) >= 2:
            return {"value": value, "confidence": 0.86, "evidence": segment}
    return None


def find_blocker(text: str) -> Optional[Dict[str, Any]]:
    return _pick(text, BLOCK_TRIGGERS, exclude=NEXT_TRIGGERS)


def find_means(text: str) -> Optional[Dict[str, Any]]:
    return _pick(text, MEANS_TRIGGERS, exclude=NEXT_TRIGGERS + ("卡",))


NAME_RE = re.compile(
    r"([\u4e00-\u9fa5A-Za-z0-9][\u4e00-\u9fa5A-Za-z0-9\-]{1,14})\s*(项目|订单|案子|机型)")


def find_name(text: str, customer: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    match = NAME_RE.search(text)
    if not match:
        return None
    base = match.group(1).strip()

    names: List[str] = []
    if customer:
        names.append(customer.get("name") or "")
        names += [part.strip() for part in (customer.get("alias") or "").split(",") if part.strip()]
    for name in sorted([n for n in names if n], key=len, reverse=True):
        if base.startswith(name):
            base = base[len(name):].strip()

    base = re.sub(r"^(那个|这个|该|其)", "", base)
    base = re.sub(r"(那个|这个|该)$", "", base).strip()
    if "的" in base:
        base = base.split("的")[-1].strip()
    base = re.sub(r"^[的了是在和与]", "", base).strip()

    if len(base) < 2:
        return None
    # The clause only repeated the customer name; there is no project name here.
    if any(_normalise(base) == _normalise(name) for name in names if name):
        return None
    return {"value": base + "项目", "confidence": 0.88, "evidence": match.group(0)}


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def parse(text: str, customers: List[Dict[str, Any]], phases: List[Dict[str, Any]],
          today: Optional[date] = None) -> Dict[str, Any]:
    today = today or date.today()
    text = (text or "").strip()
    if not text:
        return _empty("本地规则", "没有可解析的内容")

    dates = find_dates(text, today)
    start, end, is_range = find_range(text, dates)

    used: List[int] = [start["start"]] if start else []
    milestones = find_milestones(text, dates, used)

    customer = match_customer(text, customers)
    phase = match_phase(text, phases)
    department = find_department(text)
    contact = find_contact(text)
    nxt = find_next(text)
    blocker = find_blocker(text)
    means = find_means(text)
    name = find_name(text, customer)

    fields: Dict[str, Dict[str, Any]] = {}
    warnings: List[str] = []

    def put(key: str, value: Any, confidence: float, evidence: str) -> None:
        fields[key] = {"value": value or "", "confidence": round(confidence, 2),
                       "evidence": evidence}

    put("name", name["value"] if name else "", name["confidence"] if name else 0,
        name["evidence"] if name else "")

    if customer:
        fields["customer"] = {
            "value": customer["id"], "confidence": customer["confidence"],
            "evidence": customer["evidence"], "is_new": False,
            "suggest_name": customer["name"],
        }
    else:
        put("customer", "", 0, "")

    put("phase", phase["name"] if phase else "", phase["confidence"] if phase else 0,
        phase["evidence"] if phase else "")

    if start:
        put("start", start["iso"], 0.75 if start["inferred_year"] else 0.92, start["raw"])
        if start["inferred_year"]:
            warnings.append("「%s」没写年份，按 %s 年推断" % (start["raw"], start["iso"][:4]))
    else:
        put("start", "", 0, "")

    if end:
        put("end", end["iso"], 0.75 if end["inferred_year"] else 0.92, end["raw"])
        if end["inferred_year"] and (not start or start["iso"] != end["iso"]):
            warnings.append("「%s」没写年份，按 %s 年推断" % (end["raw"], end["iso"][:4]))
    else:
        put("end", "", 0, "")

    if start and end and end["iso"] >= start["iso"]:
        pass
    elif start and end and end["iso"] < start["iso"]:
        warnings.append("结束日期早于开始日期，请手动核对")

    put("contact", contact["value"] if contact else "",
        contact["confidence"] if contact else 0,
        contact["evidence"] if contact else "")
    put("dept", department["value"] if department else "",
        department["confidence"] if department else 0,
        department["evidence"] if department else "")
    dept_type = department["deptType"] if department else ""
    if dept_type == "内部" and EXTERNAL_HINT.search(text):
        dept_type = "外部"
    put("deptType", dept_type, department["confidence"] if department else 0,
        department["evidence"] if department else "")

    put("contactWay", "", 0, "")
    put("means", means["value"] if means else "",
        means["confidence"] if means else 0,
        means["evidence"] if means else "")
    put("channel", "", 0, "")
    put("note", blocker["value"] if blocker else "",
        blocker["confidence"] if blocker else 0,
        blocker["evidence"] if blocker else "")
    put("next", nxt["value"] if nxt else "", nxt["confidence"] if nxt else 0,
        nxt["evidence"] if nxt else "")
    put("updated", today.isoformat(), 1.0, "")

    unresolved = [key for key in FIELDS if fields.get(key, {}).get("confidence", 0) < 0.7]

    done = []
    if phase:
        ordered = sorted(phases, key=lambda item: item.get("ordinal", 0))
        for item in ordered:
            if item.get("name") == phase["name"]:
                break
            done.append(item.get("name"))

    return {
        "parser": "本地规则",
        "text": text,
        "fields": fields,
        "milestones": milestones,
        "done_phases": done,
        "is_range": is_range,
        "unresolved": unresolved,
        "warnings": warnings,
    }


def _empty(parser: str, warning: str) -> Dict[str, Any]:
    return {
        "parser": parser,
        "text": "",
        "fields": {key: {"value": "", "confidence": 0, "evidence": ""} for key in FIELDS},
        "milestones": [],
        "done_phases": [],
        "is_range": False,
        "unresolved": list(FIELDS),
        "warnings": [warning],
    }
