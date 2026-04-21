# -*- coding: utf-8 -*-
"""backend/routers/admin/audit.py

管理后台：审计日志查询
GET /admin/audit         → 审计日志列表
GET /admin/audit/{id}    → 单条审计详情
"""
from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy

from backend.database import get_async_db
from backend.core.exceptions import AppError
from backend.middleware.auth import admin_user, CurrentUser

router = APIRouter(tags=["admin-audit"])


@router.get("/audit")
async def admin_list_audit(
    operator:    Optional[str] = None,
    action:      Optional[str] = None,
    target_type: Optional[str] = None,
    limit:       int = 100,
    offset:      int = 0,
    user:        CurrentUser = Depends(admin_user),
    db:          AsyncSession = Depends(get_async_db),
):
    filters = "WHERE 1=1"
    params  = {"limit": limit, "offset": offset}
    if operator:
        filters += " AND operator = :operator"
        params["operator"] = operator
    if action:
        filters += " AND action = :action"
        params["action"] = action
    if target_type:
        filters += " AND target_type = :target_type"
        params["target_type"] = target_type

    count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}
    count_r = await db.execute(
        sqlalchemy.text(f"SELECT COUNT(*) FROM audit_logs {filters}"), count_params
    )
    total = count_r.scalar() or 0

    result = await db.execute(sqlalchemy.text(
        f"SELECT id, operator, action, target_type, target_id, "
        f"ip_address, created_at "
        f"FROM audit_logs {filters} "
        f"ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
    ), params)
    rows = result.fetchall()
    return {"items": [dict(r._mapping) for r in rows], "total": total}


@router.get("/audit/{log_id}")
async def admin_get_audit(log_id: int, user: CurrentUser = Depends(admin_user), db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(sqlalchemy.text(
        "SELECT * FROM audit_logs WHERE id = :id"
    ), {"id": log_id})
    row = result.fetchone()
    if row is None:
        raise AppError(404, f"log_id={log_id} 不存在")
    return dict(row._mapping)
