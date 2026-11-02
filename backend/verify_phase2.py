"""Phase 2 exit-criteria check.

Runs the read-only scanner against the synthetic fixtures and asserts the four
outcomes the roadmap asks for:

1. Dated updates are ordered correctly and the newest one wins.
2. Conflicting documents become "needs confirmation" instead of a guess.
3. Source files are byte-for-byte unchanged after a scan.
4. File modification times are never used to decide freshness.

Usage (from the repository root):

    backend/.venv/bin/python backend/verify_phase2.py

The script writes its SQLite database to a temporary directory, never to the
real user-data location, and never writes inside the fixtures.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

WORK_DIR = Path(tempfile.mkdtemp(prefix="ppd-phase2-verify-"))
os.environ["PROJECT_PROGRESS_DASHBOARD_DATA_DIR"] = str(WORK_DIR / "data")

from app import service  # noqa: E402
from app.db import connection, initialize_database  # noqa: E402

FIXTURES = BACKEND_DIR / "fixtures" / "synthetic"
RESULTS = []


def check(name: str, condition: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(condition), detail))


def tree_hashes(root: Path) -> dict:
    hashes = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            hashes[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def register(project_id: str, name: str, folder: Path, start: str, end: str) -> None:
    with connection() as db:
        db.execute(
            """INSERT OR REPLACE INTO projects
               (id, name, folder_path, planned_start, planned_end, color)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (project_id, name, str(folder), start, end, "#4a90d9"),
        )


