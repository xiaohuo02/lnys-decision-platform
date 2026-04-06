# -*- coding: utf-8 -*-
"""backend/schemas/chat_schemas.py — OpenClaw 客服 Pydantic 模型"""
from pydantic import BaseModel, Field
from typing import Optional, List


# ── 发消息请求 ────────────────────────────────────────────────
class ChatMessageRequest(BaseModel):
    session_id:  str           = Field(..., examples=["sess-uuid-xxxx"])
    message:     str           = Field(..., min_length=1, max_length=1000)
    customer_id: Optional[str] = Field(None, examples=["LY000088"])


# ── 消息响应（方案_07 § 4.6）─────────────────────────────────
class ChatMessageResponse(BaseModel):
    session_id:           Optional[str] = None
    customer_id:          Optional[str] = None
    reply:                str
    intent:               str   = "unknown"
    confidence:           float = Field(0.0, ge=0.0, le=1.0)
    handoff:              bool  = False
    handoff_reason:       Optional[str] = None
    sources:              List[str] = Field(default_factory=list)
    degraded:             bool  = False
    session_context_size: int   = 0


# ── 历史记录 ──────────────────────────────────────────────────
class ChatHistoryItem(BaseModel):
    id:         int
    role:       str             = Field(..., examples=["user"])
    content:    str
    intent:     Optional[str]   = None
    confidence: Optional[float] = None
    created_at: Optional[str]   = None


class ChatHistoryResponse(BaseModel):
    session_id: str
    messages:   List[ChatHistoryItem] = Field(default_factory=list)
