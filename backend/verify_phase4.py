"""Phase 4 exit-criteria check.

Covers login startup, the once-a-day automatic scan, failure timestamps,
manual retry, and opening a project folder. Windows registry and macOS
LaunchAgent branches run against fakes, so this script never writes a real
startup item or calls the real ``launchctl``.

Usage (from the repository root):

    backend/.venv/bin/python backend/verify_phase4.py
"""

from __future__ import annotations

import hashlib
import json
import os
import plistlib
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

WORK_DIR = Path(tempfile.mkdtemp(prefix="ppd-phase4-verify-"))
os.environ["PROJECT_PROGRESS_DASHBOARD_DATA_DIR"] = str(WORK_DIR / "data")

from app import cli, daily, routes, service, system  # noqa: E402
from app.db import connection, initialize_database  # noqa: E402
from app.schemas import StartupInput  # noqa: E402

FIXTURES = BACKEND_DIR / "fixtures" / "synthetic"
PROJECTS = WORK_DIR / "projects"
HOME_DIR = WORK_DIR / "home"
RESULTS = []


def check(name: str, condition: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(condition), detail))


def tree_hashes(root: Path) -> dict:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def register(name: str, folder: Path | str, start: str, end: str) -> str:
    from uuid import uuid4

    project_id = str(uuid4())
    with connection() as db:
        db.execute(
            "INSERT INTO projects (id, name, folder_path, planned_start, planned_end, color) VALUES (?, ?, ?, ?, ?, ?)",
            (project_id, name, str(folder), start, end, "#465ed8"),
        )
    return project_id


def scan_count(trigger: str | None = None) -> int:
    with connection() as db:
        if trigger:
            row = db.execute("SELECT COUNT(*) AS total FROM scan_runs WHERE trigger = ?", (trigger,)).fetchone()
        else:
            row = db.execute("SELECT COUNT(*) AS total FROM scan_runs").fetchone()
    return int(row["total"])


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeKey:
    def __init__(self, path: str) -> None:
        self.path = path
        self.values: dict = {}


class FakeWinreg:
    """The subset of ``winreg`` used by ``windows_startup``."""

    HKEY_CURRENT_USER = object()
    KEY_READ = 1
    KEY_WRITE = 2
    REG_SZ = 1

    def __init__(self) -> None:
        self.keys: dict = {}

    def OpenKey(self, root, path, reserved, access):
        if path not in self.keys:
            raise FileNotFoundError(path)
        return self.keys[path]

    def CreateKeyEx(self, root, path, reserved, access):
        return self.keys.setdefault(path, FakeKey(path))

    def QueryValueEx(self, key, name):
        if name not in key.values:
            raise FileNotFoundError(name)
        return key.values[name], self.REG_SZ

    def SetValueEx(self, key, name, reserved, kind, value):
        key.values[name] = value

    def DeleteValue(self, key, name):
        if name not in key.values:
            raise FileNotFoundError(name)
        del key.values[name]

    def CloseKey(self, key):
        return None


class LaunchctlRecorder:
    def __init__(self, code: int = 0, output: str = "") -> None:
        self.calls: list = []
        self.code = code
        self.output = output

    def __call__(self, arguments):
        self.calls.append(list(arguments))
        return self.code, self.output


