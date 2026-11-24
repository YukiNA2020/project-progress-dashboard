"""End-to-end check against a real server.

Starts the app on a throwaway data directory and a free port, exercises the
same endpoints the browser uses, then shuts it down. No test framework: the
point is that it runs anywhere the app runs.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
results = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((name, bool(condition)))
    mark = "PASS" if condition else "FAIL"
    line = "  [%s] %s" % (mark, name)
    if detail and not condition:
        line += "  -> %s" % detail
    print(line)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def call(port: int, path: str, method: str = "GET", payload=None, raw: bool = False):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path),
                                     data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=15) as response:
        body = response.read()
        return response.status, (body if raw else json.loads(body))


STATE = {
    "customers": [
        {"id": "c1", "name": "德国 Kalom", "alias": "Kalom,卡隆"},
        {"id": "c2", "name": "法国杜邦", "alias": "Dupont"},
        {"id": "c3", "name": "意大利 Rex", "alias": ""},
    ],
    "phases": [
        {"id": "ph1", "name": "未开始", "color": "#98a1ad"},
        {"id": "ph2", "name": "开发中", "color": "#465ed8"},
        {"id": "ph3", "name": "生产中", "color": "#e8a13a"},
        {"id": "ph4", "name": "已交付", "color": "#2b8a3e"},
    ],
    "projects": [
        {"id": "p1", "name": "洗碗机项目", "customer": "c1", "phase": "开发中",
         "start": "2026-11-10", "end": "2026-12-05", "color": "#465ed8",
         "contact": "老李", "dept": "研发部", "deptType": "内部", "contactWay": "",
         "means": "找开发要包装书", "channel": "群聊", "note": "模具要改",
         "next": "催老李确认图纸", "updated": "2026-11-24",
         "unsure": ["end"], "done": ["未开始"],
         "milestones": [
             {"id": "m2", "date": "2026-12-05", "label": "出货 DDL"},
             {"id": "m1", "date": "2026-11-20", "label": "报价 DDL"},
         ]},
        {"id": "p2", "name": "X200 项目", "customer": "c2", "phase": "未开始",
         "start": "", "end": "", "color": "#1d9e75", "contact": "", "dept": "",
         "deptType": "", "contactWay": "", "means": "", "channel": "", "note": "",
         "next": "", "updated": "2026-11-24", "unsure": [], "done": [],
         "milestones": []},
    ],
}


def main() -> int:
    port = free_port()
    data_dir = tempfile.mkdtemp(prefix="bizboard-smoke-")
    env = dict(os.environ)
    env["BIZBOARD_DATA_DIR"] = data_dir

    print("")
    print("  业务项目看板 · 冒烟测试")
    print("  端口 %d  数据目录 %s" % (port, data_dir))
    print("")

    process = subprocess.Popen(
        [sys.executable, "run.py", "--port", str(port), "--no-browser"],
        cwd=str(ROOT), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    try:
        healthy = False
        for _ in range(60):
            if process.poll() is not None:
                break
            try:
                status, body = call(port, "/api/health")
                healthy = status == 200 and body.get("ok")
                if healthy:
                    break
            except Exception:  # noqa: BLE001 - server may still be binding
                time.sleep(0.25)
        check("1. 服务能启动并通过 /api/health", healthy)
        if not healthy:
            error = process.stderr.read().decode("utf-8", "replace")[-800:] if process.stderr else ""
            print(error)
            return 1

        _status, empty = call(port, "/api/bootstrap")
        check("2. 空库读到空项目列表",
              not empty["projects"] and not empty["customers"],
              str(empty.get("counts")))

        call(port, "/api/state", "POST", STATE)
        _status, loaded = call(port, "/api/bootstrap")
        check("3. 全量写入后能读回 2 个项目 3 个客户",
              len(loaded["projects"]) == 2 and len(loaded["customers"]) == 3,
              str(loaded.get("counts")))

        project = next(p for p in loaded["projects"] if p["id"] == "p1")
        check("4. 项目字段完整往返（阶段名 / 卡点 / 下一步）",
              project["phase"] == "开发中" and project["note"] == "模具要改"
              and project["next"] == "催老李确认图纸",
              json.dumps(project, ensure_ascii=False)[:160])

        dates = [item["date"] for item in project["milestones"]]
        check("5. 关键时间点按日期升序", dates == sorted(dates), str(dates))

        check("6. 待确认字段被记住", project["unsure"] == ["end"], str(project["unsure"]))
        check("7. 已完成阶段被记住", project["done"] == ["未开始"], str(project["done"]))

        call(port, "/api/projects/p1", "PATCH", {"note": "模具已改，等确认"})
        _status, patched = call(port, "/api/bootstrap")
        target = next(p for p in patched["projects"] if p["id"] == "p1")
        check("8. 局部更新只改指定字段",
              target["note"] == "模具已改，等确认" and target["next"] == "催老李确认图纸",
              target["note"])

        call(port, "/api/customers/c1", "DELETE")
        _status, after_delete = call(port, "/api/bootstrap")
        orphan = next(p for p in after_delete["projects"] if p["id"] == "p1")
        check("9. 删客户后项目保留但解除关联",
              orphan["customer"] == "" and len(after_delete["projects"]) == 2,
              repr(orphan["customer"]))

        # Put the customer back: the parse test below needs it, and this also
        # covers the create endpoint the browser uses for a brand new customer.
        call(port, "/api/customers", "POST",
             {"name": "德国 Kalom", "alias": "Kalom,卡隆"})

        call(port, "/api/phases", "PUT", {"phases": [
            {"name": "未开始", "color": "#98a1ad"},
            {"name": "开发中", "color": "#465ed8"},
            {"name": "已交付", "color": "#2b8a3e"},
        ]})
        _status, after_phase = call(port, "/api/bootstrap")
        survivor = next(p for p in after_phase["projects"] if p["id"] == "p1")
        check("10. 删阶段后悬空的已完成阶段被清理",
              survivor["phase"] == "开发中" and "生产中" not in survivor["done"],
              str(survivor["done"]))

        _status, parsed = call(port, "/api/parse", "POST", {
            "text": "德国 Kalom 的洗碗机项目开发中，模具要改，计划 11/10 到 12/5，"
                    "12/5 是出货 DDL。我找开发老李要了包装书，下一步催他确认图纸。"})
        fields = parsed["fields"]
        check("11. 解析：客户与阶段识别正确",
              bool(fields["customer"]["value"]) and fields["phase"]["value"] == "开发中",
              "%s / %s" % (fields["customer"].get("value"), fields["phase"].get("value")))
        check("12. 解析：日期区间与年份推断",
              fields["start"]["value"] == "2026-11-10"
              and fields["end"]["value"] == "2026-12-05",
              "%s -> %s" % (fields["start"]["value"], fields["end"]["value"]))
        check("13. 解析：DDL 变成关键时间点",
              any(item["date"] == "2026-12-05" for item in parsed["milestones"]),
              str(parsed["milestones"]))
        check("14. 解析：卡点与下一步分离",
              fields["note"]["value"] == "模具要改"
              and fields["next"]["value"] == "催他确认图纸",
              "%s | %s" % (fields["note"]["value"], fields["next"]["value"]))

        _status, exported = call(port, "/api/export?format=json", raw=True)
        payload = json.loads(exported.decode("utf-8"))
        before = len(payload["data"]["projects"])
        call(port, "/api/import?mode=merge", "POST", payload)
        _status, merged = call(port, "/api/bootstrap")
        check("15. 导出再导入是幂等的",
              len(merged["projects"]) == before == 2,
              "%d -> %d" % (before, len(merged["projects"])))

        _status, csv_bytes = call(port, "/api/export?format=csv", raw=True)
        check("16. CSV 带 UTF-8 BOM（Excel 不乱码）",
              csv_bytes[:3] == b"\xef\xbb\xbf", repr(csv_bytes[:6]))

        _status, backup = call(port, "/api/backup", raw=True)
        check("17. 备份下载的是真的 SQLite 文件",
              backup[:15] == b"SQLite format 3", repr(backup[:16]))

        _status, settings = call(port, "/api/provider")
        check("18. 模型配置默认关闭且不含密钥",
              settings["enabled"] is False and settings["api_key_set"] is False
              and "api_key" not in settings,
              json.dumps(settings, ensure_ascii=False)[:120])

        guarded, _ignored = _cross_origin(port)
        check("19. 跨站写入被拒绝（防恶意网页打本地端口）", guarded == 403, str(guarded))

    finally:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()

    passed = sum(1 for _name, ok in results if ok)
    print("")
    print("  %d / %d 通过" % (passed, len(results)))
    print("")
    return 0 if passed == len(results) else 1


def _cross_origin(port: int) -> tuple:
    request = urllib.request.Request(
        "http://127.0.0.1:%d/api/state" % port,
        data=b'{"projects":[]}', method="POST",
        headers={"Content-Type": "application/json",
                 "Origin": "http://evil.example.com"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, None
    except urllib.error.HTTPError as error:
        return error.code, None


if __name__ == "__main__":
    raise SystemExit(main())
