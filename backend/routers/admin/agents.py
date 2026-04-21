# -*- coding: utf-8 -*-
"""backend/routers/admin/agents.py

管理后台：Agent 概览 API
GET /admin/agents/overview → Agent 就绪状态 + run_steps 级统计
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy
from loguru import logger

from backend.database import get_async_db
from backend.middleware.auth import admin_user, CurrentUser

router = APIRouter(tags=["admin-agents"])

# LangGraph 类名 / 节点名 → 逻辑 agent 名 的映射
# run_steps.agent_name 存储的是 LangGraph 的类名，需要归并到 registry 的逻辑名
_CLASS_TO_LOGICAL: dict[str, str] = {
    "BusinessOverviewWorkflow": "customer_agent",
    "InsightComposerAgent":     "customer_agent",
    "SupervisorAgent":          "customer_agent",
    "ForecastAgent":            "forecast_agent",
    "FraudAgent":               "fraud_agent",
    "RiskReviewAgent":          "fraud_agent",
    "SentimentAgent":           "sentiment_agent",
    "InventoryAgent":           "inventory_agent",
    "OpenClawCustomerAgent":    "openclaw_agent",
    "AssociationAgent":         "association_agent",
}


def _resolve_name(raw_name: str) -> str:
    """将 DB 中的 agent_name（可能是 LangGraph 类名）转为逻辑名"""
    return _CLASS_TO_LOGICAL.get(raw_name, raw_name)


def _merge_stat(dest: dict, src: dict) -> None:
    """将 src 统计值累加到 dest"""
    dest["total_calls"]   = dest.get("total_calls", 0) + src.get("total_calls", 0)
    dest["success_calls"] = dest.get("success_calls", 0) + src.get("success_calls", 0)
    dest["error_calls"]   = dest.get("error_calls", 0) + src.get("error_calls", 0)
    # 延迟取最近一次的值（简单策略：取较大值）
    new_lat = src.get("avg_latency_ms", 0)
    old_lat = dest.get("avg_latency_ms", 0)
    dest["avg_latency_ms"] = new_lat if new_lat > old_lat else old_lat


@router.get("/agents/overview")
async def admin_agents_overview(request: Request, user: CurrentUser = Depends(admin_user), db: AsyncSession = Depends(get_async_db)):
    """
    返回 Agent 级别的运行统计，数据来源：
    - 就绪状态：app.state.agent_registry（由 lifespan 初始化写入）
    - 调用统计：run_steps 表按 agent_name 聚合（自动映射 LangGraph 类名）
    - 最近错误：run_steps 表 status='failed'
    - 参与 Workflow：run_steps JOIN runs 去重
    """
    registry = getattr(request.app.state, "agent_registry", {})

    try:
        # ── 1. 按 agent_name 聚合调用统计 ─────────────────────────
        stat_result = await db.execute(sqlalchemy.text("""
            SELECT
                agent_name,
                COUNT(*)                                              AS total_calls,
                SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END)  AS success_calls,
                SUM(CASE WHEN status='failed'    THEN 1 ELSE 0 END)  AS error_calls,
                ROUND(AVG(
                    TIMESTAMPDIFF(MICROSECOND, started_at, COALESCE(ended_at, NOW())) / 1000
                ), 0)                                                 AS avg_latency_ms
            FROM run_steps
            WHERE agent_name IS NOT NULL AND agent_name != ''
            GROUP BY agent_name
        """))
        stat_rows = stat_result.fetchall()

        stats: dict[str, dict] = {}
        for r in stat_rows:
            logical = _resolve_name(r[0])
            row_stat = {
                "total_calls":    int(r[1] or 0),
                "success_calls":  int(r[2] or 0),
                "error_calls":    int(r[3] or 0),
                "avg_latency_ms": int(r[4] or 0),
            }
            if logical not in stats:
                stats[logical] = row_stat
            else:
                _merge_stat(stats[logical], row_stat)

        # ── 2. 最近失败记录（每个 agent 最多 5 条）────────────────
        err_result = await db.execute(sqlalchemy.text("""
            SELECT agent_name, run_id, error_message, started_at
            FROM run_steps
            WHERE status = 'failed'
              AND agent_name IS NOT NULL AND agent_name != ''
            ORDER BY started_at DESC
            LIMIT 50
        """))
        err_rows = err_result.fetchall()

        errors_by_agent: dict[str, list] = {}
        for r in err_rows:
            name = _resolve_name(r[0])
            if name not in errors_by_agent:
                errors_by_agent[name] = []
            if len(errors_by_agent[name]) < 5:
                errors_by_agent[name].append({
                    "run_id": r[1],
                    "error":  r[2] or "unknown",
                    "time":   str(r[3]) if r[3] else None,
                })

        # ── 3. 参与的 Workflow 列表 ──────────────────────────────
        wf_result = await db.execute(sqlalchemy.text("""
            SELECT DISTINCT s.agent_name, r.workflow_name
            FROM run_steps s
            JOIN runs r ON s.run_id = r.run_id
            WHERE s.agent_name IS NOT NULL AND s.agent_name != ''
              AND r.workflow_name IS NOT NULL AND r.workflow_name != ''
        """))
        wf_rows = wf_result.fetchall()

        wfs_by_agent: dict[str, list] = {}
        for r in wf_rows:
            logical = _resolve_name(r[0])
            wfs_by_agent.setdefault(logical, [])
            wf_name = r[1]
            if wf_name not in wfs_by_agent[logical]:
                wfs_by_agent[logical].append(wf_name)

    except Exception as e:
        logger.warning(f"[admin_agents] run_steps query failed: {e}")
        stats, errors_by_agent, wfs_by_agent = {}, {}, {}

    # ── 4. 合并输出（以 registry 的逻辑名为主键）──────────────────
    all_names = sorted(set(registry.keys()) | set(stats.keys()))
    agents = []
    for name in all_names:
        s = stats.get(name, {})
        agents.append({
            "name":           name,
            "status":         registry.get(name, "unknown"),
            "total_calls":    s.get("total_calls", 0),
            "success_calls":  s.get("success_calls", 0),
            "error_calls":    s.get("error_calls", 0),
            "avg_latency_ms": s.get("avg_latency_ms", 0),
            "workflows":      wfs_by_agent.get(name, []),
            "recent_errors":  errors_by_agent.get(name, []),
        })

    return {"agents": agents}
