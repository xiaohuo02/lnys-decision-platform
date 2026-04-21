# -*- coding: utf-8 -*-
"""backend/routers/admin/traces.py

管理后台：Trace 查询与回放 API
GET  /admin/traces                → run 列表（支持多维筛选 + 关键词搜索）
GET  /admin/traces/export         → CSV / JSON 导出
GET  /admin/traces/stats          → 聚合统计（按 workflow / status / 日期）
GET  /admin/traces/{run_id}       → run 详情 + step 树
POST /admin/traces/{run_id}/replay → 重触发（stub）
"""
import csv
import io
import json
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy

from backend.database import get_async_db
from backend.core.exceptions import AppError
from backend.middleware.auth import admin_user, CurrentUser

router = APIRouter(tags=["admin-traces"])

# ── 共用筛选条件构造 ──────────────────────────────────────────────

def _build_filters(
    workflow_name: Optional[str],
    status: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
    triggered_by: Optional[str],
    hide_system: bool,
    keyword: Optional[str],
):
    filters = "WHERE 1=1"
    params = {}
    if workflow_name:
        filters += " AND r.workflow_name = :wf"
        params["wf"] = workflow_name
    if status:
        filters += " AND r.status = :status"
        params["status"] = status
    if start_date:
        filters += " AND r.started_at >= :start_date"
        params["start_date"] = start_date
    if end_date:
        filters += " AND r.started_at < DATE_ADD(:end_date, INTERVAL 1 DAY)"
        params["end_date"] = end_date
    if triggered_by:
        if triggered_by == "__system__":
            filters += " AND (r.triggered_by IS NULL OR r.triggered_by = '' OR r.triggered_by = 'scheduler')"
        else:
            filters += " AND r.triggered_by = :triggered_by"
            params["triggered_by"] = triggered_by
    if hide_system:
        filters += " AND r.triggered_by IS NOT NULL AND r.triggered_by NOT IN ('', 'scheduler')"
    if keyword:
        filters += (
            " AND (r.input_summary LIKE :kw OR r.output_summary LIKE :kw "
            "OR r.error_message LIKE :kw OR r.run_id LIKE :kw "
            "OR r.workflow_name LIKE :kw)"
        )
        params["kw"] = f"%{keyword}%"
    return filters, params


_SELECT_COLS = (
    "r.run_id, r.thread_id, r.request_id, r.entrypoint, "
    "r.workflow_name, r.workflow_version, r.status, "
    "r.input_summary, r.output_summary, "
    "r.started_at, r.ended_at, r.latency_ms, "
    "COALESCE(NULLIF(r.total_tokens, 0), "
    "  (SELECT COALESCE(SUM(JSON_EXTRACT(s.token_usage_json, '$.total_tokens')), 0) "
    "   FROM run_steps s WHERE s.run_id = r.run_id)) AS total_tokens, "
    "COALESCE(NULLIF(r.total_cost, 0), "
    "  (SELECT COALESCE(SUM(s.cost_amount), 0) "
    "   FROM run_steps s WHERE s.run_id = r.run_id)) AS total_cost, "
    "r.error_message, r.triggered_by"
)

# ── GET /admin/traces — 列表 ──────────────────────────────────────

