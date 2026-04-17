# -*- coding: utf-8 -*-
"""backend/copilot/pipeline/stages/context.py — 上下文构建 Stage

对应原 engine.run 第 235-247 行:
  - ContextManager.build() → SkillContext (含 system_prompt / thread_history / memories / rules)
  - 保存当前用户消息到 Redis thread_history

副作用:
  - state.context 被填充
  - Redis 多一条 user 消息
"""
from __future__ import annotations

from typing import AsyncGenerator

from backend.copilot.events import CopilotEvent
from backend.copilot.pipeline.base_stage import BaseStage


class ContextStage(BaseStage):
    name = "context"

    async def run(self, state) -> AsyncGenerator[CopilotEvent, None]:
        state.context = await self._engine._context_mgr.build(
            thread_id=state.thread_id,
            user_id=state.user_id,
            user_role=state.user_role,
            mode=state.mode,
            page_context=state.page_context,
            source=state.source,
        )
        # 保存用户消息到 Redis（注意: 用 sanitized 后的 question）
        await self._engine._context_mgr.save_to_thread_history(
            state.thread_id, "user", state.question
        )
        # 此 Stage 不产出前端事件
        return
        yield  # pragma: no cover — 让类型检查识别为 AsyncGenerator
