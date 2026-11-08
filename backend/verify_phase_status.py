"""Phase-status rules check.

Covers the three rules added after the 3D demo project was shown as "进行中"
after delivery:

1. A "当前阶段 / 阶段" table row reads the phase's own status instead of being
   hard-coded to current; only a non-completed phase counts as in progress.
2. "待验收 / 待用户验收 / awaiting acceptance / 已交付待验收" maps to
   pending_acceptance and is resolved as the current phase.
3. When every phase is completed, the last phase is shown as current with
   basis=all_completed, even if a stale "当前阶段" row disagrees.

Usage (from the repository root):

    backend/.venv/bin/python backend/verify_phase_status.py

The script writes its synthetic documents to a temporary directory and never
touches a real project folder.
"""

from __future__ import annotations

import sys
import tempfile
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

from app.scanner.discovery import discover_markdown_files  # noqa: E402
from app.scanner.extract import classify_status, extract_phases  # noqa: E402
from app.scanner.markdown_doc import parse_document  # noqa: E402
from app.scanner.state import build_candidate  # noqa: E402

WORK_DIR = Path(tempfile.mkdtemp(prefix="ppd-phase-status-verify-"))
PROJECT = {"id": "synthetic", "name": "阶段样例", "planned_start": "2026-01-01", "planned_end": "2026-12-31"}
TODAY = date(2026, 11, 4)
RESULTS = []


def check(name: str, condition: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(condition), detail))


def candidate_for(name: str, files: dict):
    root = WORK_DIR / name
    root.mkdir(parents=True, exist_ok=True)
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    discovery = discover_markdown_files(root)
    documents = [parse_document(item.relative_path, item.text) for item in discovery.files]
    return build_candidate(PROJECT, discovery, documents, TODAY)


def main() -> int:
    # ------------------------------------------------------------------
    # 1. Status vocabulary
    # ------------------------------------------------------------------
    cases = {
        "待验收": "pending_acceptance",
        "Phase 2 待用户验收": "pending_acceptance",
        "演示已交付，等待用户验收": "pending_acceptance",
        "Delivered 2026-11-03 waiting for acceptance": "pending_acceptance",
        "已交付待验收": "pending_acceptance",
        "Delivered 2026-11-03": "completed",
        "Phase 2 已完成": "completed",
        "Phase 2 进行中": "current",
        "Phase 2 未开始": "upcoming",
    }
    for text, expected in cases.items():
        check(f"“{text}” 归类为 {expected}", classify_status(text) == expected, classify_status(text))

    # ------------------------------------------------------------------
    # 2. "当前阶段" row reads the phase's own status
    # ------------------------------------------------------------------
    fallback_doc = parse_document(
        "STATUS.md",
        "# 示例\n\n## 进度\n\n| 当前阶段 | M2 交付 |\n",
    )
    fallback = [item for item in extract_phases(fallback_doc) if item.ordinal == 2]
    check("当前阶段行没有状态时仍视为进行中", bool(fallback) and fallback[0].status == "current")
    check("当前阶段行没有状态时标记为回退值", bool(fallback) and fallback[0].status_fallback is True)

    completed_row = parse_document(
        "STATUS.md",
        "# 示例\n\n## 进度\n\n| 当前阶段 | M2 交付 | 已完成 |\n",
    )
    completed = [item for item in extract_phases(completed_row) if item.ordinal == 2]
    check(
        "当前阶段行写了已完成时不再视为进行中",
        bool(completed) and completed[0].status == "completed" and not completed[0].status_fallback,
        completed[0].status if completed else "missing",
    )

    acceptance_row = parse_document(
        "STATUS.md",
        "# 示例\n\n## 进度\n\n| 当前阶段 | M2 待验收 |\n",
    )
    acceptance = [item for item in extract_phases(acceptance_row) if item.ordinal == 2]
    check(
        "当前阶段行写待验收时归为待验收",
        bool(acceptance) and acceptance[0].status == "pending_acceptance",
        acceptance[0].status if acceptance else "missing",
    )

    status_line = parse_document(
        "STATUS.md",
        "# 示例\n\n## 进度\n\n**Status:** Phase 2 待用户验收\n\n| 当前阶段 | M2 交付 |\n",
    )
    status_line_phases = [item for item in extract_phases(status_line) if item.ordinal == 2]
    check(
        "Status 行命名为待验收时覆盖当前阶段默认值",
        bool(status_line_phases) and status_line_phases[0].status == "pending_acceptance",
        status_line_phases[0].status if status_line_phases else "missing",
    )

    # ------------------------------------------------------------------
    # 3. Pending acceptance is still the current phase, delivery date kept
    # ------------------------------------------------------------------
    pending = candidate_for(
        "pending-acceptance",
        {
            "ROADMAP.md": (
                "# 示例\n\n## Phase 1 3D 演示 MVP\n\n"
                "**Status:** Delivered 2026-11-03（Phase 1 交付已完成，等待用户验收）。\n"
            )
        },
    )
    phase = next((item for item in pending.phases if item.ordinal == 1), None)
    check("待验收阶段没有被当成已完成", phase is not None and phase.status == "pending_acceptance", str(phase and phase.status))
    check("待验收阶段保留交付日期", phase is not None and phase.end == date(2026, 11, 3), str(phase and phase.end))
    check("待验收阶段被视为当前阶段", pending.current is not None and pending.current.ordinal == 1, str(pending.current))
    check("待验收阶段项目状态为 ok", pending.status == "ok", pending.status + " " + pending.reason)

    # ------------------------------------------------------------------
    # 4. All phases completed -> last phase, basis=all_completed
    # ------------------------------------------------------------------
    all_done = candidate_for(
        "all-completed",
        {
            "ROADMAP.md": (
                "# 示例\n\n## 阶段规划\n\n"
                "| 里程碑 | 名称 | 状态 |\n"
                "| M0 | 启动 | 已完成 |\n"
                "| M1 | 设计 | 已完成 |\n"
                "| M2 | 实现 | 已完成 |\n"
                "| M3 | 验收 | 已完成 |\n"
            ),
            "STATUS.md": "# 示例\n\n## 进度\n\n| 当前阶段 | M2 |\n",
        },
    )
    check(
        "全部完成后当前阶段取编号最大的阶段",
        all_done.current is not None and all_done.current.ordinal == 3,
        str(all_done.current),
    )
    check("全部完成时 basis 为 all_completed", all_done.basis == "all_completed", all_done.basis)
    check("过期的当前阶段行不制造文档冲突", all_done.status == "ok", all_done.status + " " + all_done.reason)
    check(
        "全部完成后所有阶段状态仍为已完成",
        all(item.status == "completed" for item in all_done.phases),
        str([(item.ordinal, item.status) for item in all_done.phases]),
    )

    print()
    print("阶段状态规则检查")
    print("=" * 72)
    failed = [item for item in RESULTS if not item[1]]
    for name, ok, detail in RESULTS:
        print(("[PASS] " if ok else "[FAIL] ") + name + (f"  ({detail})" if detail and not ok else ""))
    print("-" * 72)
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} 项通过")
    print(f"临时目录：{WORK_DIR}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
