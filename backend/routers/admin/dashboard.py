# -*- coding: utf-8 -*-
"""backend/routers/admin/dashboard.py

管理后台：Dashboard 汇总 API
GET /admin/dashboard/summary → KPI 指标汇总
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy
from loguru import logger

from backend.database import get_async_db
from backend.core.response import degraded
from backend.middleware.auth import admin_user, CurrentUser

router = APIRouter(tags=["admin-dashboard"])


@router.get("/dashboard/summary")
async def admin_dashboard_summary(
    user: CurrentUser = Depends(admin_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    返回治理控制台首页所需的关键 KPI：
    - 最近 24h 请求量 / 成功率 / 平均耗时
    - 待审核 HITL 数量
    - 失败 workflow 数量
    """
    try:
        # 最近 24h runs 统计
        run_result = await db.execute(sqlalchemy.text("""
            SELECT
                COUNT(*) AS total_runs,
                SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS success_runs,
                SUM(CASE WHEN status='failed'    THEN 1 ELSE 0 END) AS failed_runs,
                ROUND(AVG(latency_ms), 0) AS avg_latency_ms,
                SUM(total_tokens) AS total_tokens
            FROM runs
            WHERE started_at >= NOW() - INTERVAL 1 DAY
        """))
        run_stats = run_result.fetchone()

        # 待审核数量
        pr_result = await db.execute(sqlalchemy.text(
            "SELECT COUNT(*) AS cnt FROM review_cases WHERE status='pending'"
        ))
        pending_reviews = pr_result.fetchone()

        total   = int(run_stats[0] or 0)
        success = int(run_stats[1] or 0)
        failed  = int(run_stats[2] or 0)

        # workflow 分布
        wf_result = await db.execute(sqlalchemy.text("""
            SELECT workflow_name, COUNT(*) AS cnt
            FROM runs
            WHERE started_at >= NOW() - INTERVAL 1 DAY
              AND workflow_name IS NOT NULL AND workflow_name != ''
            GROUP BY workflow_name ORDER BY cnt DESC
        """))
        wf_rows = wf_result.fetchall()
        wf_dist = {r[0]: int(r[1]) for r in wf_rows} if wf_rows else {}

        return {
            "period":         "last_24h",
            "total_runs":     total,
            "success_runs":   success,
            "failed_runs":    failed,
            "success_rate":   round(success / max(total, 1), 4),
            "avg_latency_ms": int(run_stats[3] or 0),
            "total_tokens":   int(run_stats[4] or 0),
            "pending_reviews": int(pending_reviews[0] or 0),
            "workflow_distribution": wf_dist,
        }
    except Exception as e:
        logger.warning(f"[admin_dashboard] summary query failed: {e}")
        return degraded({
            "period":         "last_24h",
            "total_runs":     0,
            "success_runs":   0,
            "failed_runs":    0,
            "success_rate":   0,
            "avg_latency_ms": 0,
            "total_tokens":   0,
            "pending_reviews": 0,
            "workflow_distribution": {},
        }, reason="dashboard query failed", source="error")
