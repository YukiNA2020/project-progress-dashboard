"""Health, export, import and backup."""

from __future__ import annotations

import csv
import io
import json
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response

from .. import service
from ..db import connection
from ..settings import database_path

router = APIRouter(prefix="/api")

VERSION = "1.0.0"


@router.get("/health")
def health() -> Dict[str, Any]:
    state = service.bootstrap()
    return {
        "ok": True,
        "version": VERSION,
        "mode": "backend",
        "parser": "local",
        "db": str(database_path()),
        "counts": state["counts"],
    }


@router.get("/export")
def export(format: str = "json") -> Response:
    state = service.bootstrap()
    if format == "csv":
        return Response(content=_csv(state), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition":
                                 'attachment; filename="projects.csv"'})
    payload = json.dumps(
        {"format": "bizboard", "version": 1, "data": state},
        ensure_ascii=False, indent=2)
    return Response(content=payload, media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="bizboard.json"'})


def _csv(state: Dict[str, Any]) -> bytes:
    customers = {item["id"]: item["name"] for item in state["customers"]}
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["项目名称", "客户", "当前阶段", "计划开始", "计划结束", "负责人",
                     "部门", "部门类型", "联系方式", "信息获取手段", "来源渠道",
                     "卡点/进展", "下一步动作", "更新日期", "关键时间点"])
    for project in state["projects"]:
        milestones = "；".join(
            "%s %s" % (item.get("date", ""), item.get("label", ""))
            for item in project.get("milestones") or [])
        writer.writerow([
            project.get("name", ""),
            customers.get(project.get("customer", ""), ""),
            project.get("phase", ""),
            project.get("start", ""),
            project.get("end", ""),
            project.get("contact", ""),
            project.get("dept", ""),
            project.get("deptType", ""),
            project.get("contactWay", ""),
            project.get("means", ""),
            project.get("channel", ""),
            project.get("note", ""),
            project.get("next", ""),
            project.get("updated", ""),
            milestones,
        ])
    # Excel on Chinese Windows reads a BOM-less UTF-8 CSV as GBK garbage.
    return b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8")


@router.post("/import")
async def import_state(request: Request, mode: str = "merge") -> Dict[str, Any]:
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="导入内容不是合法 JSON")

    incoming = body.get("data") if isinstance(body, dict) and "data" in body else body
    if not isinstance(incoming, dict):
        raise HTTPException(status_code=400, detail="导入内容格式不对")
    if not any(key in incoming for key in ("projects", "customers", "phases")):
        raise HTTPException(status_code=400,
                            detail="导入文件里没有 projects / customers / phases")

    if mode == "replace":
        merged = {
            "customers": incoming.get("customers") or [],
            "phases": incoming.get("phases") or [],
            "projects": incoming.get("projects") or [],
        }
        result = service.replace_state(merged)
        return {"mode": "replace", "counts": result["counts"]}

    current = service.bootstrap()
    merged = _merge(current, incoming)
    result = service.replace_state(merged)
    return {"mode": "merge", "counts": result["counts"]}


def _merge(current: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    def by_id(base: List[Dict], extra: List[Dict]) -> List[Dict]:
        seen = {item.get("id"): index for index, item in enumerate(base)}
        out = list(base)
        for item in extra or []:
            key = item.get("id")
            if key and key in seen:
                out[seen[key]] = item
            else:
                out.append(item)
        return out

    return {
        "customers": by_id(current.get("customers") or [], incoming.get("customers") or []),
        "phases": by_id(current.get("phases") or [], incoming.get("phases") or []),
        "projects": by_id(current.get("projects") or [], incoming.get("projects") or []),
    }


@router.get("/backup")
def backup() -> FileResponse:
    path = database_path()
    if not path.is_file():
        raise HTTPException(status_code=404, detail="数据库还没建立")
    with connection() as db:
        db.execute("PRAGMA wal_checkpoint(FULL)")
    return FileResponse(str(path), media_type="application/octet-stream",
                        filename="dashboard.sqlite3")
