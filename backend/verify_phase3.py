"""Phase 3 exit-criteria check.

Exercises the model layer with a fake transport, so no network or API key is
needed. Each scenario asserts that a provider failure, a malformed answer, a
missing citation, an invented date, or a disagreement with the rules is
visible and never replaces the last accepted state.

Usage (from the repository root):

    backend/.venv/bin/python backend/verify_phase3.py

The script copies the synthetic fixtures into a temporary directory, writes
its SQLite database there, and never touches the repository fixtures.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import stat
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

WORK_DIR = Path(tempfile.mkdtemp(prefix="ppd-phase3-verify-"))
os.environ["PROJECT_PROGRESS_DASHBOARD_DATA_DIR"] = str(WORK_DIR / "data")
os.environ["PROJECT_PROGRESS_DASHBOARD_PROVIDER_TIMEOUT"] = "5"

from app import config_store, service  # noqa: E402
from app.db import connection, initialize_database  # noqa: E402
from app.providers import client  # noqa: E402
from app.providers.transport import ProviderHttpError, ProviderTimeout  # noqa: E402

FIXTURES = BACKEND_DIR / "fixtures" / "synthetic"
PROJECTS = WORK_DIR / "projects"
RESULTS = []
API_KEY = "sk-test-abcdef1234567890"


def check(name: str, condition: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(condition), detail))


def tree_hashes(root: Path) -> dict:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


# ---------------------------------------------------------------------------
# Fake provider
# ---------------------------------------------------------------------------


def _user_text(payload: dict) -> str:
    messages = payload.get("messages") or []
    for message in reversed(messages):
        content = message.get("content")
        # The system prompt also mentions <evidence>; only the user message
        # carries the closing tag and the JSON block.
        if isinstance(content, str) and "</evidence>" in content:
            return content
    return ""


def parse_evidence(text: str) -> list:
    # The instruction sentence also mentions <evidence>, so take the last pair.
    start = text.rfind("<evidence>") + len("<evidence>")
    end = text.rfind("</evidence>")
    return json.loads(text[start:end])["evidence"]


def find_quote(evidence: list, needle: str):
    for item in evidence:
        index = item["text"].find(needle)
        if index >= 0:
            return item, item["text"][max(0, index - 4) : index + len(needle) + 4]
    return None, ""


class FakeProvider:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.mode = "agree"
        self.ordinal = 2
        self.confidence = "high"
        self.schedule_date = ""
        self.calls = []

    def _body(self, evidence: list) -> str:
        if self.mode == "malformed":
            return "抱歉，我从这些材料里看不出当前阶段。"

        ordinal = self.ordinal
        item, quote = (None, "")
        if ordinal is not None:
            item, quote = find_quote(evidence, f"Phase {ordinal}")
            if item is None:
                # Fall back to any phase mention so the failure is about the
                # mode, not about the fixture.
                item, quote = find_quote(evidence, "Phase")

        citations = []
        if item is not None:
            evidence_id = item["id"]
            if self.mode == "bad_id":
                evidence_id = "E99"
            citations.append({"evidence_id": evidence_id, "quote": quote, "supports": "current_phase"})
        if self.mode == "bad_quote":
            citations = [{"evidence_id": "E1", "quote": "这句原文根本不存在于任何证据", "supports": "current_phase"}]

        summary_item = next((entry for entry in evidence if entry["kind"] == "summary"), None)
        summary_text = ""
        if summary_item is not None:
            summary_text = "模型根据证据整理的项目简介，用于验证结构化输出。"
            citations.append(
                {
                    "evidence_id": summary_item["id"],
                    "quote": summary_item["text"][:20],
                    "supports": "summary",
                }
            )

        payload = {
            "current_phase_ordinal": ordinal,
            "current_phase_name": f"Phase {ordinal}" if ordinal is not None else None,
            "phase_status": "in_progress" if ordinal is not None else "unknown",
            "testing": False,
            "summary": summary_text,
            "schedule_changes": [],
            "conflicts": [],
            "citations": citations,
            "confidence": self.confidence,
        }

        if self.mode == "invented_date":
            target, quote = find_quote(evidence, "Phase")
            citations.append({"evidence_id": target["id"], "quote": quote, "supports": "schedule"})
            payload["schedule_changes"] = [
                {"field": "planned_end", "date": "2027-05-05", "reason": "模型推测的结束日期"}
            ]

        if self.mode == "schedule" and self.schedule_date:
            target, quote = find_quote(evidence, self.schedule_date)
            if target is not None:
                citations.append({"evidence_id": target["id"], "quote": quote, "supports": "schedule"})
                payload["schedule_changes"] = [
                    {"field": "planned_end", "date": self.schedule_date, "reason": "客户验收时间"}
                ]

        if self.mode == "conflict":
            target, quote = find_quote(evidence, "Phase")
            citations.append({"evidence_id": target["id"], "quote": quote, "supports": "conflict"})
            payload["conflicts"] = ["README 与 STATUS 对当前阶段的说法互相矛盾"]

        return json.dumps(payload, ensure_ascii=False)

    def __call__(self, url: str, payload: dict, headers: dict, timeout: float = None):
        self.calls.append({"url": url, "payload": payload, "headers": headers})
        if self.mode == "http500":
            raise ProviderHttpError(500, "接口返回 HTTP 500：internal server error")
        if self.mode == "timeout":
            raise ProviderTimeout("接口在 5 秒内没有响应")
        if self.mode == "badauth":
            raise ProviderHttpError(401, "接口返回 HTTP 401：invalid api key")

        text = _user_text(payload)
        if not text:
            # Connectivity test: answer with a tiny JSON object.
            body = json.dumps({"ok": True})
        else:
            evidence = parse_evidence(text)
            body = self._body(evidence)

        if "system" in payload:
            return 200, {"content": [{"type": "text", "text": body}]}
        return 200, {"choices": [{"message": {"content": body}}]}


FAKE = FakeProvider()
client.post_json = FAKE


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def copy_fixture(project_id: str, fixture: str) -> Path:
    target = PROJECTS / project_id
    shutil.copytree(FIXTURES / fixture, target)
    return target


def write_fixture(project_id: str, files: dict) -> Path:
    target = PROJECTS / project_id
    target.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (target / name).write_text(text, encoding="utf-8")
    return target


def register(project_id: str, name: str, folder: Path, start: str, end: str) -> dict:
    with connection() as db:
        db.execute(
            """INSERT OR REPLACE INTO projects
               (id, name, folder_path, planned_start, planned_end, color)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (project_id, name, str(folder), start, end, "#4a90d9"),
        )
        row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return dict(row)


