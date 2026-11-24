"""Launcher.

Adds its own folder to sys.path so it works no matter what the working
directory is (double-clicked .bat, a shortcut, or a terminal in another folder).
"""

from __future__ import annotations

import argparse
import socket
import sys
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

DEFAULT_PORT = 8787
PORT_TRIES = 14


def free_port(start: int = DEFAULT_PORT) -> int:
    for offset in range(PORT_TRIES):
        port = start + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    return start


def main() -> int:
    parser = argparse.ArgumentParser(description="业务项目看板 · 本地服务")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        print("缺少依赖：uvicorn。先执行 pip install -r requirements.txt")
        return 1

    from app.main import app

    port = args.port or free_port()
    url = "http://127.0.0.1:%d" % port

    print("")
    print("  业务项目看板")
    print("  地址：%s" % url)
    print("  关掉这个窗口即停止服务（数据已存盘，不会丢）")
    print("")

    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001 - a missing browser must not stop the server
            pass

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
