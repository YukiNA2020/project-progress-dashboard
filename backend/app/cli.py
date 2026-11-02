"""Command line entry point, also used by the login-startup registration.

``python backend/run.py serve --open-browser`` is what the Windows Run key and
the macOS LaunchAgent point at. It starts the loopback service, performs the
once-a-day automatic scan, and opens the dashboard in the default browser.

If a dashboard is already listening on the port, the second launch only opens
the browser: this is what keeps two login-startup entries from creating two
services on the same machine.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
import time
import webbrowser
from typing import List, Optional
from urllib.request import urlopen

DEFAULT_PORT = 8000
DEFAULT_HOST = "127.0.0.1"
AUTO_SCAN_ENV = "PROJECT_PROGRESS_DASHBOARD_AUTO_SCAN"
SERVICE_NAME = "project-progress-dashboard-api"


def base_url(port: int = DEFAULT_PORT) -> str:
    return f"http://{DEFAULT_HOST}:{port}"


def probe_running(port: int = DEFAULT_PORT, timeout: float = 0.6) -> bool:
    """True when this dashboard (not just any server) answers on the port."""
    try:
        with urlopen(f"{base_url(port)}/api/health", timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 - a closed port is the normal case
        return False
    return isinstance(payload, dict) and payload.get("service") == SERVICE_NAME


def _configure_logging() -> str:
    from .settings import log_path

    path = log_path()
    logging.basicConfig(
        filename=str(path),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    return str(path)


def _open_when_ready(port: int, timeout: float = 25.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if probe_running(port, timeout=0.8):
            webbrowser.open(base_url(port))
            return True
        time.sleep(0.4)
    return False


def _emit(message: str) -> None:
    """Write to the console when there is one.

    The login-startup entry may use ``pythonw.exe`` on Windows, where
    ``sys.stdout`` is ``None``. Logging always happens, so nothing is lost.
    """
    logging.getLogger("dashboard.cli").info(message)
    if sys.stdout is None:
        return
    try:
        print(message, flush=True)
    except Exception:  # noqa: BLE001 - a missing console must not break startup
        return


def serve(args: argparse.Namespace) -> int:
    from .db import initialize_database

    log_file = _configure_logging()

    if probe_running(args.port):
        _emit(f"看板已在运行：{base_url(args.port)}")
        if args.open_browser:
            webbrowser.open(base_url(args.port))
        return 0

    initialize_database()

    os.environ[AUTO_SCAN_ENV] = "0" if args.no_daily_scan else "1"
    if args.open_browser:
        threading.Thread(target=_open_when_ready, args=(args.port,), daemon=True).start()

    import uvicorn

    from .main import app

    _emit(f"看板服务：{base_url(args.port)}（日志：{log_file}）")
    try:
        uvicorn.run(app, host=DEFAULT_HOST, port=args.port, log_config=None)
    except Exception:  # noqa: BLE001 - a startup failure must reach the log
        logging.getLogger("dashboard.cli").exception("看板服务启动失败")
        raise
    return 0


def scan_command(args: argparse.Namespace) -> int:
    from . import service
    from .db import initialize_database

    initialize_database()
    run = service.scan_all(use_model=False if args.rules_only else None, trigger="cli")
    summary = {
        key: run.get(key)
        for key in (
            "result",
            "message",
            "projects_total",
            "projects_ok",
            "projects_needing_confirmation",
            "projects_failed",
            "schedule_proposals",
            "model_enabled",
        )
    }
    _emit(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if run.get("result") != "failed" else 1


def startup_command(args: argparse.Namespace) -> int:
    from .system import StartupError, disable_startup, enable_startup, startup_status

    try:
        if args.action == "enable":
            status = enable_startup()
        elif args.action == "disable":
            status = disable_startup()
        else:
            status = startup_status()
    except StartupError as error:
        _emit(json.dumps({"ok": False, "message": str(error)}, ensure_ascii=False))
        return 1
    _emit(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dashboard",
        description="项目进度看板本地服务",
    )
    subparsers = parser.add_subparsers(dest="command")

    serve_parser = subparsers.add_parser("serve", help="启动本地服务")
    serve_parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve_parser.add_argument("--open-browser", action="store_true", help="服务就绪后打开浏览器")
    serve_parser.add_argument(
        "--no-daily-scan",
        action="store_true",
        help="本次启动不执行每日自动巡检",
    )
    serve_parser.set_defaults(handler=serve)

    scan_parser = subparsers.add_parser("scan", help="立即巡检一次并打印摘要")
    scan_parser.add_argument("--rules-only", action="store_true", help="只跑本地规则，不调用模型")
    scan_parser.set_defaults(handler=scan_command)

    startup_parser = subparsers.add_parser("startup", help="查看或修改登录时自动启动")
    startup_parser.add_argument("action", choices=["status", "enable", "disable"])
    startup_parser.set_defaults(handler=startup_command)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "handler", None):
        parser.print_help()
        return 2
    return args.handler(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