def scan(project_id: str, use_model=None) -> dict:
    return service.scan_all([project_id], use_model=use_model)


def state(project_id: str) -> dict:
    return service.state_for(project_id) or {}


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


def setup() -> None:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    PROJECTS.mkdir(parents=True, exist_ok=True)
    initialize_database()
    config_store.save_settings(
        {
            "enabled": True,
            "provider": "openai",
            "base_url": "https://api.example.test/v1",
            "model": "verify-model",
            "api_key": API_KEY,
        }
    )


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


def scenario_disabled() -> None:
    folder = copy_fixture("alpha-off", "alpha-clean")
    register("alpha-off", "Alpha 关闭模型", folder, "2026-09-01", "2026-12-20")
    before = tree_hashes(folder)
    run = scan("alpha-off", use_model=False)
    after = tree_hashes(folder)
    data = state("alpha-off")
    check("关闭模型时规则结果照常产出", run["result"] == "ok" and data["status"] == "ok")
    check("关闭模型时记录 model_status=disabled", data["model_status"] == "disabled")
    check("关闭模型时不发起任何请求", len(FAKE.calls) == 0)
    check("模型关闭的巡检仍不写入项目文件", before == after)


def scenario_agree() -> None:
    folder = copy_fixture("alpha-agree", "alpha-clean")
    register("alpha-agree", "Alpha 模型一致", folder, "2026-09-01", "2026-12-20")
    FAKE.reset()
    FAKE.mode = "agree"
    FAKE.ordinal = 2
    run = scan("alpha-agree")
    data = state("alpha-agree")
    check("规则与模型一致时状态为 ok", data["status"] == "ok", data.get("reason", ""))
    check("一致时记录 model_status=ok", data["model_status"] == "ok")
    check("一致时已接受阶段被推进", data["accepted_phase_ordinal"] == 2, str(data["accepted_phase_ordinal"]))
    check("一致时依据标注为规则加模型", data["current_basis"] == "rules_and_model", data["current_basis"])
    check("采纳了带引用的模型简介", "模型根据证据整理" in (data["model_summary"] or ""))
    check("简介来源指向被引用的文件", data["summary_source"] == "README.md", data["summary_source"] or "")
    check("模型引用被保存下来", len(data["model_citations"]) >= 1)
    check("巡检成功计数包含模型", run["model_ok"] == 1 and run["model_failed"] == 0)
    check("巡检记录保留模型开关状态", service.latest_run()["model_enabled"] is True)

    ok, message, elapsed = client.ping(config_store.get_settings())
    check("测试连接复用同一适配器", ok and "连接成功" in message and elapsed >= 0, message)

    FAKE.reset()
    FAKE.mode = "badauth"
    ok, message, _elapsed = client.ping(config_store.get_settings())
    check("测试连接能报告鉴权失败", not ok and "401" in message, message)


