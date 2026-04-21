# -*- coding: utf-8 -*-
"""backend/routers/chat.py — OpenClaw 客服 API（瘦路由）"""
import asyncio
import json

from typing import Any
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from loguru import logger

from backend.dependencies.db import DbSession
from backend.dependencies.redis import RedisClient
from backend.dependencies.agents import get_optional_agent
from backend.schemas.base import ApiResponse
from backend.schemas.chat_schemas import ChatMessageRequest, ChatMessageResponse, ChatHistoryResponse
from backend.services.chat_service import ChatService

router = APIRouter()


def _svc(
    db:    DbSession,
    redis: RedisClient,
    agent = get_optional_agent("openclaw_agent"),
) -> ChatService:
    return ChatService(db, redis, agent)


@router.post("/message", summary="OpenClaw 对话（C-L-O-A-W 五层）", response_model=ApiResponse[ChatMessageResponse])
async def send_message(
    body: ChatMessageRequest,
    svc:  ChatService = Depends(_svc),
):
    return await svc.send_message(body)


@router.post("/stream", summary="OpenClaw 流式对话（SSE）")
async def stream_chat(
    request: Request,
    body: ChatMessageRequest,
    svc:  ChatService = Depends(_svc),
):
    """
    SSE 流式聊天端点。
    协议：
      event: token    data: {"content":"..."}
      event: done     data: {"intent":"...","confidence":0.9,"sources":[]}
      event: error    data: {"message":"..."}
    当前阶段：先获取完整回复，再逐字符模拟流式输出。
    """

    async def event_generator():
        try:
            # 获取完整回复
            result = await svc.send_message(body)
            data = result.get("data", result) if isinstance(result, dict) else result

            reply      = data.get("reply", "")
            intent     = data.get("intent", "")
            confidence = data.get("confidence", 0)
            sources    = data.get("sources", [])

            if not reply:
                yield _sse("error", {"message": "空回复"})
                return

            # 逐块流式输出（每 3-5 字符一块，模拟 token 流）
            chunk_size = 4
            for i in range(0, len(reply), chunk_size):
                if await request.is_disconnected():
                    return
                chunk = reply[i:i + chunk_size]
                yield _sse("token", {"content": chunk})
                await asyncio.sleep(0.03)

            # 完成事件
            yield _sse("done", {
                "intent": intent,
                "confidence": confidence,
                "sources": sources if isinstance(sources, list) else [],
            })

        except Exception as e:
            logger.error(f"[chat/stream] error: {e}")
            yield _sse("error", {"message": "对话服务异常，请稍后重试"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/history/{session_id}", summary="对话历史（MySQL）", response_model=ApiResponse[ChatHistoryResponse])
async def get_history(
    session_id: str,
    svc: ChatService = Depends(_svc),
):
    return await svc.get_history(session_id)


@router.delete("/session/{session_id}", summary="删除会话（Redis + MySQL）", response_model=ApiResponse[Any])
async def delete_session(
    session_id: str,
    svc: ChatService = Depends(_svc),
):
    return await svc.delete_session(session_id)


def _sse(event: str, data: dict) -> str:
    """格式化 SSE 事件"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
