# -*- coding: utf-8 -*-
"""backend/routers/admin/copilot_config.py — Copilot 配置管理 API

管理控制台用：
  GET  /admin/copilot/config/skills         → 技能列表 + 权限矩阵
  GET  /admin/copilot/config/overrides      → 用户级权限覆盖列表
  PUT  /admin/copilot/config/overrides      → 设置权限覆盖
  DELETE /admin/copilot/config/overrides     → 删除权限覆盖
  GET  /admin/copilot/config/feedback-stats  → 反馈统计看板
  GET  /admin/copilot/config/search          → 对话搜索
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from backend.database import get_async_db
from backend.core.response import ok
from backend.middleware.auth import admin_user, CurrentUser
from backend.governance.trace_center.audit import async_write_audit_log
from backend.copilot.permissions import ROLE_SKILL_MATRIX, OPS_ONLY_SKILLS
from backend.copilot.registry import SkillRegistry
from backend.models.copilot import CopilotSkillOverride

router = APIRouter(tags=["copilot-config"])


# ── Schemas ──

class SkillOverrideBody(BaseModel):
    user_id: str
    skill_name: str
    enabled: bool
    reason: Optional[str] = None


class SkillOverrideDeleteBody(BaseModel):
    user_id: str
    skill_name: str


# ── 技能列表 + 权限矩阵 ──

@router.get("/copilot/config/skills")
async def list_skills(user: CurrentUser = Depends(admin_user)):
    """返回所有已注册 Skill 及权限矩阵"""
    registry = SkillRegistry.instance()
    skills = []
    for s in registry._skills.values():
        skills.append({
            "name": s.name,
            "display_name": s.display_name,
            "description": s.description,
            "mode": list(s.mode),
            "required_roles": list(s.required_roles),
            "ops_only": s.name in OPS_ONLY_SKILLS,
        })

    return ok({
        "skills": skills,
        "role_matrix": {k: list(v) for k, v in ROLE_SKILL_MATRIX.items()},
        "ops_only_skills": list(OPS_ONLY_SKILLS),
    })


# ── 用户级权限覆盖 CRUD ──

@router.get("/copilot/config/overrides")
async def list_overrides(
    user_id: Optional[str] = None,
    user: CurrentUser = Depends(admin_user),
    db: AsyncSession = Depends(get_async_db),
):
    """获取权限覆盖列表"""
    try:
        stmt = select(CopilotSkillOverride).where(CopilotSkillOverride.is_active == True)
        if user_id:
            stmt = stmt.where(CopilotSkillOverride.user_id == user_id)
        stmt = stmt.order_by(CopilotSkillOverride.user_id, CopilotSkillOverride.skill_name)
        result = await db.execute(stmt)
        items = [
            {
                "id": r.id, "user_id": r.user_id, "skill_name": r.skill_name,
                "enabled": bool(r.enabled), "granted_by": r.granted_by, "reason": r.reason,
                "created_at": str(r.created_at), "updated_at": str(r.updated_at),
            }
            for r in result.scalars().all()
        ]
        return ok({"overrides": items, "total": len(items)})
    except Exception as e:
        logger.warning(f"[copilot_config] list_overrides error: {e}")
        return ok({"overrides": [], "total": 0})


@router.put("/copilot/config/overrides")
async def set_override(
    body: SkillOverrideBody,
    user: CurrentUser = Depends(admin_user),
    db: AsyncSession = Depends(get_async_db),
):
    """设置用户级 Skill 权限覆盖（upsert）"""
    await db.execute(
        text("""
            INSERT INTO copilot_skill_overrides (user_id, skill_name, enabled, granted_by, reason, is_active)
            VALUES (:uid, :skill, :enabled, :granted_by, :reason, 1)
            ON DUPLICATE KEY UPDATE enabled = :enabled, granted_by = :granted_by,
                                     reason = :reason, is_active = 1,
                                     updated_at = CURRENT_TIMESTAMP
        """),
        {
            "uid": body.user_id,
            "skill": body.skill_name,
            "enabled": body.enabled,
            "granted_by": user.username,
            "reason": body.reason,
        },
    )
    await db.commit()
    await async_write_audit_log(
        db, operator=user.username, action="set_skill_override",
        target_type="copilot_skill_override", target_id=f"{body.user_id}/{body.skill_name}",
        after={"enabled": body.enabled, "reason": body.reason},
    )
    return ok({"status": "ok"})


@router.delete("/copilot/config/overrides")
async def delete_override(
    body: SkillOverrideDeleteBody,
    user: CurrentUser = Depends(admin_user),
    db: AsyncSession = Depends(get_async_db),
):
    """删除权限覆盖（软删除）"""
    await db.execute(
        update(CopilotSkillOverride)
        .where(
            CopilotSkillOverride.user_id == body.user_id,
            CopilotSkillOverride.skill_name == body.skill_name,
        )
        .values(is_active=False)
    )
    await db.commit()
    await async_write_audit_log(
        db, operator=user.username, action="delete_skill_override",
        target_type="copilot_skill_override", target_id=f"{body.user_id}/{body.skill_name}",
    )
    return ok({"status": "deleted"})


# ── 反馈统计看板 ──

@router.get("/copilot/config/feedback-stats")
async def feedback_stats(
    days: int = Query(30, ge=1, le=365),
    user: CurrentUser = Depends(admin_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Copilot 反馈质量统计"""
    try:
        stats = {}

        # 总体统计
        result = await db.execute(text("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN feedback = 1 THEN 1 ELSE 0 END) AS positive,
                SUM(CASE WHEN feedback = -1 THEN 1 ELSE 0 END) AS negative,
                SUM(CASE WHEN feedback IS NULL THEN 1 ELSE 0 END) AS unrated,
                ROUND(AVG(elapsed_ms), 0) AS avg_latency_ms
            FROM copilot_messages
            WHERE role = 'assistant' AND created_at >= DATE_SUB(NOW(), INTERVAL :days DAY)
        """), {"days": days})
        row = result.fetchone()

        stats["overview"] = {
            "total": row[0] or 0,
            "positive": row[1] or 0,
            "negative": row[2] or 0,
            "unrated": row[3] or 0,
            "avg_latency_ms": int(row[4] or 0),
            "satisfaction_rate": round((row[1] or 0) / max(((row[1] or 0) + (row[2] or 0)), 1) * 100, 1),
        }

        # 按 Skill 分布
        result = await db.execute(text("""
            SELECT
                JSON_UNQUOTE(JSON_EXTRACT(skills_used, '$[0]')) AS skill,
                COUNT(*) AS cnt,
                SUM(CASE WHEN feedback = 1 THEN 1 ELSE 0 END) AS pos,
                SUM(CASE WHEN feedback = -1 THEN 1 ELSE 0 END) AS neg
            FROM copilot_messages
            WHERE role = 'assistant'
              AND skills_used IS NOT NULL
              AND created_at >= DATE_SUB(NOW(), INTERVAL :days DAY)
            GROUP BY skill
            ORDER BY cnt DESC
        """), {"days": days})
        skill_rows = result.fetchall()

        stats["by_skill"] = [
            {"skill": r[0], "count": r[1], "positive": r[2], "negative": r[3]}
            for r in skill_rows
        ]

        # 按天趋势
        result = await db.execute(text("""
            SELECT
                DATE(created_at) AS dt,
                COUNT(*) AS total,
                SUM(CASE WHEN feedback = 1 THEN 1 ELSE 0 END) AS pos,
                SUM(CASE WHEN feedback = -1 THEN 1 ELSE 0 END) AS neg
            FROM copilot_messages
            WHERE role = 'assistant'
              AND created_at >= DATE_SUB(NOW(), INTERVAL :days DAY)
            GROUP BY dt ORDER BY dt
        """), {"days": days})
        trend_rows = result.fetchall()

        stats["daily_trend"] = [
            {"date": str(r[0]), "total": r[1], "positive": r[2], "negative": r[3]}
            for r in trend_rows
        ]

        # 最近差评消息
        result = await db.execute(text("""
            SELECT m.id, m.thread_id, m.content, m.feedback_text, m.skills_used, m.created_at
            FROM copilot_messages m
            WHERE m.role = 'assistant' AND m.feedback = -1
              AND m.created_at >= DATE_SUB(NOW(), INTERVAL :days DAY)
            ORDER BY m.created_at DESC LIMIT 20
        """), {"days": days})
        bad_rows = result.fetchall()

        stats["recent_negative"] = [
            {
                "id": r[0], "thread_id": r[1],
                "content": r[2][:200] if r[2] else "",
                "feedback_text": r[3], "skills_used": r[4],
                "created_at": str(r[5]),
            }
            for r in bad_rows
        ]

        return ok(stats)
    except Exception as e:
        logger.warning(f"[copilot_config] feedback_stats error: {e}")
        return ok({"overview": {}, "by_skill": [], "daily_trend": [], "recent_negative": []})


# ── 对话搜索 ──

@router.get("/copilot/config/search")
async def search_conversations(
    q: str = Query(..., min_length=1),
    mode: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    user: CurrentUser = Depends(admin_user),
    db: AsyncSession = Depends(get_async_db),
):
    """全文搜索对话消息"""
    try:
        sql = """
            SELECT m.id, m.thread_id, m.role, m.content, m.skills_used,
                   m.created_at, t.title, t.mode
            FROM copilot_messages m
            JOIN copilot_threads t ON m.thread_id = t.id
            WHERE m.content LIKE :q
        """
        params = {"q": f"%{q}%", "limit": limit}
        if mode:
            sql += " AND t.mode = :mode"
            params["mode"] = mode
        sql += " ORDER BY m.created_at DESC LIMIT :limit"

        result = await db.execute(text(sql), params)
        rows = result.fetchall()
        results = [
            {
                "message_id": r[0], "thread_id": r[1], "role": r[2],
                "content": r[3][:300] if r[3] else "",
                "skills_used": r[4],
                "created_at": str(r[5]),
                "thread_title": r[6], "mode": r[7],
            }
            for r in rows
        ]
        return ok({"results": results, "total": len(results), "query": q})
    except Exception as e:
        logger.warning(f"[copilot_config] search error: {e}")
        return ok({"results": [], "total": 0, "query": q})