def scenario_preserve_on_failure() -> None:
    """Rules advance to Phase 3, but the provider fails: accepted stays Phase 2."""
    folder = copy_fixture("alpha-fail", "alpha-clean")
    register("alpha-fail", "Alpha 模型失败", folder, "2026-09-01", "2026-12-20")
    scan("alpha-fail", use_model=False)
    accepted_before = state("alpha-fail")["accepted_phase_ordinal"]

    with open(folder / "STATUS.md", "a", encoding="utf-8") as handle:
        handle.write("\n## 2026-11-02\n\n- 进入 Phase 3，灰度名单确认\n")

    FAKE.reset()
    FAKE.mode = "http500"
    run = scan("alpha-fail")
    data = state("alpha-fail")
    check("服务商 500 时项目标为 model_error", data["status"] == "model_error", data["status"])
    check("服务商 500 时已接受状态不被覆盖", data["accepted_phase_ordinal"] == accepted_before, str(data["accepted_phase_ordinal"]))
    check("候选阶段仍可供排查", data["candidate_phase_ordinal"] == 3, str(data["candidate_phase_ordinal"]))
    check("失败原因写入了状态", "HTTP 500" in (data["model_error"] or ""), data["model_error"] or "")
    check("失败的项目计入 run 统计", run["model_failed"] == 1 and run["result"] == "failed", run["result"])
    check("失败时生成可见的待处理项", any(item["kind"] == "model_issue" for item in service.pending_for("alpha-fail")))

    FAKE.mode = "timeout"
    scan("alpha-fail")
    data = state("alpha-fail")
    check("超时同样不推进已接受状态", data["accepted_phase_ordinal"] == accepted_before)
    check("超时提示可读", "没有响应" in (data["model_error"] or ""), data["model_error"] or "")

    FAKE.mode = "badauth"
    scan("alpha-fail")
    check("鉴权失败不会泄露密钥", API_KEY not in json.dumps(state("alpha-fail"), ensure_ascii=False))


def scenario_invalid_outputs() -> None:
    folder = copy_fixture("alpha-invalid", "alpha-clean")
    register("alpha-invalid", "Alpha 输出校验", folder, "2026-09-01", "2026-12-20")
    scan("alpha-invalid", use_model=False)
    accepted_before = state("alpha-invalid")["accepted_phase_ordinal"]

    cases = [
        ("malformed", "JSON"),
        ("bad_id", "不在发送给模型的证据中"),
        ("bad_quote", "找不到"),
        ("invented_date", "没有出现"),
    ]
    for mode, expected in cases:
        FAKE.reset()
        FAKE.mode = mode
        scan("alpha-invalid")
        data = state("alpha-invalid")
        check(f"{mode} 被拒绝为 model_error", data["status"] == "model_error", data["status"])
        check(f"{mode} 的失败原因可定位", expected in (data["model_error"] or ""), data["model_error"] or "")
        check(f"{mode} 不覆盖已接受状态", data["accepted_phase_ordinal"] == accepted_before)

    FAKE.reset()
    FAKE.mode = "agree"
    scan("alpha-invalid")
    check("修正后可恢复为 ok", state("alpha-invalid")["status"] == "ok", state("alpha-invalid")["status"])


