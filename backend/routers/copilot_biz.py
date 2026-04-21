# -*- coding: utf-8 -*-
"""backend/routers/copilot_biz.py — 运营助手 SSE 端点（业务空间）

与 admin/copilot_stream.py 共用 CopilotEngine，但 mode="biz"。
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from backend.database import get_async_db
from backend.core.response import ok
from backend.middleware.auth import get_current_user, CurrentUser
from backend.copilot.engine import CopilotEngine
from backend.copilot.persistence import CopilotPersistence
from backend.copilot.actions import ActionExecutor
from backend.copilot.agent_logger import get_agent_logger

router = APIRouter(tags=["copilot-biz"])


class BizStreamBody(BaseModel):
    question: str
    thread_id: Optional[str] = None
    page_context: Optional[dict] = None


class BizFeedbackBody(BaseModel):
    message_id: int
    feedback: int = Field(..., ge=-1, le=1)
    feedback_text: Optional[str] = None


class BizActionBody(BaseModel):
    action_type: str
    target: str
    payload: Optional[dict] = None
    thread_id: Optional[str] = None
    message_id: Optional[int] = None


def _get_biz_user(user: CurrentUser) -> tuple[str, str]:
    """从 JWT 中提取业务空间用户信息"""
    user_id = user.username
    user_role = user.roles[0] if user.roles else "biz_viewer"
    return user_id, user_role


@router.post("/copilot/stream")
async def biz_copilot_stream(
    body: BizStreamBody,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """运营助手 SSE 流式对话"""
    thread_id = body.thread_id or str(uuid.uuid4())
    user_id, user_role = _get_biz_user(user)
    mode = "biz"
    agent_log = get_agent_logger(mode)

    agent_log.info(
        f"[biz:stream] user={user_id} role={user_role} "
        f"thread={thread_id} q='{body.question[:60]}'"
    )

    redis = request.app.state.redis if hasattr(request.app.state, "redis") else None
    # R6-2: 从 app.state.container 注入 AgentContainer（container 未挂载时传 None，Engine 走旧路径）
    _app_container = getattr(request.app.state, "container", None)
    engine = CopilotEngine(
        redis=redis, db=db,
        container=(_app_container.agent if _app_container is not None else None),
    )
    persistence = CopilotPersistence(db=db)

    await persistence.get_or_create_thread(thread_id, user_id, mode)
    await persistence.save_message(thread_id, "user", body.question, source="web")

    async def event_generator():
        collected_text = []
        # R6-1: Pipeline v2 flag 开启时走 run_v2，否则走原 run
        from backend.config import settings as _s
        _runner = engine.run_v2 if _s.COPILOT_PIPELINE_V2 else engine.run
        try:
            async for event in _runner(
                question=body.question,
                mode=mode,
                user_id=user_id,
                user_role=user_role,
                thread_id=thread_id,
                page_context=body.page_context,
                source="web",
            ):
                if event.type.value == "text_delta" and event.content:
                    collected_text.append(event.content)
                yield event.to_sse()
        except Exception as e:
            from backend.copilot.events import run_error_event
            yield run_error_event(str(e)).to_sse()
        finally:
            full_text = "".join(collected_text)
            if full_text:
                await persistence.save_message(thread_id, "assistant", full_text, source="web")
                await engine.save_assistant_reply(thread_id, full_text)
            if full_text and len(body.question) > 2:
                await persistence.update_thread_title(thread_id, body.question[:50])

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "X-Thread-Id": thread_id},
    )


@router.get("/copilot/threads")
async def biz_list_threads(
    page_origin: Optional[str] = None,
    limit: int = 50, offset: int = 0,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    user_id, _ = _get_biz_user(user)
    persistence = CopilotPersistence(db=db)
    threads = await persistence.list_threads(
        user_id, mode="biz", page_origin=page_origin, limit=limit, offset=offset,
    )
    return ok({"threads": threads, "total": len(threads)})


@router.get("/copilot/threads/{thread_id}/messages")
async def biz_get_messages(
    thread_id: str, limit: int = 100, offset: int = 0,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    persistence = CopilotPersistence(db=db)
    messages = await persistence.get_thread_messages(thread_id, limit, offset)
    return ok({"messages": messages, "total": len(messages)})


@router.post("/copilot/feedback")
async def biz_feedback(body: BizFeedbackBody, db: AsyncSession = Depends(get_async_db)):
    persistence = CopilotPersistence(db=db)
    await persistence.set_feedback(body.message_id, body.feedback, body.feedback_text)
    return ok({"status": "ok"})


@router.post("/copilot/action/execute")
async def biz_action(
    body: BizActionBody,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    user_id, user_role = _get_biz_user(user)
    feishu = request.app.state.feishu if hasattr(request.app.state, "feishu") else None
    executor = ActionExecutor(db=db, feishu_bridge=feishu)
    result = await executor.execute(
        action_type=body.action_type, user_id=user_id, user_role=user_role,
        target=body.target, payload=body.payload,
        thread_id=body.thread_id, message_id=body.message_id,
    )
    return ok(result)
