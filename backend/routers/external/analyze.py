# -*- coding: utf-8 -*-
"""backend/routers/external/analyze.py

外部分析入口
POST /api/v1/analyze  → SupervisorAgent 路由 → 对应 Workflow
GET  /api/v1/runs/{run_id}  → 查询 run 状态
"""
import uuid
from typing import List, Optional

import sqlalchemy
from fastapi import APIRouter, BackgroundTasks, Depends
from loguru import logger
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_db
from backend.agents.supervisor_agent import supervisor_agent, SupervisorInput
from backend.core.bg_run_tracker import run_with_status as _run_with_status
from backend.governance.guardrails.input_guard import input_guard
from backend.core.exceptions import BusinessError, ResourceNotFoundError
from backend.middleware.auth import get_optional_user, CurrentUser

router = APIRouter()



class AnalyzeRequest(BaseModel):
    request_text:  str
    request_type:  Optional[str] = None        # 可选显式路由
    use_mock:      bool = False
    thread_id:     Optional[str] = None
    customer_id:   Optional[str] = None        # openclaw 场景使用
    transaction_features: Optional[List] = None  # risk_review 批量交易特征


class AnalyzeResponse(BaseModel):
    run_id:    str
    thread_id: str
    route:     str
    status:    str
    message:   str
    stream_url: Optional[str] = None  # SSE 进度推送地址


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    req:              AnalyzeRequest,
    background_tasks: BackgroundTasks,
    db:               AsyncSession = Depends(get_async_db),
    opt_user:         CurrentUser | None = Depends(get_optional_user),
):
    """
    业务分析主入口。
    1. InputGuard 输入安全检查
    2. SupervisorAgent 异步路由
    3. 异步启动对应 workflow
    4. 返回 run_id + SSE stream_url
    """
    run_id    = str(uuid.uuid4())
    thread_id = req.thread_id or str(uuid.uuid4())
    triggered_by = opt_user.username if opt_user else None

    # 0. InputGuard 输入安全检查
    guard_result = input_guard.check(req.request_text)
    if not guard_result.passed:
        raise BusinessError(
            f"输入被拦截: {guard_result.blocked_reason}",
            error_code="INPUT_GUARD_REJECTED",
        )
    safe_text = guard_result.sanitized_text or req.request_text

    # 1. SupervisorAgent 异步路由
    sup_out = await supervisor_agent.aroute(SupervisorInput(
        request_text=safe_text,
        request_type=req.request_type,
        run_id=run_id,
        thread_id=thread_id,
    ))

    # 2. 统一创建 pending run 记录
    route = sup_out.route
    try:
        await db.execute(sqlalchemy.text("""
            INSERT INTO runs (run_id, thread_id, request_id, entrypoint, workflow_name, status, triggered_by, started_at)
            VALUES (:run_id, :tid, :rid, :ep, :wf, 'pending', :triggered_by, NOW())
        """), {
            "run_id": run_id, "tid": thread_id, "rid": run_id,
            "ep": "/api/v1/analyze", "wf": route, "triggered_by": triggered_by,
        })
        await db.commit()
    except sqlalchemy.exc.SQLAlchemyError as e:
        logger.warning(f"[analyze] insert run record failed (non-fatal): {e}")

    # 3. 异步启动对应 workflow
    if route == "business_overview":
        background_tasks.add_task(
            _run_with_status, run_id, _run_business_overview_bg,
            dict(run_id=run_id, thread_id=thread_id,
                 request_text=req.request_text, use_mock=req.use_mock),
        )
    elif route == "risk_review":
        background_tasks.add_task(
            _run_with_status, run_id, _run_risk_review_bg,
            dict(run_id=run_id, thread_id=thread_id,
                 transaction_features=req.transaction_features or []),
        )
    elif route == "openclaw":
        background_tasks.add_task(
            _run_with_status, run_id, _run_openclaw_bg,
            dict(run_id=run_id, thread_id=thread_id,
                 customer_id=req.customer_id or "unknown", message=req.request_text),
        )
    elif route == "ops_copilot":
        return AnalyzeResponse(
            run_id=run_id,
            thread_id=thread_id,
            route=route,
            status="rejected",
            message="运维诊断请求请使用 POST /admin/ops-copilot/ask 接口",
        )
    else:
        logger.warning(
            f"[analyze] unhandled route={route}, falling back to business_overview. "
            f"run_id={run_id}"
        )
        background_tasks.add_task(
            _run_with_status, run_id, _run_business_overview_bg,
            dict(run_id=run_id, thread_id=thread_id,
                 request_text=req.request_text, use_mock=req.use_mock),
        )

    return AnalyzeResponse(
        run_id=run_id,
        thread_id=thread_id,
        route=route,
        status="accepted",
        message=f"分析请求已接收，workflow={route}，置信度={sup_out.confidence:.2f}",
        stream_url=f"/api/v1/workflows/{run_id}/stream",
    )


@router.get("/runs/{run_id}")
async def get_run_status(run_id: str, db: AsyncSession = Depends(get_async_db)):
    """查询 run 状态（从 MySQL runs 表）"""
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

    return dict(row._mapping)


@router.get("/artifacts/{artifact_id}")
async def get_artifact(artifact_id: str, db: AsyncSession = Depends(get_async_db)):
    """查询 artifact 元数据（从 MySQL artifacts 表）"""
    result = await db.execute(
        sqlalchemy.text(
            "SELECT artifact_id, artifact_type, artifact_uri, content_type, "
            "summary, run_id, created_at "
            "FROM artifacts WHERE artifact_id = :id"
        ),
        {"id": artifact_id},
    )
    row = result.fetchone()

    if row is None:
        raise ResourceNotFoundError(f"artifact_id={artifact_id} 不存在")

    return dict(row._mapping)



async def _run_business_overview_bg(
    run_id: str,
    thread_id: str,
    request_text: str,
    use_mock: bool,
) -> None:
    try:
        from backend.agents.workflows.business_overview import run_business_overview
        await run_business_overview(
            request_text=request_text,
            use_mock=use_mock,
            thread_id=thread_id,
            run_id=run_id,
        )
    except Exception as e:
        logger.error(f"[analyze bg business_overview] run_id={run_id} error: {e}")


async def _run_risk_review_bg(
    run_id: str,
    thread_id: str,
    transaction_features: list,
) -> None:
    try:
        from backend.agents.workflows.risk_review import run_risk_review
        await run_risk_review(
            transaction_features=transaction_features,
            thread_id=thread_id,
            run_id=run_id,
        )
    except Exception as e:
        logger.error(f"[analyze bg risk_review] run_id={run_id} error: {e}")


async def _run_openclaw_bg(
    run_id: str,
    thread_id: str,
    customer_id: str,
    message: str,
) -> None:
    try:
        from backend.agents.workflows.openclaw_session import run_openclaw_session
        await run_openclaw_session(
            customer_id=customer_id,
            message=message,
            session_id=thread_id,
            run_id=run_id,
        )
    except Exception as e:
        logger.error(f"[analyze bg openclaw] run_id={run_id} error: {e}")