def scenario_disagreement() -> None:
    folder = write_fixture(
        "zeta",
        {
            "README.md": "# 分歧样例\n\n用于验证规则与模型的分歧。Phase 3 的灰度方案尚在评审。\n",
            "STATUS.md": "# Status\n\n## 2026-10-29\n\n- 进入 Phase 2，接口联调开始\n",
        },
    )
    register("zeta", "Zeta 分歧", folder, "2026-10-01", "2026-12-31")
    scan("zeta", use_model=False)
    accepted_before = state("zeta")["accepted_phase_ordinal"]
    check("分歧样例先由规则判定为 Phase 2", accepted_before == 2, str(accepted_before))

    FAKE.reset()
    FAKE.mode = "agree"
    FAKE.ordinal = 3
    run = scan("zeta")
    data = state("zeta")
    check("规则与模型分歧时进入待确认", data["status"] == "needs_confirmation", data["status"])
    check("分歧原因同时给出两个阶段", "Phase 2" in data["reason"] and "Phase 3" in data["reason"], data["reason"])
    check("分歧时不推进已接受状态", data["accepted_phase_ordinal"] == accepted_before)
    check("分歧项出现在待确认列表", any(item["kind"] == "ambiguous_state" for item in service.pending_for("zeta")))
    check("分歧计入 run 的待确认数", run["projects_needing_confirmation"] == 1)

    FAKE.mode = "conflict"
    FAKE.ordinal = 2
    scan("zeta")
    data = state("zeta")
    check("模型自报冲突时同样待确认", data["status"] == "needs_confirmation", data["status"])
    check("冲突原因来自模型", "互相矛盾" in data["reason"], data["reason"])

    FAKE.mode = "agree"
    FAKE.ordinal = 2
    FAKE.confidence = "low"
    scan("zeta")
    data = state("zeta")
    check("低置信但两方一致时仍可接受", data["status"] == "ok", data["status"])
    check("低置信在备注中可见", any("low" in note for note in data["notes"]), " / ".join(data["notes"]))


def scenario_schedule() -> None:
    folder = copy_fixture("delta", "delta-schedule")
    register("delta", "Delta 排期", folder, "2026-09-01", "2026-11-30")
    FAKE.reset()
    FAKE.mode = "schedule"
    FAKE.ordinal = 1
    FAKE.schedule_date = "2026-12-15"
    scan("delta", use_model=False)

    before_project = service.project_detail("delta")["project"]
    run = scan("delta")
    detail = service.project_detail("delta")
    proposals = [item for item in detail["pending"] if item["kind"] == "schedule_change"]
    check("规则与模型读到同一日期时只保留一条提议", len(proposals) == 1, str(len(proposals)))
    check("提议不改动日历上的计划日期", detail["project"]["planned_end"] == before_project["planned_end"])
    check("排期提议计数进入 run", run["schedule_proposals"] == 1, str(run["schedule_proposals"]))

    if proposals:
        service.decide_pending(proposals[0]["id"], "accept")
    detail = service.project_detail("delta")
    check("用户接受后才更新计划日期", detail["project"]["planned_end"] == "2026-12-15", detail["project"]["planned_end"])
    check("接受后该提议不再待确认",
          not [item for item in detail["pending"] if item["kind"] == "schedule_change"])

    # A model-only proposal must also wait for confirmation.
    only = write_fixture(
        "eta",
        {
            "README.md": "# 验收样例\n\n用于验证模型读到的排期提议。\n",
            "STATUS.md": "# Status\n\n## 2026-10-28\n\n- 客户验收定在 2026-12-31，交付按此调整\n",
        },
    )
    register("eta", "Eta 验收", only, "2026-10-01", "2026-11-30")
    FAKE.reset()
    FAKE.mode = "schedule"
    FAKE.ordinal = None
    FAKE.schedule_date = "2026-12-31"
    scan("eta", use_model=False)
    before = service.project_detail("eta")["project"]["planned_end"]
    scan("eta")
    detail = service.project_detail("eta")
    proposed = [item for item in detail["pending"] if item["kind"] == "schedule_change"]
    check("模型读到的排期也先成为提议", len(proposed) == 1 and proposed[0]["candidate_value"] == "2026-12-31",
          str([(item['candidate_value']) for item in proposed]))
    check("模型排期提议不自动落到日历", detail["project"]["planned_end"] == before)


def scenario_privacy() -> None:
    payload = FAKE.calls[-1]["payload"] if FAKE.calls else {}
    blob = json.dumps(payload, ensure_ascii=False)
    check("请求体里没有 API 密钥", API_KEY not in blob)
    check("请求体里没有绝对路径", str(WORK_DIR) not in blob and "/Users/" not in blob)
    check("请求体里只有相对来源路径", "STATUS.md" in blob or "README.md" in blob)
    check("请求体小于最小化上限", len(blob) < 12000, str(len(blob)))

    provider = config_store.get_settings()
    check("配置接口不返回密钥", "api_key" not in provider and provider.get("api_key_set") is True)
    check("配置接口只给出掩码", provider["key_hint"].startswith("sk-") and API_KEY not in provider["key_hint"])

    credentials = WORK_DIR / "data" / "credentials.json"
    mode = stat.S_IMODE(credentials.stat().st_mode) if credentials.exists() else 0
    check("密钥文件在数据目录且权限为 0600", credentials.exists() and mode == 0o600, oct(mode))
    check("密钥不在仓库目录内", not str(credentials).startswith(str(BACKEND_DIR.parent / "src")))


