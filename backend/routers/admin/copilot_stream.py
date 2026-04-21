# -*- coding: utf-8 -*-
"""backend/routers/admin/copilot_stream.py — Copilot SSE 流式端点 + 历史 API

管理控制台（运维助手）入口：
  POST /admin/copilot/stream   → SSE 流式对话
  GET  /admin/copilot/threads  → 对话历史列表
  GET  /admin/copilot/threads/{id}/messages → 线程消息
  POST /admin/copilot/feedback → 消息反馈
  POST /admin/copilot/action/execute → 执行 Action
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from backend.database import get_async_db, get_redis
from backend.core.response import ok
from backend.middleware.auth import admin_user, CurrentUser
from backend.copilot.engine import CopilotEngine
from backend.copilot.persistence import CopilotPersistence
from backend.copilot.actions import ActionExecutor
from backend.copilot.agent_logger import get_agent_logger

router = APIRouter(tags=["copilot-stream"])


# ── Request Schemas ──

class CopilotStreamBody(BaseModel):
    question: str
    thread_id: Optional[str] = None
    page_context: Optional[dict] = None
    mode: str = "ops"  # 管理台默认 ops


class FeedbackBody(BaseModel):
    message_id: int
    feedback: int = Field(..., ge=-1, le=1)
    feedback_text: Optional[str] = None


class ActionExecuteBody(BaseModel):
    action_type: str
    target: str
    payload: Optional[dict] = None
    thread_id: Optional[str] = None
    message_id: Optional[int] = None


# ── SSE 流式对话 ──

@router.post("/copilot/stream")
async def copilot_stream(
    body: CopilotStreamBody,
    request: Request,
    user: CurrentUser = Depends(admin_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Copilot SSE 流式对话端点"""
    thread_id = body.thread_id or str(uuid.uuid4())
    user_id = user.username
    user_role = user.roles[0] if user.roles else "biz_viewer"
    mode = body.mode
    agent_log = get_agent_logger(mode)

    agent_log.info(
        f"[stream:request] user={user_id} role={user_role} mode={mode} "
        f"thread={thread_id} q='{body.question[:60]}'"
    )

    redis = request.app.state.redis if hasattr(request.app.state, "redis") else None
    feishu = request.app.state.feishu if hasattr(request.app.state, "feishu") else None
    # R6-2: 从 app.state.container 注入 AgentContainer（container 未挂载时传 None，Engine 走旧路径）
    _app_container = getattr(request.app.state, "container", None)
    engine = CopilotEngine(
        redis=redis, db=db,
        container=(_app_container.agent if _app_container is not None else None),
    )
    persistence = CopilotPersistence(db=db)

    # 确保线程存在
    await persistence.get_or_create_thread(
        thread_id=thread_id,
        user_id=user_id,
        mode=mode,
        page_origin=body.page_context.get("page") if body.page_context else None,
    )

    # 持久化用户消息
    await persistence.save_message(
        thread_id=thread_id,
        role="user",
        content=body.question,
        source="web",
    )

    async def event_generator():
        collected_text = []
        collected_thinking = []
        collected_skills = []
        collected_artifacts = []

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
                # 收集数据用于持久化
                if event.type.value == "text_delta" and event.content:
                    collected_text.append(event.content)
                elif event.type.value == "thinking_delta" and event.content:
                    collected_thinking.append(event.content)
                elif event.type.value == "tool_call_start" and event.metadata:
                    skill = event.metadata.get("skill")
                    if skill:
                        collected_skills.append(skill)
                elif event.type.value == "artifact_delta" and event.content:
                    collected_artifacts.append(event.content)

                yield event.to_sse()

        except Exception as e:
            logger.error(f"[stream:error] {e}")
            from backend.copilot.events import run_error_event
            yield run_error_event(str(e)).to_sse()
        finally:
            # 持久化助手回答
            full_text = "".join(collected_text)
            if full_text:
                await persistence.save_message(
                    thread_id=thread_id,
                    role="assistant",
                    content=full_text,
                    skills_used=collected_skills or None,
                    thinking="".join(collected_thinking) or None,
                    artifacts=collected_artifacts or None,
                    source="web",
                )
                # 保存到 Redis 以支持多轮上下文
                await engine.save_assistant_reply(thread_id, full_text)

            # 自动生成标题（首条消息后）
            if full_text and len(body.question) > 2:
                short_title = body.question[:50]
                await persistence.update_thread_title(thread_id, short_title)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Thread-Id": thread_id,
        },
    )


# ── 历史列表 ──

@router.get("/copilot/threads")
async def list_threads(
    mode: Optional[str] = None,
    page_origin: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user: CurrentUser = Depends(admin_user),
    db: AsyncSession = Depends(get_async_db),
):
    persistence = CopilotPersistence(db=db)
    threads = await persistence.list_threads(
        user_id=user.username,
        mode=mode,
        page_origin=page_origin,
        limit=limit,
        offset=offset,
    )
    return ok({"threads": threads, "total": len(threads)})


@router.get("/copilot/threads/{thread_id}/messages")
async def get_thread_messages(
    thread_id: str,
    limit: int = 100,
    offset: int = 0,
    user: CurrentUser = Depends(admin_user),
    db: AsyncSession = Depends(get_async_db),
):
    persistence = CopilotPersistence(db=db)
    messages = await persistence.get_thread_messages(thread_id, limit, offset)
    return ok({"messages": messages, "total": len(messages)})


# ── 反馈 ──

@router.post("/copilot/feedback")
async def submit_feedback(
    body: FeedbackBody,
    user: CurrentUser = Depends(admin_user),
    db: AsyncSession = Depends(get_async_db),
):
    persistence = CopilotPersistence(db=db)
    await persistence.set_feedback(body.message_id, body.feedback, body.feedback_text)
    return ok({"status": "ok"})


# ── Action 执行 ──

@router.post("/copilot/action/execute")
async def execute_action(
    body: ActionExecuteBody,
    request: Request,
    user: CurrentUser = Depends(admin_user),
    db: AsyncSession = Depends(get_async_db),
):
    feishu = request.app.state.feishu if hasattr(request.app.state, "feishu") else None
    executor = ActionExecutor(db=db, feishu_bridge=feishu)

    result = await executor.execute(
        action_type=body.action_type,
        user_id=user.username,
        user_role=user.roles[0] if user.roles else "biz_viewer",
        target=body.target,
        payload=body.payload,
        thread_id=body.thread_id,
        message_id=body.message_id,
    )
    return ok(result)


# ── 线程管理 ──

@router.post("/copilot/threads/{thread_id}/pin")
async def pin_thread(
    thread_id: str,
    user: CurrentUser = Depends(admin_user),
    db: AsyncSession = Depends(get_async_db),
):
    persistence = CopilotPersistence(db=db)
    await persistence.pin_thread(thread_id, True)
    return ok({"status": "pinned"})


@router.post("/copilot/threads/{thread_id}/unpin")
async def unpin_thread(
    thread_id: str,
    user: CurrentUser = Depends(admin_user),
    db: AsyncSession = Depends(get_async_db),
):
    persistence = CopilotPersistence(db=db)
    await persistence.pin_thread(thread_id, False)
    return ok({"status": "unpinned"})
