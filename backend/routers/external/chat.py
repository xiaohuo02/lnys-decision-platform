# -*- coding: utf-8 -*-
"""backend/routers/external/chat.py

外部客服入口
POST /api/v1/chat/openclaw  → OpenClaw 客服对话（同步，当前阶段）
"""
import uuid
from typing import Optional

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from backend.database import SessionLocal
from backend.agents.openclaw_agent import openclaw_customer_agent, OpenClawInput

router = APIRouter()


class ChatRequest(BaseModel):
    customer_id: str
    message:     str
    session_id:  Optional[str] = None


class ChatResponse(BaseModel):
    session_id:    str
    reply:         str
    intent:        str
    confidence:    float
    handoff:       bool
    handoff_reason: Optional[str]
    sources:       list


@router.post("/chat/openclaw", response_model=ChatResponse)
async def chat_openclaw(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    inp = OpenClawInput(
        session_id=session_id,
        customer_id=req.customer_id,
        message=req.message,
    )

    def _sync_respond():
        db = SessionLocal()
        try:
            return openclaw_customer_agent.respond(inp, db)
        finally:
            db.close()

    # 在线程池中执行同步 respond()，避免阻塞 FastAPI 事件循环
    output = await run_in_threadpool(_sync_respond)
    return ChatResponse(
        session_id=output.session_id,
        reply=output.reply,
        intent=output.intent,
        confidence=output.confidence,
        handoff=output.handoff,
        handoff_reason=output.handoff_reason,
        sources=output.sources,
    )
