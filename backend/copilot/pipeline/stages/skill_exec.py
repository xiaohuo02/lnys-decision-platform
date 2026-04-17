# -*- coding: utf-8 -*-
"""backend/copilot/pipeline/stages/skill_exec.py — Skill 执行 + 综合回答 Stage

整合原 engine.run 第 353-450 行的三个分支:
  A) selected_skill is None → general_chat（无 synthesize）
  B) from_cache=True → 跳过 tool_call, 直接 synthesize(cached_data)
  C) 正常 → TOOL_CALL_START → skill.execute → TOOL_CALL_END → synthesize

所有 text_delta 事件的 content 会被追加到 state.output_parts, 供 OutputPIIStage 和 PersistStage 使用。
Skill 执行带 60s 超时保护（与原代码一致）。
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from backend.copilot.events import (
    CopilotEvent,
    EventType,
    decision_step_event,
    text_delta_event,
)
from backend.copilot.pipeline.base_stage import BaseStage
from backend.copilot.agent_logger import SkillCallTracer
from backend.core.telemetry import telemetry, TelemetryEventType


class SkillExecStage(BaseStage):
    name = "skill_exec"

    async def run(self, state) -> AsyncGenerator[CopilotEvent, None]:
        # A) 通用对话
        if state.selected_skill is None:
            async for event in self._engine._general_chat(state.question, state.context):
                yield event
                if event.type == EventType.TEXT_DELTA and event.content:
                    state.output_parts.append(str(event.content))
            return

        skill = state.selected_skill

        # B) 缓存命中: 直接跑 synthesize（§3.2 abstain 短路）
        if state.from_cache and state.skill_data:
            if not state.skill_data.get("abstain"):
                async for event in self._engine._synthesize_answer(
                    state.question, state.context, skill, state.skill_data
                ):
                    yield event
                    if event.type == EventType.TEXT_DELTA and event.content:
                        state.output_parts.append(str(event.content))
            else:
                yield decision_step_event("abstain", f"知识库拒答(cache): {state.skill_data.get('reason', 'unknown')}")
            return

        # C) 正常路径: 跑 skill + synthesize
        yield decision_step_event("skill_exec", f"执行 {skill.display_name}")
        state.context.tool_args = state.tool_args
        tracer = SkillCallTracer(state.mode, skill.name, state.user_id, state.thread_id)
        tracer.start()

        yield CopilotEvent(
            type=EventType.TOOL_CALL_START,
            metadata={"skill": skill.name, "display_name": skill.display_name},
        )

        skill_data = None
        try:
            async with asyncio.timeout(60):
                async for event in skill.execute(state.question, state.context):
                    if event.type == EventType.TOOL_RESULT:
                        skill_data = event.data
                    yield event
                    tracer.log_event(event.type.value)

            yield CopilotEvent(type=EventType.TOOL_CALL_END, metadata={"skill": skill.name})
            tracer.end(success=True)

            # 缓存 Skill 结果用于去重
            if skill_data:
                await self._engine._dedup.check_and_cache(
                    skill.name, state.tool_args, result=skill_data
                )

            try:
                telemetry.emit(TelemetryEventType.SKILL_EXECUTED, {
                    "skill": skill.name,
                    "display_name": skill.display_name,
                    "has_data": skill_data is not None,
                }, component="CopilotEngine", thread_id=state.thread_id)
            except Exception:
                pass

            state.skill_executed = True
            state.skill_data = skill_data
        except asyncio.TimeoutError:
            tracer.end(success=False, error="timeout")
            from backend.copilot.agent_logger import get_agent_logger
            get_agent_logger(state.mode).error(
                f"[stage:skill_exec] timeout skill={skill.name}"
            )
            yield CopilotEvent(
                type=EventType.TOOL_CALL_END,
                metadata={"skill": skill.name, "error": "timeout"},
            )
            yield text_delta_event(
                f"\n\n抱歉，{skill.display_name} 执行超时，请稍后重试。"
            )
            state.output_parts.append(f"\n\n抱歉，{skill.display_name} 执行超时，请稍后重试。")
        except Exception as e:
            tracer.end(success=False, error=str(e))
            from backend.copilot.agent_logger import get_agent_logger
            get_agent_logger(state.mode).error(
                f"[stage:skill_exec] error skill={skill.name} err={e}"
            )
            yield CopilotEvent(
                type=EventType.TOOL_CALL_END,
                metadata={"skill": skill.name, "error": str(e)},
            )
            # 注: 与原代码保持一致，skill 执行异常不向上抛，继续 synthesize 分支（此时 skill_data=None）

        # 综合回答（仅当有数据且非拒答时：§3.2 abstain 短路）
        if state.skill_data and not state.skill_data.get("abstain"):
            yield decision_step_event("synthesize", "LLM 综合分析中")
            async for event in self._engine._synthesize_answer(
                state.question, state.context, skill, state.skill_data
            ):
                yield event
                if event.type == EventType.TEXT_DELTA and event.content:
                    state.output_parts.append(str(event.content))
        elif state.skill_data and state.skill_data.get("abstain"):
            yield decision_step_event("abstain", f"知识库拒答: {state.skill_data.get('reason', 'unknown')}")
