# -*- coding: utf-8 -*-
"""backend/copilot/pipeline/stages/dedup.py — 重复调用检测 Stage

对应原 engine.run 第 370-393 行:
  - 对 selected_skill + tool_args 做去重检查
  - 命中缓存 → 发 SKILL_CACHE_HIT + decision_step, 设置 state.from_cache=True, skill_data
  - 未命中 → 不发事件，SkillExecStage 会真正跑 skill

注意: selected_skill is None（general_chat）时跳过 dedup。
"""
from __future__ import annotations

from typing import AsyncGenerator

from backend.copilot.events import (
    CopilotEvent,
    EventType,
    decision_step_event,
)
from backend.copilot.pipeline.base_stage import BaseStage


class DedupStage(BaseStage):
    name = "dedup"

    async def run(self, state) -> AsyncGenerator[CopilotEvent, None]:
        if state.selected_skill is None:
            return
            yield  # pragma: no cover

        is_dup, cached = await self._engine._dedup.check_and_cache(
            state.selected_skill.name, state.tool_args
        )
        if is_dup and cached is not None:
            yield CopilotEvent(
                type=EventType.SKILL_CACHE_HIT,
                metadata={
                    "skill": state.selected_skill.name,
                    "reason": "连续重复调用，返回缓存结果",
                },
            )
            yield decision_step_event(
                "cache_hit",
                f"{state.selected_skill.display_name} 结果命中缓存",
            )
            state.skill_data = cached
            state.from_cache = True