def main() -> int:
    initialize_database()
    before = tree_hashes(FIXTURES)

    register("alpha", "Atlas 设备接入", FIXTURES / "alpha-clean", "2026-09-01", "2026-12-20")
    register("beta", "Beta 冲突样例", FIXTURES / "beta-conflict", "2026-09-01", "2026-12-01")
    register("gamma", "Gamma 无数据", FIXTURES / "gamma-nodata", "2026-09-01", "2026-12-01")
    register("delta", "Delta 排期变更", FIXTURES / "delta-schedule", "2026-09-01", "2026-11-30")
    register("epsilon", "Epsilon 未来日期", FIXTURES / "epsilon-future", "2026-09-01", "2026-12-01")

    run = service.scan_all()
    first_run = run

    alpha = service.state_for("alpha")
    alpha_phases = service.phases_for("alpha")
    alpha_evidence = service.evidence_for("alpha")
    check("alpha 状态为 ok", alpha["status"] == "ok", alpha["status"] + " " + alpha["reason"])
    check("alpha 当前阶段为 Phase 2", alpha["candidate_phase_ordinal"] == 2, str(alpha["candidate_phase"]))
    check(
        "alpha 阶段序列完整（0-3）",
        [phase["ordinal"] for phase in alpha_phases] == [0, 1, 2, 3],
        str([phase["ordinal"] for phase in alpha_phases]),
    )
    check("alpha 最新进展为 2026-10-29", alpha["newest_record_date"] == "2026-10-29", str(alpha["newest_record_date"]))
    check(
        "alpha 已完成阶段带明确日期",
        alpha_phases[0]["end_date"] == "2026-09-05" and alpha_phases[1]["end_date"] == "2026-10-20",
        f"{alpha_phases[0]['end_date']} / {alpha_phases[1]['end_date']}",
    )
    check(
        "alpha 未给未开始阶段编造日期",
        alpha_phases[3]["start_date"] is None and alpha_phases[3]["end_date"] is None,
        f"{alpha_phases[3]['start_date']} / {alpha_phases[3]['end_date']}",
    )
    check(
        "alpha 排除 node_modules",
        all(not item["source_path"].startswith("node_modules") for item in alpha_evidence),
        str(sorted({item["source_path"] for item in alpha_evidence})),
    )
    check(
        "alpha 忽略代码块与 HTML 注释中的日期",
        all(item["record_date"] not in ("2030-01-01", "2030-02-02") for item in alpha_evidence),
        str(sorted({str(item["record_date"]) for item in alpha_evidence})),
    )
    check(
        "alpha 证据按日期倒序",
        [item["record_date"] for item in alpha_evidence if item["record_date"]]
        == sorted([item["record_date"] for item in alpha_evidence if item["record_date"]], reverse=True),
    )
    check(
        "alpha 只把 2026-10-29 标为最新",
        {item["record_date"] for item in alpha_evidence if item["is_newest"]} == {"2026-10-29"},
        str({item["record_date"] for item in alpha_evidence if item["is_newest"]}),
    )
    check("alpha 提取了 README 简介", "设备接入平台" in (alpha["summary"] or ""), (alpha["summary"] or "")[:40])

    beta = service.state_for("beta")
    beta_pending = service.pending_for("beta")
    check("beta 标记为待确认", beta["status"] == "needs_confirmation", beta["status"] + " " + beta["reason"])
    check("beta 给出冲突原因", "当前阶段" in (beta["reason"] or ""), beta["reason"])
    check(
        "beta 生成待确认条目",
        any(item["kind"] == "ambiguous_state" for item in beta_pending),
        str([item["kind"] for item in beta_pending]),
    )
    check("beta 不写入候选阶段", beta["candidate_phase"] is None, str(beta["candidate_phase"]))

    gamma = service.state_for("gamma")
    check("gamma 状态为 unknown", gamma["status"] == "unknown", gamma["status"] + " " + gamma["reason"])
    check("gamma 不推测阶段", gamma["candidate_phase"] is None, str(gamma["candidate_phase"]))

    delta = service.state_for("delta")
    delta_pending = [item for item in service.pending_for("delta") if item["kind"] == "schedule_change"]
    with connection() as db:
        delta_project = dict(db.execute("SELECT * FROM projects WHERE id = 'delta'").fetchone())
    check("delta 生成 1 条排期变更", len(delta_pending) == 1, str(len(delta_pending)))
    check(
        "delta 候选结束日期为 2026-12-15",
        delta_pending and delta_pending[0]["candidate_value"] == "2026-12-15" and delta_pending[0]["field"] == "planned_end",
        str(delta_pending[0] if delta_pending else None),
    )
    check(
        "delta 未自动修改项目排期",
        delta_project["planned_end"] == "2026-11-30",
        delta_project["planned_end"],
    )
    check("delta 当前阶段仍可确定", delta["candidate_phase_ordinal"] == 1, str(delta["candidate_phase"]))
    check(
        "delta 不把“计划开始 Phase 2”当排期变更",
        all(item["candidate_value"] != "2026-11-01" for item in delta_pending),
        str([item["candidate_value"] for item in delta_pending]),
    )

    epsilon = service.state_for("epsilon")
    check(
        "epsilon 忽略未来日期（2099）",
        epsilon["newest_record_date"] == "2026-10-22",
        str(epsilon["newest_record_date"]),
    )

    after = tree_hashes(FIXTURES)
    check("源文件字节未变化", before == after, f"{len(before)} 个文件比对")
    check("未在源目录新增文件", set(before) == set(after), str(sorted(set(after) - set(before))))

    # Modification time must never influence freshness: make the newest-dated
    # file look ancient and the oldest-dated file look brand new, then rescan.
    copy_root = WORK_DIR / "alpha-copy"
    shutil.copytree(FIXTURES / "alpha-clean", copy_root)
    os.utime(copy_root / "STATUS.md", (946684800, 946684800))  # 2000-01-01
    os.utime(copy_root / "ROADMAP.md", (3315686400, 3315686400))  # 2075-01-01
    register("alpha-copy", "Atlas 副本", copy_root, "2026-09-01", "2026-12-20")
    service.scan_all(["alpha-copy"])
    copied = service.state_for("alpha-copy")
    check(
        "文件修改时间不影响状态判断",
        copied["newest_record_date"] == "2026-10-29" and copied["candidate_phase_ordinal"] == 2,
        f"{copied['newest_record_date']} / {copied['candidate_phase']}",
    )

    # A newer dated record must move the project forward and be reported as a
    # change in the scan summary.
    status_copy = copy_root / "STATUS.md"
    status_copy.write_text(
        status_copy.read_text(encoding="utf-8") + "\n## 2026-10-31\n\n- 进入 Phase 3，灰度名单确认\n",
        encoding="utf-8",
    )
    service.scan_all(["alpha-copy"])
    changed = service.state_for("alpha-copy")
    change_run = service.latest_run()
    check(
        "新增更晚的进展记录后阶段前进",
        changed["candidate_phase_ordinal"] == 3,
        str(changed["candidate_phase"]),
    )
    check(
        "巡检摘要记录了阶段变化",
        any(item["kind"] == "phase" and item["current"] for item in change_run["changes"]),
        str(change_run["changes"]),
    )

    # Unavailable path keeps the last accepted state.
    register("delta", "Delta 排期变更", FIXTURES / "does-not-exist", "2026-09-01", "2026-11-30")
    service.scan_all(["delta"])
    delta_after_failure = service.state_for("delta")
    check(
        "路径不可访问时保留上次状态",
        delta_after_failure["candidate_phase_ordinal"] == 1
        and delta_after_failure["scan_error"] is not None,
        f"{delta_after_failure['candidate_phase']} / {delta_after_failure['scan_error']}",
    )
    run = service.latest_run()
    check("巡检结果记录为 partial/failed", run["result"] in ("partial", "failed"), run["result"])

    failed = [item for item in RESULTS if not item[1]]
    print()
    print("Phase 2 验收检查")
    print("=" * 72)
    for name, ok, detail in RESULTS:
        mark = "PASS" if ok else "FAIL"
        suffix = f"  ({detail})" if detail and not ok else ""
        print(f"[{mark}] {name}{suffix}")
    print("-" * 72)
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} 项通过")
    print(
        f"首次巡检：{first_run['result']} · 项目 {first_run['projects_total']} 个 "
        f"（ok {first_run['projects_ok']} / 待确认 {first_run['projects_needing_confirmation']} / "
        f"未知 {first_run['projects_unknown']} / 失败 {first_run['projects_failed']}）"
    )
    print(f"最后一次巡检：{run['result']} · {run['message']}")
    if failed:
        print()
        print("失败项：")
        for name, _, detail in failed:
            print(f"  - {name}: {detail}")
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        shutil.rmtree(WORK_DIR, ignore_errors=True)
