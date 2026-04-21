# -*- coding: utf-8 -*-
"""backend/routers/admin/reviews.py

管理后台：HITL 审核 API
所有审核动作（approve / edit / reject）仅通过此路由暴露，不对外部 API 开放。

审批动作完成后，若 review_case.context_json 中包含 thread_id，
则通过 BackgroundTask 调用 resume_risk_review(thread_id) 恢复
LangGraph 暂停的 risk_review workflow，实现 HITL 闭环。
"""
import json
import sqlalchemy
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.concurrency import run_in_threadpool
from loguru import logger
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_db, SessionLocal
from backend.core.exceptions import AppError
from backend.middleware.auth import admin_user, risk_reviewer, CurrentUser
from backend.governance.trace_center.audit import write_audit_log
from backend.governance.hitl_center.hitl import (
    list_review_cases, get_review_case,
    approve_case, edit_case, reject_case,
)

router = APIRouter(tags=["admin-reviews"])


# ── 请求体 ─────────────────────────────────────────────────────────

class ApproveBody(BaseModel):
    note:        Optional[str] = None

class EditBody(BaseModel):
    override_payload: Optional[Dict[str, Any]] = None
    note:             Optional[str] = None

class RejectBody(BaseModel):
    note:        Optional[str] = None


# ── 路由 ───────────────────────────────────────────────────────────

@router.get("/reviews")
async def admin_list_reviews(
    status:      Optional[str] = None,
    priority:    Optional[str] = None,
    review_type: Optional[str] = None,
    limit:       int = 50,
    offset:      int = 0,
    user:        CurrentUser = Depends(admin_user),
    db:          AsyncSession = Depends(get_async_db),
):
    sync_db = SessionLocal()
    try:
        items = await run_in_threadpool(
            list_review_cases, sync_db,
            status=status, priority=priority,
            review_type=review_type, limit=limit, offset=offset,
        )
    finally:
        sync_db.close()
    # total count for pagination
    try:
        filters = "WHERE 1=1"
        count_params: dict = {}
        if status:
            filters += " AND status = :status"
            count_params["status"] = status
        if priority:
            filters += " AND priority = :priority"
            count_params["priority"] = priority
        if review_type:
            filters += " AND review_type = :review_type"
            count_params["review_type"] = review_type
        count_r = await db.execute(
            sqlalchemy.text(f"SELECT COUNT(*) FROM review_cases {filters}"),
            count_params,
        )
        total = count_r.scalar() or 0
    except Exception:
        total = len(items)
    return {"items": items, "total": total}


@router.get("/reviews/{case_id}")
async def admin_get_review(case_id: str, user: CurrentUser = Depends(admin_user)):
    sync_db = SessionLocal()
    try:
        case = await run_in_threadpool(get_review_case, sync_db, case_id)
    finally:
        sync_db.close()
    if case is None:
        raise AppError(404, f"case_id={case_id} 不存在")
    return case


@router.post("/reviews/{case_id}/approve")
async def admin_approve(
    case_id:          str,
    body:             ApproveBody,
    background_tasks: BackgroundTasks,
    user:             CurrentUser = Depends(risk_reviewer),
):
    sync_db = SessionLocal()
    try:
        action_id = await run_in_threadpool(approve_case, sync_db, case_id, user.username, body.note)
        await _schedule_workflow_resume(sync_db, case_id, background_tasks)
        write_audit_log(
            sync_db, operator=user.username, action="approve_review",
            target_type="review_case", target_id=case_id,
            after={"note": body.note},
        )
    finally:
        sync_db.close()
    return {"action_id": action_id, "status": "approved"}


@router.post("/reviews/{case_id}/edit")
async def admin_edit(
    case_id:          str,
    body:             EditBody,
    background_tasks: BackgroundTasks,
    user:             CurrentUser = Depends(risk_reviewer),
):
    sync_db = SessionLocal()
    try:
        action_id = await run_in_threadpool(edit_case, sync_db, case_id, user.username, body.override_payload or {}, body.note)
        await _schedule_workflow_resume(sync_db, case_id, background_tasks)
        write_audit_log(
            sync_db, operator=user.username, action="edit_review",
            target_type="review_case", target_id=case_id,
            after={"note": body.note, "has_override": bool(body.override_payload)},
        )
    finally:
        sync_db.close()
    return {"action_id": action_id, "status": "edited"}


@router.post("/reviews/{case_id}/reject")
async def admin_reject(
    case_id:          str,
    body:             RejectBody,
    background_tasks: BackgroundTasks,
    user:             CurrentUser = Depends(risk_reviewer),
):
    sync_db = SessionLocal()
    try:
        action_id = await run_in_threadpool(reject_case, sync_db, case_id, user.username, body.note)
        await _schedule_workflow_resume(sync_db, case_id, background_tasks)
        write_audit_log(
            sync_db, operator=user.username, action="reject_review",
            target_type="review_case", target_id=case_id,
            after={"note": body.note},
        )
    finally:
        sync_db.close()
    return {"action_id": action_id, "status": "rejected"}


# ── HITL 闭环：审批后恢复 LangGraph workflow ──────────────────────

async def _schedule_workflow_resume(
    db,
    case_id:          str,
    background_tasks: BackgroundTasks,
) -> None:
    """
    从 review_cases.context_json 读取 thread_id，
    若存在则安排后台任务恢复 risk_review workflow。
    失败仅记录 warning，不影响审批响应。
    """
    try:
        row = await run_in_threadpool(
            lambda: db.execute(
                sqlalchemy.text(
                    "SELECT context_json FROM review_cases WHERE case_id = :id"
                ),
                {"id": case_id},
            ).fetchone()
        )
        if row is None:
            return
        ctx = json.loads(row[0] or "{}")
        thread_id = ctx.get("thread_id")
        if thread_id:
            logger.info(
                f"[reviews] scheduling workflow resume "
                f"case_id={case_id} thread_id={thread_id}"
            )
            background_tasks.add_task(_resume_workflow_bg, thread_id=thread_id)
        else:
            logger.debug(
                f"[reviews] no thread_id in context_json, skipping resume "
                f"case_id={case_id}"
            )
    except Exception as e:
        logger.warning(
            f"[reviews] _schedule_workflow_resume failed (non-fatal) "
            f"case_id={case_id}: {e}"
        )


async def _resume_workflow_bg(thread_id: str) -> None:
    """后台任务：调用 resume_risk_review 恢复 LangGraph workflow"""
    try:
        from backend.agents.workflows.risk_review import resume_risk_review
        await resume_risk_review(thread_id)
    except Exception as e:
        logger.error(
            f"[reviews] resume_workflow_bg failed thread_id={thread_id}: {e}"
        )
