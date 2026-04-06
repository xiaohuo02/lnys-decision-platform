# -*- coding: utf-8 -*-
"""backend/schemas/ops_copilot.py

OpsCopilotAgent 正式输入输出契约定义。
仅用于 Agent 侧，不对 router 层产生约束。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class OpsCopilotInput(BaseModel):
    """OpsCopilotAgent 输入契约。

    Attributes:
        question:   管理员自然语言问题。
        context:    可选附加上下文（如当前页面、选中 run_id 等）。
        thread_id:  可选会话 thread ID，供多轮追踪使用。
        user_role:  可选调用方角色，用于权限感知回答。
    """

    question: str
    context: Optional[Dict[str, Any]] = None
    thread_id: Optional[str] = None
    user_role: Optional[str] = None


class OpsCopilotOutput(BaseModel):
    """OpsCopilotAgent 输出契约。

    Attributes:
        intent:            识别到的问题意图分类。
        answer:            自然语言回答，不能为空。
        confidence:        意图置信度，0.0–1.0。
        sources:           支撑回答的数据来源摘要列表。
        suggested_actions: 建议用户进行的下一步操作列表（只读建议）。
        fallback_used:     是否触发了降级逻辑。
        error:             若发生异常或降级，记录可读的错误说明；正常时为 None。
    """

    intent: str = "unknown_intent"
    answer: str
    confidence: float = 0.0
    sources: List[str] = Field(default_factory=list)
    suggested_actions: List[str] = Field(default_factory=list)
    fallback_used: bool = False
    error: Optional[str] = None
