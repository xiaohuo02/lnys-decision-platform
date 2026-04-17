# -*- coding: utf-8 -*-
"""backend/copilot/events.py — Copilot SSE 事件类型定义

基于 AG-UI 协议设计，覆盖完整的 Agent-User 交互生命周期。
"""
from __future__ import annotations

import json
import time
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EventType(str, Enum):
    """SSE 事件类型枚举"""
    # ── Lifecycle ──
    RUN_START       = "run_start"
    RUN_END         = "run_end"
    RUN_ERROR       = "run_error"

    # ── Text Stream ──
    TEXT_DELTA      = "text_delta"

    # ── Thinking Chain ──
    THINKING_START  = "thinking_start"
    THINKING_DELTA  = "thinking_delta"
    THINKING_END    = "thinking_end"

    # ── Tool / Skill Call ──
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_ARGS  = "tool_call_args"
    TOOL_CALL_END   = "tool_call_end"
    TOOL_RESULT     = "tool_result"

    # ── Artifact (GenUI) ──
    ARTIFACT_START  = "artifact_start"
    ARTIFACT_DELTA  = "artifact_delta"
    ARTIFACT_END    = "artifact_end"

    # ── Suggestions ──
    SUGGESTIONS     = "suggestions"

    # ── State ──
    STATE_DELTA     = "state_delta"

    # ── Metadata ──
    INTENT          = "intent"
    CONFIDENCE      = "confidence"
    SOURCES         = "sources"

    # ── Memory ──
    MEMORY_UPDATED  = "memory_updated"

    # ── Decision Chain (治理可视化) ──
    CONTEXT_STATUS  = "context_status"
    SECURITY_CHECK  = "security_check"
    MEMORY_RECALL   = "memory_recall"
    SKILL_CACHE_HIT = "skill_cache_hit"
    DECISION_STEP   = "decision_step"


class CopilotEvent(BaseModel):
    """单个 SSE 事件的结构化表示"""
    type: EventType
    content: Any = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    artifact_type: Optional[str] = None
    items: Optional[List[Dict[str, Any]]] = None
    data: Optional[Dict[str, Any]] = None
    timestamp: float = Field(default_factory=time.time)

    def to_sse(self) -> str:
        """序列化为 SSE 文本格式"""
        payload: Dict[str, Any] = {"type": self.type.value}
        if self.content is not None:
            payload["content"] = self.content
        if self.metadata:
            payload["metadata"] = self.metadata
        if self.artifact_type:
            payload["artifact_type"] = self.artifact_type
        if self.items:
            payload["items"] = self.items
        if self.data:
            payload["data"] = self.data
        payload["ts"] = self.timestamp
        return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


def run_start_event(thread_id: str, mode: str) -> CopilotEvent:
    return CopilotEvent(
        type=EventType.RUN_START,
        metadata={"thread_id": thread_id, "mode": mode},
    )


def run_end_event(thread_id: str, elapsed_ms: int, token_usage: Optional[Dict] = None) -> CopilotEvent:
    return CopilotEvent(
        type=EventType.RUN_END,
        metadata={"thread_id": thread_id, "elapsed_ms": elapsed_ms},
        data={"token_usage": token_usage} if token_usage else None,
    )


def run_error_event(error: str, code: int = 500) -> CopilotEvent:
    return CopilotEvent(
        type=EventType.RUN_ERROR,
        content=error,
        metadata={"code": code},
    )


def text_delta_event(text: str) -> CopilotEvent:
    return CopilotEvent(type=EventType.TEXT_DELTA, content=text)


def thinking_event(phase: str, content: str = "") -> CopilotEvent:
    type_map = {
        "start": EventType.THINKING_START,
        "delta": EventType.THINKING_DELTA,
        "end": EventType.THINKING_END,
    }
    return CopilotEvent(type=type_map[phase], content=content)


def suggestions_event(items: List[Dict[str, Any]]) -> CopilotEvent:
    return CopilotEvent(type=EventType.SUGGESTIONS, items=items)


def intent_event(intent: str) -> CopilotEvent:
    return CopilotEvent(type=EventType.INTENT, content=intent)


def confidence_event(score: float) -> CopilotEvent:
    return CopilotEvent(type=EventType.CONFIDENCE, content=round(score, 2))


def sources_event(items: List[Dict[str, Any]]) -> CopilotEvent:
    return CopilotEvent(type=EventType.SOURCES, items=items)


def context_status_event(
    status: str, tokens: int, max_tokens: int, usage_pct: float,
    compacted: bool = False, tokens_before: int = 0, tokens_after: int = 0,
) -> CopilotEvent:
    return CopilotEvent(
        type=EventType.CONTEXT_STATUS,
        metadata={
            "status": status,
            "tokens": tokens,
            "max_tokens": max_tokens,
            "usage_pct": round(usage_pct, 1),
            "compacted": compacted,
            "tokens_before": tokens_before,
            "tokens_after": tokens_after,
        },
    )


def security_check_event(
    check_type: str, passed: bool, detail: str = "",
    hits: Optional[List[Dict[str, Any]]] = None,
) -> CopilotEvent:
    return CopilotEvent(
        type=EventType.SECURITY_CHECK,
        metadata={
            "check_type": check_type,
            "passed": passed,
            "detail": detail,
        },
        items=hits,
    )


def memory_recall_event(
    layer: str, count: int, keys: Optional[List[str]] = None,
) -> CopilotEvent:
    return CopilotEvent(
        type=EventType.MEMORY_RECALL,
        metadata={"layer": layer, "count": count},
        items=[{"key": k} for k in (keys or [])],
    )


def decision_step_event(step: str, detail: str = "", data: Optional[Dict[str, Any]] = None) -> CopilotEvent:
    return CopilotEvent(
        type=EventType.DECISION_STEP,
        content=step,
        metadata={"detail": detail},
        data=data,
    )