@router.get("/traces")
async def admin_list_traces(
    workflow_name: Optional[str] = None,
    status:        Optional[str] = None,
    start_date:    Optional[str] = None,
    end_date:      Optional[str] = None,
    triggered_by:  Optional[str] = None,
    hide_system:   bool = False,
    keyword:       Optional[str] = None,
    sort_by:       str = "started_at",
    sort_dir:      str = "desc",
    limit:         int = 50,
    offset:        int = 0,
    user:          CurrentUser = Depends(admin_user),
    db:            AsyncSession = Depends(get_async_db),
):
    base_from = "FROM runs r"
    filters, params = _build_filters(
        workflow_name, status, start_date, end_date,
        triggered_by, hide_system, keyword,
    )
    params["limit"] = limit
    params["offset"] = offset

    # 安全排序字段白名单
    allowed_sort = {"started_at", "latency_ms", "total_tokens", "total_cost", "status", "workflow_name"}
    col = sort_by if sort_by in allowed_sort else "started_at"
    direction = "ASC" if sort_dir.lower() == "asc" else "DESC"

    count_result = await db.execute(
        sqlalchemy.text(f"SELECT COUNT(*) {base_from} {filters}"),
        {k: v for k, v in params.items() if k not in ("limit", "offset")},
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        sqlalchemy.text(
            f"SELECT {_SELECT_COLS} {base_from} {filters} "
            f"ORDER BY r.{col} {direction} LIMIT :limit OFFSET :offset"
        ),
        params,
    )
    rows = result.fetchall()

    # 筛选器下拉选项（返回 username + display_name）
    user_result = await db.execute(sqlalchemy.text(
        "SELECT DISTINCT r2.triggered_by, COALESCE(u.display_name, r2.triggered_by) AS display_name "
        "FROM runs r2 LEFT JOIN users u ON r2.triggered_by = u.username COLLATE utf8mb4_unicode_ci "
        "WHERE r2.triggered_by IS NOT NULL AND r2.triggered_by != '' "
        "ORDER BY r2.triggered_by"
    ))
    user_list = [
        {"username": r[0], "display_name": r[1]}
        for r in user_result.fetchall()
    ]

    wf_result = await db.execute(sqlalchemy.text(
        "SELECT DISTINCT workflow_name FROM runs ORDER BY workflow_name"
    ))
    wf_list = [r[0] for r in wf_result.fetchall()]

    return {
        "items": [dict(r._mapping) for r in rows],
        "total": total,
        "offset": offset,
        "limit": limit,
        "users": user_list,
        "workflows": wf_list,
    }


# ── GET /admin/traces/stats — 聚合统计 ───────────────────────────

@router.get("/traces/stats")
async def admin_traces_stats(
    start_date: Optional[str] = None,
    end_date:   Optional[str] = None,
    user:       CurrentUser = Depends(admin_user),
    db:         AsyncSession = Depends(get_async_db),
):
    date_filter = "WHERE 1=1"
    params = {}
    if start_date:
        date_filter += " AND started_at >= :sd"
        params["sd"] = start_date
    if end_date:
        date_filter += " AND started_at < DATE_ADD(:ed, INTERVAL 1 DAY)"
        params["ed"] = end_date

    # 总览
    overview = await db.execute(sqlalchemy.text(f"""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as completed,
               SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed,
               SUM(CASE WHEN status='running' OR status='pending' THEN 1 ELSE 0 END) as active,
               AVG(latency_ms) as avg_latency,
               SUM(total_tokens) as total_tokens,
               SUM(total_cost) as total_cost
        FROM runs {date_filter}
    """), params)
    ov = dict(overview.fetchone()._mapping)

    # 按 workflow 分组
    by_wf = await db.execute(sqlalchemy.text(f"""
        SELECT workflow_name, COUNT(*) as cnt,
               SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as ok,
               SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as fail,
               AVG(latency_ms) as avg_lat
        FROM runs {date_filter}
        GROUP BY workflow_name ORDER BY cnt DESC
    """), params)
    wf_rows = [dict(r._mapping) for r in by_wf.fetchall()]

    # 按日期分组（最近 30 天）
    by_day = await db.execute(sqlalchemy.text(f"""
        SELECT DATE(started_at) as day, COUNT(*) as cnt,
               SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as fail
        FROM runs {date_filter}
        GROUP BY DATE(started_at) ORDER BY day DESC LIMIT 30
    """), params)
    day_rows = [dict(r._mapping) for r in by_day.fetchall()]

    return {"overview": ov, "by_workflow": wf_rows, "by_day": day_rows}


# ── GET /admin/traces/export — 导出 CSV / JSON ──────────────────