class HealthHandler(BaseHTTPRequestHandler):
    payload: dict = {}

    def do_GET(self):
        body = json.dumps(self.payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        return None


def health_server(payload: dict) -> ThreadingHTTPServer:
    handler = type("Handler", (HealthHandler,), {"payload": payload})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> int:
    initialize_database()
    PROJECTS.mkdir(parents=True, exist_ok=True)
    HOME_DIR.mkdir(parents=True, exist_ok=True)

    # A private copy so the repository fixtures stay untouched.
    alpha = PROJECTS / "alpha"
    shutil.copytree(FIXTURES / "alpha-clean", alpha)

    # ------------------------------------------------------------------
    # 1. At most one automatic scan per local calendar day
    # ------------------------------------------------------------------
    check("首次启动可领取当天自动巡检", daily.claim("2026-11-02") is True)
    check("同一天第二次领取被拒绝", daily.claim("2026-11-02") is False)

    project_id = register("Alpha 样例", alpha, "2026-09-01", "2026-12-20")

    first = daily.run_if_due(day="2026-11-03")
    check("新的一天会执行自动巡检", first["ran"] is True and first["reason"] == "first_start_of_day")
    check("自动巡检记为 auto", service.latest_run()["trigger"] == "auto")
    with connection() as db:
        day_row = db.execute("SELECT result FROM daily_scans WHERE scan_date = '2026-11-03'").fetchone()
    check("自动巡检写入当天记录", day_row is not None and day_row["result"] in ("ok", "partial", "failed"))

    before = scan_count("auto")
    second = daily.run_if_due(day="2026-11-03")
    check("当天重复启动不再巡检", second["ran"] is False and second["reason"] == "already_ran_today")
    check("当天只产生一条自动巡检记录", scan_count("auto") == before == 1)

    third = daily.run_if_due(day="2026-11-04")
    check("跨日再次启动会再巡检一次", third["ran"] is True and scan_count("auto") == 2)

    failures = []

    def boom(trigger="auto"):
        raise RuntimeError("scanner exploded")

    try:
        daily.run_if_due(day="2026-11-06", scanner=boom)
    except RuntimeError:
        pass
    with connection() as db:
        row = db.execute("SELECT * FROM daily_scans WHERE scan_date = '2026-11-06'").fetchone()
    check("自动巡检异常也会记录失败状态", dict(row)["result"] == "failed")
    check("失败后当天不再自动重试", daily.run_if_due(day="2026-11-06", scanner=boom)["ran"] is False)

    # Two processes claiming the same day: exactly one may win.
    claim_script = (
        "import sys; sys.path.insert(0, %r);"
        "from app.db import initialize_database; initialize_database();"
        "from app import daily; print('CLAIM' if daily.claim('2026-11-07') else 'SKIP')"
        % str(BACKEND_DIR)
    )
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", claim_script],
            env={**os.environ, "PROJECT_PROGRESS_DASHBOARD_DATA_DIR": str(WORK_DIR / "data")},
            stdout=subprocess.PIPE,
            text=True,
        )
        for _ in range(4)
    ]
    outputs = [process.communicate(timeout=60)[0].strip() for process in processes]
    check(
        "多进程同时启动只有一次领取成功",
        outputs.count("CLAIM") == 1 and outputs.count("SKIP") == 3,
        str(outputs),
    )

    # ------------------------------------------------------------------
    # 2. Failure timestamp, retained state, manual retry
    # ------------------------------------------------------------------
    service.scan_all(trigger="manual")
    state = service.state_for(project_id)
    accepted_before = (state["accepted_phase"], state["accepted_phase_ordinal"])
    success_before = state["last_success_at"]
    check("手动巡检成功且无失败时间", state["scan_error"] is None and state["last_failure_at"] is None)

    moved = PROJECTS / "alpha-moved"
    alpha.rename(moved)
    run = service.scan_all(trigger="manual")
    failed_state = service.state_for(project_id)
    check("路径失联时巡检整体为失败", run["result"] == "failed")
    check("失败时写入失败时间", bool(failed_state["last_failure_at"]))
    check("失败时保留上次成功时间", failed_state["last_success_at"] == success_before)
    check("失败时保留已接受阶段", (failed_state["accepted_phase"], failed_state["accepted_phase_ordinal"]) == accepted_before)
    check("失败时可以手动重试（接口仍可调用）", routes.trigger_scan(None, None)["result"] == "failed")

    moved.rename(alpha)
    retry = service.scan_all(trigger="manual")
    recovered = service.state_for(project_id)
    check("恢复路径后重试成功", retry["result"] == "ok" and recovered["scan_error"] is None)
    check("恢复后仍保留历史失败时间", bool(recovered["last_failure_at"]))
    check("恢复后重新推进已接受阶段", recovered["accepted_phase"] == accepted_before[0])
    check("手动巡检记为 manual", service.latest_run()["trigger"] == "manual")

    # ------------------------------------------------------------------
    # 3. Open project folder through the platform adapter
    # ------------------------------------------------------------------
    captured = {}

    def capture(command):
        captured["command"] = command
        return 0

    result = system.open_folder(str(alpha), platform="macos", runner=capture)
    check("macOS 使用 open 打开文件夹", captured["command"][0] == "open" and result["opened"] is True)
    check("打开的是登记的绝对路径", captured["command"][1] == str(alpha.resolve()))

    system.open_folder(str(alpha), platform="windows", runner=capture)
    check("Windows 使用 explorer", captured["command"][0] == "explorer")
    system.open_folder(str(alpha), platform="linux", runner=capture)
    check("Linux 使用 xdg-open", captured["command"][0] == "xdg-open")

    called = []

    def should_not_run(command):
        called.append(command)
        return 0

    missing = PROJECTS / "not-here"
    try:
        system.open_folder(str(missing), platform="macos", runner=should_not_run)
        missing_error = ""
    except system.OpenFolderError as error:
        missing_error = str(error)
    check("路径不存在时给出可读错误", "不存在" in missing_error)
    check("路径不存在时不会调用系统命令", called == [])

    afile = PROJECTS / "note.md"
    afile.write_text("x", encoding="utf-8")
    try:
        system.open_folder(str(afile), platform="macos", runner=should_not_run)
        not_dir_error = ""
    except system.OpenFolderError as error:
        not_dir_error = str(error)
    check("路径不是文件夹时拒绝打开", "不是文件夹" in not_dir_error)

    try:
        system.open_folder("   ", platform="macos", runner=should_not_run)
        empty_error = ""
    except system.OpenFolderError as error:
        empty_error = str(error)
    check("空路径被拒绝", "为空" in empty_error)

    weird = PROJECTS / "a b;$HOME `echo`"
    weird.mkdir()
    system.open_folder(str(weird), platform="macos", runner=capture)
    check("含空格与元字符的路径原样作为单个参数", captured["command"][1] == str(weird.resolve()))

    # The route is exercised with a stand-in so verification never opens Finder.
    opened_paths = []
    original_open = system.open_folder

    def fake_open(raw_path):
        opened_paths.append(raw_path)
        return {"opened": True, "path": raw_path, "handler": "fake"}

    system.open_folder = fake_open
    folder_result = routes.open_project_folder(project_id)
    system.open_folder = original_open
    check("接口只打开已登记项目的文件夹", folder_result["opened"] is True and opened_paths == [str(alpha)])

    broken_id = register("失联项目", PROJECTS / "gone", "2026-09-01", "2026-10-01")
    try:
        routes.open_project_folder(broken_id)
        route_error = ""
    except Exception as error:  # HTTPException
        route_error = str(getattr(error, "detail", error))
    check("接口对不可访问路径返回错误而不是崩溃", "不存在" in route_error)
    try:
        routes.open_project_folder("no-such-id")
        unknown_error = ""
    except Exception as error:
        unknown_error = str(getattr(error, "detail", error))
    check("未知项目返回 404 文案", "不存在" in unknown_error)

    # ------------------------------------------------------------------
    # 4. Windows login startup (fake registry)
    # ------------------------------------------------------------------
    registry = FakeWinreg()
    system.registry_module = registry
    system.platform_id = lambda: "windows"

    windows_status = system.enable_startup()
    command = registry.keys[r"Software\Microsoft\Windows\CurrentVersion\Run"].values["ProjectProgressDashboard"]
    launcher_text = (BACKEND_DIR / "launch_hidden.vbs").read_text(encoding="utf-8")
    check("Windows 启动项写入 Run 键", bool(command))
    check(
        "启动命令使用隐藏启动器",
        "wscript.exe" in command and "launch_hidden.vbs" in command and (BACKEND_DIR / "launch_hidden.vbs").is_file(),
    )
    check("隐藏启动器指向 run.py 与 serve --open-browser", "run.py" in launcher_text and "serve --open-browser" in launcher_text)
    check("隐藏启动器不依赖被策略禁止的 pythonw", r"\.venv\Scripts\pythonw.exe" not in launcher_text)
    check("启动状态为已启用", windows_status["enabled"] is True and windows_status["platform"] == "windows")
    check("状态里的命令与注册表一致", windows_status["command"] == command)
    check("状态给出注册表位置", windows_status["location"].startswith("HKEY_CURRENT_USER"))

    system.enable_startup()
    check("重复启用不会产生第二条启动项", len(registry.keys[r"Software\Microsoft\Windows\CurrentVersion\Run"].values) == 1)

    disabled = system.disable_startup()
    check("关闭后从注册表移除", disabled["enabled"] is False and not registry.keys[r"Software\Microsoft\Windows\CurrentVersion\Run"].values)
    check("重复关闭不报错", system.disable_startup()["enabled"] is False)
    check("关闭后状态为未启用", system.startup_status()["enabled"] is False)

    # ------------------------------------------------------------------
    # 5. macOS login startup (fake launchctl, temporary home)
    # ------------------------------------------------------------------
    system.home_override = HOME_DIR
    system.python_executable = "/Applications/Python 3.11/bin/python3"
    system.platform_id = lambda: "macos"
    if not hasattr(os, "getuid"):
        # macOS 的 launchctl 域名需要 uid；在非 POSIX 系统上仅用于模拟。
        system.macos_startup._uid = lambda: 501
    recorder = LaunchctlRecorder()
    system.launchctl_runner = recorder

    mac_status = system.enable_startup()
    plist_path = Path(HOME_DIR) / "Library" / "LaunchAgents" / "com.projectprogressdashboard.dashboard.plist"
    check("macOS 写入 LaunchAgent plist", plist_path.is_file())
    payload = plistlib.loads(plist_path.read_bytes())
    check("plist 在登录时运行", payload.get("RunAtLoad") is True and payload.get("KeepAlive") is False)
    check("plist 指向 run.py serve --open-browser", payload["ProgramArguments"][1].endswith("run.py") and payload["ProgramArguments"][2:] == ["serve", "--open-browser"])
    check("plist 把输出写入日志文件", str(payload.get("StandardErrorPath", "")).endswith("dashboard.log"))
    check("启用时调用 launchctl bootstrap", any(call[0] == "bootstrap" for call in recorder.calls))
    check("macOS 启动状态为已启用", mac_status["enabled"] is True)
    check("位置显示为 ~ 路径", mac_status["location"].replace("\\", "/").startswith("~/Library/LaunchAgents/"))

    system.disable_startup()
    check("关闭后删除 plist", not plist_path.exists())
    check("关闭时调用 launchctl bootout", any(call[0] == "bootout" for call in recorder.calls))
    check("删除后状态为未启用", system.startup_status()["enabled"] is False)

    failing = LaunchctlRecorder(code=1, output="Bootstrap failed: 5: Input/output error")
    system.launchctl_runner = failing
    fallback = system.enable_startup()
    check("launchctl 失败时给出可手动执行的命令", "launchctl bootstrap" in fallback["manual_step"])
    check("launchctl 失败仍保留已写入的启动项文件", plist_path.is_file())
    system.disable_startup()

    # ------------------------------------------------------------------
    # 6. Single-instance probe and CLI surface
    # ------------------------------------------------------------------
    ours = health_server({"service": "project-progress-dashboard-api", "status": "ok"})
    port = ours.server_address[1]
    check("能识别已在运行的看板", cli.probe_running(port, timeout=2) is True)

    other = health_server({"service": "some-other-app", "status": "ok"})
    check("不会把别的服务当成看板", cli.probe_running(other.server_address[1], timeout=2) is False)

    closed_socket = socket.socket()
    closed_socket.bind(("127.0.0.1", 0))
    closed_port = closed_socket.getsockname()[1]
    closed_socket.close()
    check("端口未监听时返回否", cli.probe_running(closed_port, timeout=0.3) is False)
    ours.shutdown()
    other.shutdown()

    parsed = cli.build_parser().parse_args(["serve", "--open-browser", "--port", "8123"])
    check("serve 支持 --open-browser 与 --port", parsed.open_browser is True and parsed.port == 8123)
    import contextlib
    import io

    with contextlib.redirect_stdout(io.StringIO()):
        check("未指定子命令时打印帮助", cli.main([]) == 2)
    check("启动命令使用当前解释器", system.launcher_arguments()[0] == "/Applications/Python 3.11/bin/python3")
    check(
        "启动命令指向真实的 run.py",
        (BACKEND_DIR / "run.py").is_file()
        and system.launcher_arguments()[1].replace("\\", "/").endswith("backend/run.py"),
    )

    # ------------------------------------------------------------------
    # 7. API surface and old-database upgrade
    # ------------------------------------------------------------------
    system.platform_id = lambda: "macos"
    service_state = routes.get_system()
    check("系统接口返回平台与启动信息", service_state["platform"] == "macos" and "enabled" in service_state["startup"])
    check("系统接口返回每日巡检状态", service_state["daily"]["today"] == daily.local_day())
    check("系统接口返回数据与日志路径", service_state["paths"]["log"].endswith("dashboard.log"))
    check("健康检查报告 Phase 4", routes.health()["phase"] == 4)
    check("关闭启动项走同一个接口", routes.set_startup(StartupInput(enabled=False))["enabled"] is False)

    legacy = WORK_DIR / "legacy" / "dashboard.sqlite3"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy_db = sqlite3.connect(legacy)
    legacy_db.executescript(
        """
        CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT NOT NULL, folder_path TEXT NOT NULL,
            planned_start TEXT NOT NULL, planned_end TEXT NOT NULL, color TEXT NOT NULL,
            archived INTEGER NOT NULL DEFAULT 0, created_at TEXT, updated_at TEXT);
        CREATE TABLE project_state (project_id TEXT PRIMARY KEY, status TEXT NOT NULL DEFAULT 'unknown',
            reason TEXT NOT NULL DEFAULT '', summary TEXT NOT NULL DEFAULT '',
            summary_source TEXT NOT NULL DEFAULT '', accepted_phase TEXT, accepted_phase_ordinal INTEGER,
            accepted_phase_start TEXT, accepted_phase_end TEXT, candidate_phase TEXT,
            candidate_phase_ordinal INTEGER, candidate_phase_start TEXT, candidate_phase_end TEXT,
            current_basis TEXT NOT NULL DEFAULT 'none', candidate_testing INTEGER NOT NULL DEFAULT 0,
            newest_record_date TEXT, newest_record_claim TEXT, newest_record_source TEXT,
            files_scanned INTEGER NOT NULL DEFAULT 0, evidence_count INTEGER NOT NULL DEFAULT 0,
            scan_error TEXT, notes TEXT NOT NULL DEFAULT '[]', scanned_at TEXT,
            last_success_at TEXT, updated_at TEXT);
        CREATE TABLE scan_runs (id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
            result TEXT NOT NULL, projects_total INTEGER NOT NULL DEFAULT 0,
            projects_ok INTEGER NOT NULL DEFAULT 0, projects_needing_confirmation INTEGER NOT NULL DEFAULT 0,
            projects_unknown INTEGER NOT NULL DEFAULT 0, projects_failed INTEGER NOT NULL DEFAULT 0,
            schedule_proposals INTEGER NOT NULL DEFAULT 0, changes TEXT NOT NULL DEFAULT '[]',
            message TEXT NOT NULL DEFAULT '');
        INSERT INTO project_state (project_id, status, accepted_phase, accepted_phase_ordinal)
            VALUES ('old', 'ok', 'Phase 2', 2);
        """
    )
    legacy_db.commit()
    legacy_db.close()

    os.environ["PROJECT_PROGRESS_DASHBOARD_DATA_DIR"] = str(legacy.parent)
    initialize_database()
    with connection() as db:
        columns = {row["name"] for row in db.execute("PRAGMA table_info(project_state)")}
        run_columns = {row["name"] for row in db.execute("PRAGMA table_info(scan_runs)")}
        kept = db.execute("SELECT accepted_phase FROM project_state WHERE project_id = 'old'").fetchone()
    check("旧库自动补上 last_failure_at", "last_failure_at" in columns)
    check("旧库自动补上 trigger", "trigger" in run_columns)
    check("旧库原有数据保持不变", kept is not None and kept["accepted_phase"] == "Phase 2")
    check("旧库补建每日巡检表", bool(db_has_table("daily_scans")))

    os.environ["PROJECT_PROGRESS_DASHBOARD_DATA_DIR"] = str(WORK_DIR / "data")

    # ------------------------------------------------------------------
    # 8. Read-only guarantee still holds
    # ------------------------------------------------------------------
    before_hash = tree_hashes(PROJECTS)
    service.scan_all(trigger="manual")
    after_hash = tree_hashes(PROJECTS)
    check("巡检后合成样例逐字节不变", before_hash == after_hash)

    return report()


def db_has_table(name: str) -> bool:
    with connection() as db:
        row = db.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone()
    return row is not None


def report() -> int:
    failed = [item for item in RESULTS if not item[1]]
    print("-" * 72)
    for name, ok, detail in RESULTS:
        print(("[PASS] " if ok else "[FAIL] ") + name + (f"  ({detail})" if detail and not ok else ""))
    print("-" * 72)
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} 项通过")
    print(f"临时目录：{WORK_DIR}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
