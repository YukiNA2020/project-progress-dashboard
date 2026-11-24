"""Environment self-check.

Run this first when something does not start. It answers one question: can this
machine run the backend, or should I just double-click index.html?
"""

from __future__ import annotations

import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINE = "-" * 62


def check_python() -> bool:
    version = "%d.%d.%d" % sys.version_info[:3]
    ok = sys.version_info >= (3, 8)
    print("  Python        %s  %s" % (version, "OK" if ok else "版本太低，需要 3.8+"))
    return ok


def check_packages() -> bool:
    missing = []
    for name in ("fastapi", "uvicorn", "pydantic"):
        try:
            __import__(name)
            print("  %-13s 已安装" % name)
        except Exception:  # noqa: BLE001
            print("  %-13s 缺失" % name)
            missing.append(name)
    if missing:
        print("")
        print("  安装命令：")
        print("    %s -m pip install %s" % (sys.executable, " ".join(missing)))
    return not missing


def check_data_dir() -> bool:
    from app.settings import data_directory

    target = data_directory()
    probe = target / ".write_test"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        print("  数据目录      %s 可写" % target)
        return True
    except OSError as error:
        print("  数据目录      %s 不可写（%s）" % (target, error))
        return False


def check_files() -> bool:
    ok = True
    for relative in ("index.html", "assets/store.js", "assets/local-parse.js", "run.py"):
        exists = (ROOT / relative).is_file()
        print("  %-18s %s" % (relative, "在" if exists else "缺失"))
        ok = ok and exists
    return ok


def main() -> int:
    sys.path.insert(0, str(ROOT))
    print("")
    print(LINE)
    print("  业务项目看板 · 环境自检")
    print(LINE)
    print("  系统          %s %s" % (platform.system(), platform.release()))
    print("  解释器        %s" % sys.executable)
    print("")

    python_ok = check_python()
    files_ok = check_files()
    print("")
    packages_ok = check_packages()
    print("")
    data_ok = False
    try:
        data_ok = check_data_dir()
    except Exception as error:  # noqa: BLE001
        print("  数据目录      检查失败：%s" % error)

    print("")
    print(LINE)
    if python_ok and packages_ok and files_ok and data_ok:
        print("  结论：可以走后端模式（数据落盘）")
        print("  下一步：双击 scripts\\start.bat（Windows）")
        print("         或   scripts/start.command（macOS）")
    else:
        print("  结论：后端跑不起来，但离线模式照样能用")
        print("  下一步：直接双击 index.html")
        print("        功能齐全，只是数据存在浏览器里，记得用「导出」备份")
    print(LINE)
    print("")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