@router.get("/traces/export")
async def admin_export_traces(
    fmt:           str = "csv",
    workflow_name: Optional[str] = None,
    status:        Optional[str] = None,
    start_date:    Optional[str] = None,
    end_date:      Optional[str] = None,
    triggered_by:  Optional[str] = None,
    hide_system:   bool = False,
    keyword:       Optional[str] = None,
    max_rows:      int = 5000,
    user:          CurrentUser = Depends(admin_user),
    db:            AsyncSession = Depends(get_async_db),
):
    base_from = "FROM runs r"
    filters, params = _build_filters(
        workflow_name, status, start_date, end_date,
        triggered_by, hide_system, keyword,
    )
    params["limit"] = min(max_rows, 10000)

    result = await db.execute(
        sqlalchemy.text(
            f"SELECT {_SELECT_COLS} {base_from} {filters} "
            f"ORDER BY r.started_at DESC LIMIT :limit"
        ),
        params,
    )
    rows = [dict(r._mapping) for r in result.fetchall()]

    # 序列化 datetime（naive datetime 视为 UTC）
    def _ser(obj):
        if isinstance(obj, datetime):
            from datetime import timezone as _tz
            if obj.tzinfo is None:
                obj = obj.replace(tzinfo=_tz.utc)
            return obj.isoformat()
        return str(obj) if obj is not None else ""

    if fmt == "json":
        content = json.dumps(rows, ensure_ascii=False, default=_ser, indent=2)
        return StreamingResponse(
            iter([content]),
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=traces_export.json"},
        )

    # CSV
    buf = io.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _ser(v) for k, v in row.items()})
    content = buf.getvalue()
    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=traces_export.csv"},
    )


# ── GET /admin/traces/{run_id} — 详情 ────────────────────────────

@router.get("/traces/{run_id}")
async def admin_get_trace(
    run_id: str,
    user:   CurrentUser = Depends(admin_user),
    db:     AsyncSession = Depends(get_async_db),
):
    result = await db.execute(
        sqlalchemy.text("SELECT * FROM runs WHERE run_id = :id"),
        {"id": run_id},
    )
    run_row = result.fetchone()
    if run_row is None:
        raise AppError(404, f"run_id={run_id} 不存在")

    result2 = await db.execute(
        sqlalchemy.text(
            "SELECT step_id, parent_step_id, step_type, step_name, "
            "agent_name, tool_name, model_name, "
            "status, input_summary, output_summary, "
            "token_usage_json, cost_amount, retry_count, "
            "guardrail_hits_json, error_message, started_at, ended_at "
            "FROM run_steps WHERE run_id = :id ORDER BY started_at"
        ),
        {"id": run_id},
    )
    raw_steps = result2.fetchall()

    def _parse_step(s):
        d = dict(s._mapping)
        # 解析 token_usage_json 字符串为对象
        tu = d.get("token_usage_json")
        if isinstance(tu, str):
            try:
                d["token_usage"] = json.loads(tu)
            except Exception:
                d["token_usage"] = {}
        elif isinstance(tu, dict):
            d["token_usage"] = tu
        else:
            d["token_usage"] = {}
        # 计算 step 耗时
        sa, ea = d.get("started_at"), d.get("ended_at")
        if sa and ea:
            try:
                delta = (ea - sa).total_seconds() * 1000
                d["latency_ms"] = int(delta)
            except Exception:
                d["latency_ms"] = None
        else:
            d["latency_ms"] = None
        return d

    # run 级 token/cost 兜底
    run_data = dict(run_row._mapping)
    if not run_data.get("total_tokens"):
        run_data["total_tokens"] = sum(
            (json.loads(s._mapping.get("token_usage_json") or "{}").get("total_tokens", 0)
             if isinstance(s._mapping.get("token_usage_json"), str) else 0)
            for s in raw_steps
        )
    if not run_data.get("total_cost"):
        run_data["total_cost"] = float(sum(
            (s._mapping.get("cost_amount") or 0) for s in raw_steps
        ))

    return {
        "run": run_data,
        "steps": [_parse_step(s) for s in raw_steps],
    }


# ── POST /admin/traces/{run_id}/replay — 重触发 ──────────────────

@router.post("/traces/{run_id}/replay")
async def admin_replay_trace(
    run_id: str,
    user:   CurrentUser = Depends(admin_user),
    db:     AsyncSession = Depends(get_async_db),
):
    """Trace 回放入口（当前为 stub，后续接 workflow 重触发逻辑）"""
    result = await db.execute(
        sqlalchemy.text("SELECT run_id, workflow_name, status FROM runs WHERE run_id = :id"),
        {"id": run_id},
    )
    run_row = result.fetchone()
    if run_row is None:
        raise AppError(404, f"run_id={run_id} 不存在")
    return {
        "run_id":        run_id,
        "workflow_name": run_row[1],
        "replay_status": "stub_not_yet_implemented",
        "message":       "Replay 功能待 workflow 接入后启用",
    }
