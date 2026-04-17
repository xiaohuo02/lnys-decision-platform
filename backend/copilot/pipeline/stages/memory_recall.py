# -*- coding: utf-8 -*-
"""backend/copilot/pipeline/stages/memory_recall.py — 记忆召回 Stage

对应原 engine.run 第 313-332 行:
  - 发 memory_recall_event（L1 redis / L2 memory / L3 rules）让前端展示
  - MEMORY_RECALLED 遥测
"""
from __future__ import annotations

from typing import AsyncGenerator

from backend.copilot.events import CopilotEvent, memory_recall_event
from backend.core.telemetry import telemetry, TelemetryEventType
from backend.copilot.pipeline.base_stage import BaseStage


class MemoryRecallStage(BaseStage):
    name = "memory_recall"

    async def run(self, state) -> AsyncGenerator[CopilotEvent, None]:
        try:
            context = state.context
            layers_used = []
            if getattr(context, "redis_history_count", 0) > 0:
                layers_used.append(("L1_redis", context.redis_history_count))
            if getattr(context, "memory_count", 0) > 0:
                layers_used.append(("L2_memory", context.memory_count))
            if getattr(context, "rules_count", 0) > 0:
                layers_used.append(("L3_rules", context.rules_count))

            for layer, count in layers_used:
                yield memory_recall_event(layer=layer, count=count)
                try:
                    telemetry.emit(TelemetryEventType.MEMORY_RECALLED, {
                        "layer": layer, "count": count,
                    }, component="CopilotEngine", thread_id=state.thread_id)
                except Exception:
                    pass
        except Exception:
            # 记忆召回事件是观测用，失败不影响主流程
            pass
