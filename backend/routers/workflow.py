# -*- coding: utf-8 -*-
"""backend/routers/workflow.py — Workflow 管理 API（瘦路由）

POST /api/v1/workflows/run          → 启动 workflow
GET  /api/v1/workflows/{id}/status   → 查询 workflow 状态
POST /api/v1/workflows/{id}/cancel   → 取消 workflow
GET  /api/v1/agents                  → Agent 列表
GET  /api/v1/agents/{id}             → Agent 详情
"""
import uuid
from typing import Optional

import sqlalchemy
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from backend.database import get_async_db
from backend.core.response import ok
from backend.core.cancel_registry import cancel_registry
from backend.core.exceptions import ResourceNotFoundError
from backend.core.bg_run_tracker import run_with_status
from backend.middleware.auth import get_optional_user, CurrentUser

router = APIRouter()


class WorkflowRunRequest(BaseModel):
    request_text: str
    request_type: Optional[str] = None
    use_mock:     bool = False
    thread_id:    Optional[str] = None


# ── Workflows ────────────────────────────────────────────────────

@router.post("/workflows/run", summary="启动 workflow 分析")
async def run_workflow(
    body:             WorkflowRunRequest,
    background_tasks: BackgroundTasks,
    db:               AsyncSession = Depends(get_async_db),
    opt_user:         CurrentUser | None = Depends(get_optional_user),
):
    run_id    = str(uuid.uuid4())
    thread_id = body.thread_id or str(uuid.uuid4())
    triggered_by = opt_user.username if opt_user else None

    # 插入 runs 表记录
    wf_name = body.request_type or "business_overview"
    try:
        await db.execute(sqlalchemy.text("""
            INSERT INTO runs (run_id, thread_id, request_id, entrypoint, workflow_name, status, triggered_by, started_at)
            VALUES (:run_id, :tid, :rid, :ep, :wf, 'pending', :triggered_by, NOW())
        """), {
            "run_id": run_id,
            "tid":    thread_id,
            "rid":    run_id,
            "ep":     "/api/v1/workflows/run",
            "wf":     wf_name,
            "triggered_by": triggered_by,
        })
        await db.commit()
    except sqlalchemy.exc.SQLAlchemyError as e:
        logger.warning(f"[workflow] insert run record failed (non-fatal): {e}")

    # 根据 request_type 路由到对应 workflow 后台任务
    try:
        from backend.routers.external.analyze import (
            _run_business_overview_bg, _run_risk_review_bg, _run_openclaw_bg,
        )
        _WORKFLOW_DISPATCH = {
            "business_overview": lambda: dict(
                run_id=run_id, thread_id=thread_id,
                request_text=body.request_text, use_mock=body.use_mock,
            ),
            "risk_review": lambda: dict(
                run_id=run_id, thread_id=thread_id,
                transaction_features=[],
            ),
            "openclaw": lambda: dict(
                run_id=run_id, thread_id=thread_id,
                customer_id="unknown", message=body.request_text,
            ),
        }
        _WORKFLOW_FN = {
            "business_overview": _run_business_overview_bg,
            "risk_review":       _run_risk_review_bg,
            "openclaw":          _run_openclaw_bg,
        }
        coro_fn     = _WORKFLOW_FN.get(wf_name, _run_business_overview_bg)
        coro_kwargs = _WORKFLOW_DISPATCH.get(wf_name, _WORKFLOW_DISPATCH["business_overview"])()
        background_tasks.add_task(
            run_with_status,
            run_id, coro_fn, coro_kwargs,
        )
    except Exception as e:
        logger.warning(f"[workflow] bg task schedule failed: {e}")

    return ok({
        "run_id":    run_id,
        "thread_id": thread_id,
        "status":    "pending",
    }, message="workflow 已提交，状态=pending")


@router.get("/workflows/{run_id}/status", summary="查询 workflow 状态")
async def get_workflow_status(run_id: str, db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(
        sqlalchemy.text(
            "SELECT run_id, workflow_name, status, started_at, ended_at, "
            "latency_ms, total_tokens, error_message "
            "FROM runs WHERE run_id = :run_id"
        ),
        {"run_id": run_id},
    )
    row = result.fetchone()
    if row is None:
        raise ResourceNotFoundError(f"run_id={run_id} 不存在")
    return ok(dict(row._mapping))


@router.post("/workflows/{run_id}/cancel", summary="取消 workflow")
async def cancel_workflow(run_id: str, db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(
        sqlalchemy.text(
            "UPDATE runs SET status='cancelled', ended_at=NOW() "
            "WHERE run_id = :run_id AND status IN ('pending','running')"
        ),
        {"run_id": run_id},
    )
    await db.commit()
    if result.rowcount == 0:
        raise ResourceNotFoundError(f"run_id={run_id} 不存在或已结束")
    cancel_registry.cancel(run_id)
    return ok({"run_id": run_id, "status": "cancelled"})


# ── Agents ───────────────────────────────────────────────────────

_AGENT_INFO = [
    {"id": "customer_agent",    "name": "客户分析 Agent",   "status": "loaded", "type": "specialist"},
    {"id": "forecast_agent",    "name": "销售预测 Agent",   "status": "loaded", "type": "specialist"},
    {"id": "fraud_agent",       "name": "欺诈风控 Agent",   "status": "loaded", "type": "specialist"},
    {"id": "sentiment_agent",   "name": "舆情分析 Agent",   "status": "loaded", "type": "specialist"},
    {"id": "inventory_agent",   "name": "库存优化 Agent",   "status": "loaded", "type": "specialist"},
    {"id": "openclaw_agent",    "name": "OpenClaw 客服 Agent", "status": "loaded", "type": "specialist"},
    {"id": "association_agent", "name": "关联分析 Agent",   "status": "loaded", "type": "specialist"},
    {"id": "supervisor_agent",  "name": "Supervisor Agent", "status": "loaded", "type": "orchestrator"},
]


def _enrich_agent(agent_id: str, registry: dict) -> dict:
    """从 registry 构建包含 load_status 和 degraded 标志的 agent 信息"""
    raw = registry.get(agent_id, "unknown")
    is_ready = raw == "ready"
    info = next((a for a in _AGENT_INFO if a["id"] == agent_id), None)
    return {
        "id":          agent_id,
        "name":        info["name"] if info else agent_id,
        "type":        info["type"] if info else "specialist",
        "load_status": "ready" if is_ready else "not_loaded",
        "degraded":    not is_ready,
        "status":      raw,
    }


@router.get("/agents", summary="Agent 列表")
async def list_agents(request: Request):
    registry = getattr(request.app.state, "agent_registry", {})
    if registry:
        items = [_enrich_agent(k, registry) for k in registry]
        return ok(items)
    return ok(_AGENT_INFO)


@router.get("/agents/{agent_id}", summary="Agent 详情")
async def get_agent(agent_id: str, request: Request):
    registry = getattr(request.app.state, "agent_registry", {})
    if registry and agent_id in registry:
        return ok(_enrich_agent(agent_id, registry))
    for a in _AGENT_INFO:
        if a["id"] == agent_id:
            return ok(a)
    raise ResourceNotFoundError(f"Agent {agent_id} 不存在")


