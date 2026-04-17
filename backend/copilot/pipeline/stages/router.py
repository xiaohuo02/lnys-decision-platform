# -*- coding: utf-8 -*-
"""backend/copilot/pipeline/stages/router.py — LLM 路由 Stage

对应原 engine.run 第 334-368 行:
  - 权限过滤 + skill 可用性过滤 → available_skills
  - 无 skill → 提示并 should_stop
  - LLM FC 路由 → selected_skill / tool_args / tokens
  - 发 decision_step_event + thinking_event + intent_event + confidence_event

副作用:
  - state.available_skills / selected_skill / tool_args / acc_tokens 被填充
"""
from __future__ import annotations

from typing import AsyncGenerator

from backend.copilot.events import (
    CopilotEvent,
    text_delta_event,
    thinking_event,
    decision_step_event,
    intent_event,
    confidence_event,
)
from backend.copilot.pipeline.base_stage import BaseStage


class RouterStage(BaseStage):
    name = "router"

    async def run(self, state) -> AsyncGenerator[CopilotEvent, None]:
        # 1. 获取可用 Skill
        allowed_skills = await self._engine._permission.get_allowed_skills(
            state.user_id, state.user_role, state.mode
        )
        available_skills = self._engine._registry.get_available_skills(
            state.mode, state.user_role, allowed_skills
        )
        state.available_skills = available_skills

        if not available_skills:
            yield text_delta_event("抱歉，当前没有可用的分析功能。请联系管理员配置权限。")
            state.status = "completed"
            state.should_stop = True
            return

        # 2. 路由决策
        yield decision_step_event(
            "routing", f"正在分析意图，{len(available_skills)} 个 Skill 可用"
        )
        yield thinking_event("start")
        yield thinking_event("delta", "Analyzing user intent...")

        selected_skill, tool_args, route_tokens = await self._engine._route_to_skill(
            state.question, state.context, available_skills
        )
        state.selected_skill = selected_skill
        state.tool_args = tool_args or {}
        state.acc_tokens += route_tokens

        if selected_skill is None:
            # 3a. 无 Skill 命中 → 通用对话路径
            yield thinking_event("delta", "General question, generating response...")
            yield thinking_event("end")
            yield intent_event("general_chat")
            yield confidence_event(0.5)
        else:
            # 3b. Skill 命中 → 继续走 Dedup / SkillExec
            yield thinking_event("delta", f"Routing to {selected_skill.display_name}...")
            yield thinking_event("end")
            yield intent_event(selected_skill.name)
            yield confidence_event(0.9)
