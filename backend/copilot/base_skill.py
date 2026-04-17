# -*- coding: utf-8 -*-
"""backend/copilot/base_skill.py — Copilot Skill 基类

所有 Skill 继承此基类，实现 execute() 异步生成器方法。
Skill 通过 yield CopilotEvent 向引擎输出流式事件。
"""
from __future__ import annotations

import abc
from typing import Any, AsyncGenerator, Dict, Optional, Set

from pydantic import BaseModel, Field

from backend.copilot.events import CopilotEvent


class SkillContext(BaseModel):
    """传递给 Skill 的执行上下文"""
    user_id: str
    user_role: str
    mode: str                                    # "ops" | "biz"
    thread_id: str
    page_context: Dict[str, Any] = Field(default_factory=dict)
    tool_args: Dict[str, Any] = Field(default_factory=dict)      # LLM Function Calling 提取的参数
    thread_history: list = Field(default_factory=list)            # 最近 N 轮对话
    system_prompt: str = ""
    source: str = "web"                          # "web" | "feishu" | "scheduler" | "api"

    class Config:
        arbitrary_types_allowed = True


class BaseCopilotSkill(abc.ABC):
    """Copilot Skill 基类

    子类需要实现：
      - name: str                 — 唯一标识
      - display_name: str         — 展示名
      - description: str          — LLM 用于 Function Calling 路由的描述
      - mode: Set[str]            — 可用模式 {"ops", "biz"} 或子集
      - required_roles: Set[str]  — 允许使用的角色集合
      - parameters_schema: dict   — JSON Schema，LLM 从中提取参数
      - execute()                 — 异步生成器，yield CopilotEvent
    """

    name: str = ""
    display_name: str = ""
    description: str = ""
    mode: Set[str] = {"ops", "biz"}
    required_roles: Set[str] = set()
    parameters_schema: Dict[str, Any] = {}
    summarization_hint: str = ""  # 给 LLM 的 per-skill 摘要约束，_synthesize_answer 时注入

    @abc.abstractmethod
    async def execute(
        self, question: str, context: SkillContext
    ) -> AsyncGenerator[CopilotEvent, None]:
        """执行 Skill，yield 一系列 CopilotEvent

        Args:
            question: 用户原始问题
            context: 执行上下文（含 tool_args、用户信息、页面上下文等）

        Yields:
            CopilotEvent — 每个事件通过 SSE 推送到前端
        """
        yield  # type: ignore  # pragma: no cover

    def to_function_schema(self) -> Dict[str, Any]:
        """转换为 LLM Function Calling 的 tool schema 格式。

        Skill 元数据（name / description / parameters_schema）在运行时为静态值，
        首次构造后缓存于实例 __dict__，后续调用直接复用，
        避免 CopilotEngine._route_to_skill 每请求重新序列化 11 个 schema。
        """
        cached = self.__dict__.get("_cached_schema")
        if cached is not None:
            return cached
        schema = {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema or {
                    "type": "object",
                    "properties": {},
                },
            },
        }
        self.__dict__["_cached_schema"] = schema
        return schema

    def is_available(self, mode: str, user_role: str) -> bool:
        """检查 Skill 在给定模式和角色下是否可用"""
        if mode not in self.mode:
            return False
        if self.required_roles and user_role not in self.required_roles:
            return False
        return True

    def __repr__(self) -> str:
        return f"<Skill:{self.name} mode={self.mode}>"
