# -*- coding: utf-8 -*-
"""backend/routers/admin/memory.py

管理后台：Memory Center（用户记忆治理）API
GET  /admin/memory/records               → 记忆列表
POST /admin/memory/records/{id}/disable  → 停用记忆
POST /admin/memory/records/{id}/expire   → 强制过期
POST /admin/memory/records/{id}/feedback → 写治理反馈
GET  /admin/memory/records/{id}/feedback → 反馈历史
"""
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy

from backend.database import get_async_db
from backend.core.exceptions import AppError
from backend.governance.trace_center.audit import async_write_audit_log
from backend.middleware.auth import admin_user, CurrentUser

router = APIRouter(tags=["admin-memory"])


class FeedbackBody(BaseModel):
    feedback_type: str   # disable / expire / flag_pii / human_review / auto
    reason:        Optional[str] = None


@router.get("/memory/records")
async def admin_list_memory(
    customer_id: Optional[str] = None,
    risk_level:  Optional[str] = None,
    is_active:   Optional[int] = None,
    limit:       int = 100,
    offset:      int = 0,
    user:        CurrentUser = Depends(admin_user),
    db:          AsyncSession = Depends(get_async_db),
):
    filters = "WHERE 1=1"
    params  = {"limit": limit, "offset": offset}
    if customer_id:
        filters += " AND customer_id = :cid"
        params["cid"] = customer_id
    if risk_level:
        filters += " AND risk_level = :rl"
        params["rl"] = risk_level
    if is_active is not None:
        filters += " AND is_active = :ia"
        params["ia"] = is_active

    count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}
    count_r = await db.execute(
        sqlalchemy.text(f"SELECT COUNT(*) FROM memory_records {filters}"), count_params
    )
    total = count_r.scalar() or 0

    result = await db.execute(sqlalchemy.text(
        f"SELECT memory_id, customer_id, memory_kind, source_type, "
        f"content_summary, risk_level, pii_flag, expires_at, is_active, "
        f"created_at, updated_at "
        f"FROM memory_records {filters} "
        f"ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
    ), params)
    rows = result.fetchall()
    return {"items": [dict(r._mapping) for r in rows], "total": total}


@router.post("/memory/records/{memory_id}/disable")
async def admin_disable_memory(
    memory_id: str,
    user:      CurrentUser = Depends(admin_user),
    db:        AsyncSession = Depends(get_async_db),
):
    await _check_memory(db, memory_id)
    await db.execute(sqlalchemy.text(
        "UPDATE memory_records SET is_active=0, updated_at=NOW() WHERE memory_id=:id"
    ), {"id": memory_id})
    await _write_feedback(db, memory_id, "disable", user.username, None)
    await db.commit()
    await async_write_audit_log(db, user.username, "disable_memory", "memory_record", memory_id)
    return {"memory_id": memory_id, "status": "disabled"}


@router.post("/memory/records/{memory_id}/expire")
async def admin_expire_memory(
    memory_id: str,
    user:      CurrentUser = Depends(admin_user),
    db:        AsyncSession = Depends(get_async_db),
):
    await _check_memory(db, memory_id)
    await db.execute(sqlalchemy.text(
        "UPDATE memory_records SET expires_at=NOW(), updated_at=NOW() WHERE memory_id=:id"
    ), {"id": memory_id})
    await _write_feedback(db, memory_id, "expire", user.username, "人工强制过期")
    await db.commit()
    await async_write_audit_log(db, user.username, "expire_memory", "memory_record", memory_id)
    return {"memory_id": memory_id, "status": "expired"}


@router.post("/memory/records/{memory_id}/feedback")
async def admin_memory_feedback(
    memory_id: str,
    body:      FeedbackBody,
    user:      CurrentUser = Depends(admin_user),
    db:        AsyncSession = Depends(get_async_db),
):
    await _check_memory(db, memory_id)
    await _write_feedback(db, memory_id, body.feedback_type, user.username, body.reason)
    await db.commit()
    await async_write_audit_log(db, user.username, "memory_feedback", "memory_record", memory_id,
                                after={"feedback_type": body.feedback_type})
    return {"memory_id": memory_id, "feedback_type": body.feedback_type, "status": "recorded"}