def scenario_skipped() -> None:
    empty = PROJECTS / "empty"
    empty.mkdir(parents=True, exist_ok=True)
    register("empty", "Empty 无文档", empty, "2026-10-01", "2026-10-31")
    FAKE.reset()
    run = scan("empty")
    data = state("empty")
    check("没有证据时不调用模型", len(FAKE.calls) == 0, str(len(FAKE.calls)))
    check("跳过的模型状态可区分", data["model_status"] == "skipped", data["model_status"])
    check("无文档项目状态仍为 unknown", data["status"] == "unknown")
    check("跳过不计为模型失败", run["model_failed"] == 0)


def scenario_anthropic() -> None:
    folder = copy_fixture("alpha-anthropic", "alpha-clean")
    register("alpha-anthropic", "Alpha Anthropic", folder, "2026-09-01", "2026-12-20")
    config_store.save_settings(
        {
            "enabled": True,
            "provider": "anthropic",
            "base_url": "https://api.anthropic.test/v1",
            "model": "claude-test",
            "api_key": API_KEY,
        }
    )
    FAKE.reset()
    FAKE.mode = "agree"
    FAKE.ordinal = 2
    scan("alpha-anthropic")
    data = state("alpha-anthropic")
    last = FAKE.calls[-1]
    check("Anthropic 适配器可用", data["status"] == "ok" and data["model_status"] == "ok", data["status"])
    check("Anthropic 请求使用 messages 端点", last["url"].endswith("/v1/messages"), last["url"])
    check("Anthropic 请求带版本头", "anthropic-version" in last["headers"])
    check("Anthropic 记录服务商名", data["model_provider"] == "anthropic", data["model_provider"] or "")


def scenario_migration() -> None:
    legacy_dir = WORK_DIR / "legacy"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    legacy = legacy_dir / "dashboard.sqlite3"
    if legacy.exists():
        legacy.unlink()
    raw = sqlite3.connect(legacy)
    raw.execute("CREATE TABLE project_state (project_id TEXT PRIMARY KEY, status TEXT NOT NULL DEFAULT 'unknown')")
    raw.execute("CREATE TABLE scan_runs (id TEXT PRIMARY KEY)")
    raw.commit()
    raw.close()

    previous = os.environ["PROJECT_PROGRESS_DASHBOARD_DATA_DIR"]
    os.environ["PROJECT_PROGRESS_DASHBOARD_DATA_DIR"] = str(legacy_dir)
    try:
        initialize_database()
        raw = sqlite3.connect(legacy)
        columns = {row[1] for row in raw.execute("PRAGMA table_info(project_state)")}
        run_columns = {row[1] for row in raw.execute("PRAGMA table_info(scan_runs)")}
        tables = {row[0] for row in raw.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        raw.close()
    finally:
        os.environ["PROJECT_PROGRESS_DASHBOARD_DATA_DIR"] = previous

    check("旧数据库自动补齐模型列", "model_status" in columns and "model_error" in columns)
    check("旧数据库补齐巡检统计列", "model_ok" in run_columns and "model_failed" in run_columns)
    check("旧数据库补建服务商表", "provider_settings" in tables)


def scenario_readonly() -> None:
    folder = PROJECTS / "alpha-agree"
    before = tree_hashes(folder)
    config_store.save_settings({"enabled": True})
    config_store.save_settings({"model": "verify-model", "api_key": API_KEY})
    FAKE.reset()
    FAKE.mode = "agree"
    FAKE.ordinal = 2
    scan("alpha-agree")
    check("模型巡检后项目文件逐字节不变", before == tree_hashes(folder))

    detail = json.dumps(service.project_detail("alpha-agree"), ensure_ascii=False)
    check("项目详情响应不含密钥", API_KEY not in detail)


def main() -> int:
    setup()
    scenario_disabled()
    scenario_agree()
    scenario_preserve_on_failure()
    scenario_invalid_outputs()
    scenario_disagreement()
    scenario_schedule()
    scenario_privacy()
    scenario_skipped()
    scenario_anthropic()
    scenario_migration()
    scenario_readonly()

    passed = [item for item in RESULTS if item[1]]
    failed = [item for item in RESULTS if not item[1]]
    for name, ok, detail in RESULTS:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  → {detail}" if detail and not ok else ""))
    print("-" * 72)
    print(f"{len(passed)}/{len(RESULTS)} 项通过")
    if failed:
        print("失败项：" + "、".join(item[0] for item in failed))
        return 1
    print(f"临时目录：{WORK_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
