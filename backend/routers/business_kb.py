# -*- coding: utf-8 -*-
"""backend/routers/business_kb.py — 业务前台 KB 路由（含 §3.4 反馈写入）

定位
----
区别于 ``backend/routers/admin/knowledge_v2.py`` 的管理后台 CRUD，
本模块挂在 ``/api/kb/*`` 下，**面向已登录的业务/运营/客服用户**，
当前阶段只暴露 §3.4 反馈写入接口（POST /api/kb/feedback）。

后续 §4 业务前台一体化时，会在此扩展：
* ``POST /api/kb/answer``  RAG 答案接口（带 grounding 校验）
* ``GET  /api/kb/search``  domain 受限的统一搜索代理

鉴权：
* POST /api/kb/feedback —— 任意已登录用户即可（业务侧需要低门槛收集 bad case）
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from backend.core.response import ok
from backend.database import get_db
from backend.knowledge.feedback_service import KBFeedbackService
from backend.knowledge.schemas import (
    FEEDBACK_REASONS,
    FEEDBACK_SOURCES,
    KBFeedbackIn,
)
from backend.middleware.auth import CurrentUser, get_current_user

router = APIRouter(tags=["business-kb"])


@router.post("/kb/feedback")
def submit_kb_feedback(
    body: KBFeedbackIn,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """提交一条 KB 反馈（👍/👎/🤷）。

    ``trace_id`` 优先取 body；缺省时回退到中间件注入的 ``request.state.trace_id``。
    """
    # 防御性归一：未在受控值内的 reason / source 一律走 'other' / 'biz_kb'
    rating_reason = body.rating_reason if body.rating_reason in FEEDBACK_REASONS else None
    if body.rating_reason and rating_reason is None:
        rating_reason = "other"
    source = body.source if body.source in FEEDBACK_SOURCES else "biz_kb"

    trace_id: Optional[str] = body.trace_id
    if not trace_id:
        trace_id = getattr(request.state, "trace_id", None)

    svc = KBFeedbackService.get_instance()
    result = svc.submit(
        db,
        user_id=user.username,
        query=body.query,
        rating=body.rating,
        trace_id=trace_id,
        kb_id=body.kb_id,
        answer=body.answer,
        citations=body.citations,
        rating_reason=rating_reason,
        free_text=body.free_text,
        source=source,
    )
    return ok({
        "feedback_id": result["feedback_id"],
        "action": result["action"],
        "trace_id": trace_id,
    }, trace_id=trace_id)