@router.get("/memory/records/{memory_id}/feedback")
async def admin_get_memory_feedback(
    memory_id: str,
    user:      CurrentUser = Depends(admin_user),
    db:        AsyncSession = Depends(get_async_db),
):
    """获取某条记忆的反馈历史"""
    await _check_memory(db, memory_id)
    result = await db.execute(sqlalchemy.text(
        "SELECT id, feedback_type, reason, operated_by, created_at "
        "FROM memory_feedback WHERE memory_id = :mid "
        "ORDER BY created_at DESC"
    ), {"mid": memory_id})
    return [dict(r._mapping) for r in result.fetchall()]


async def _check_memory(db: AsyncSession, memory_id: str):
    result = await db.execute(sqlalchemy.text(
        "SELECT memory_id FROM memory_records WHERE memory_id = :id"
    ), {"id": memory_id})
    if result.fetchone() is None:
        raise AppError(404, f"memory_id={memory_id} 不存在")


async def _write_feedback(
    db: AsyncSession, memory_id: str, feedback_type: str, operated_by: str, reason: Optional[str]
):
    await db.execute(sqlalchemy.text("""
        INSERT INTO memory_feedback (memory_id, feedback_type, reason, operated_by)
        VALUES (:mid, :ft, :reason, :by)
    """), {"mid": memory_id, "ft": feedback_type, "reason": reason, "by": operated_by})


# ── 记忆治理: 新鲜度 + 健康总览 ──

@router.get("/memory/governance/health")
async def memory_governance_health(
    user: CurrentUser = Depends(admin_user),
    db:   AsyncSession = Depends(get_async_db),
):
    """记忆治理健康总览 — 含新鲜度评分分布"""
    from backend.core.memory_freshness import freshness_engine

    # 加载 memory_records
    result = await db.execute(sqlalchemy.text(
        "SELECT memory_id, customer_id, memory_kind AS domain, "
        "content_summary, risk_level, is_active, "
        "COALESCE(importance, 0.5) AS importance, "
        "0 AS access_count, created_at, updated_at "
        "FROM memory_records WHERE is_active = 1 "
        "ORDER BY updated_at DESC LIMIT 500"
    ))
    rows = [dict(r._mapping) for r in result.fetchall()]

    scored = freshness_engine.batch_score(rows)
    summary = freshness_engine.health_summary(scored)

    # 加载 copilot_memory 统计
    copilot_stats = {"total": 0, "active": 0}
    try:
        r2 = await db.execute(sqlalchemy.text(
            "SELECT COUNT(*) AS total, SUM(is_active) AS active FROM copilot_memory"
        ))
        row = r2.fetchone()
        if row:
            copilot_stats = {"total": row.total or 0, "active": row.active or 0}
    except Exception:
        pass

    return {
        "ok": True,
        "data": {
            "memory_records": summary.model_dump(),
            "copilot_memory": copilot_stats,
            "layer_breakdown": {
                "L3_rules": "static config",
                "L2_copilot_memory": copilot_stats,
                "L1_thread_history": "Redis TTL 7d",
            },
            "freshness_config": freshness_engine.config.model_dump(),
        },
    }


@router.get("/memory/governance/freshness")
async def memory_freshness_list(
    limit:  int = 50,
    domain: Optional[str] = None,
    status_filter: Optional[str] = None,
    user: CurrentUser = Depends(admin_user),
    db:   AsyncSession = Depends(get_async_db),
):
    """记忆新鲜度列表 — 带评分"""
    from backend.core.memory_freshness import freshness_engine

    filters = "WHERE is_active = 1"
    params: dict = {"limit": limit}
    if domain:
        filters += " AND memory_kind = :domain"
        params["domain"] = domain

    result = await db.execute(sqlalchemy.text(
        f"SELECT memory_id, customer_id, memory_kind AS domain, "
        f"content_summary, risk_level, "
        f"COALESCE(importance, 0.5) AS importance, "
        f"0 AS access_count, created_at, updated_at "
        f"FROM memory_records {filters} "
        f"ORDER BY updated_at DESC LIMIT :limit"
    ), params)
    rows = [dict(r._mapping) for r in result.fetchall()]

    scored = freshness_engine.batch_score(rows)

    # 可选: 按 freshness status 过滤
    if status_filter:
        scored = [m for m in scored if m.get("freshness", {}).get("status") == status_filter]

    return {
        "ok": True,
        "data": scored,
        "total": len(scored),
    }
