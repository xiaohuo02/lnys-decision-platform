# -*- coding: utf-8 -*-
"""backend/copilot/pipeline/stages/token_governor.py — 上下文治理 Stage

对应原 engine.run 第 249-311 行:
  - context_monitor.evaluate() → HEALTHY / NEEDS_COMPACT / CIRCUIT_BREAK
  - NEEDS_COMPACT → 触发 compact_messages, 替换 thread_history
  - CIRCUIT_BREAK → 发提示但不停止运行（保持原行为）
  - context_status_event 让前端展示 token 使用情况

副作用:
  - state.context.thread_history 可能被压缩后替换
"""
from __future__ import annotations

from typing import AsyncGenerator

from backend.copilot.events import CopilotEvent, context_status_event, text_delta_event
from backend.core.telemetry import telemetry, TelemetryEventType
from backend.copilot.pipeline.base_stage import BaseStage


class TokenGovernorStage(BaseStage):
    name = "token_governor"

    async def run(self, state) -> AsyncGenerator[CopilotEvent, None]:
        try:
            from backend.core.context_monitor import context_monitor, ContextStatus
            from backend.core.token_counter import token_counter

            ctx_tokens = token_counter.estimate_messages(state.context.thread_history)
            ctx_status = context_monitor.evaluate(ctx_tokens, state.thread_id)
            max_tokens = context_monitor.budget.max_tokens
            usage_pct = (ctx_tokens / max_tokens * 100) if max_tokens > 0 else 0

            telemetry.emit(TelemetryEventType.CONTEXT_EVALUATED, {
                "tokens": ctx_tokens,
                "status": ctx_status.value,
                "max_tokens": max_tokens,
            }, component="CopilotEngine", thread_id=state.thread_id)

            if ctx_status == ContextStatus.NEEDS_COMPACT:
                from backend.copilot.agent_logger import get_agent_logger
                get_agent_logger(state.mode).info(
                    f"[stage:token_governor] NEEDS_COMPACT tokens={ctx_tokens} thread={state.thread_id}"
                )
                telemetry.emit(TelemetryEventType.COMPACT_TRIGGERED, {
                    "tokens_before": ctx_tokens,
                    "thread_id": state.thread_id,
                }, component="CopilotEngine", thread_id=state.thread_id)

                result = await context_monitor.compact_messages(
                    state.context.thread_history, thread_id=state.thread_id
                )
                if result.is_effective:
                    state.context.thread_history = result.compacted_messages
                    telemetry.emit(TelemetryEventType.COMPACT_COMPLETED, {
                        "tokens_before": result.tokens_before,
                        "tokens_after": result.tokens_after,
                        "messages_before": result.messages_before,
                        "messages_after": result.messages_after,
                        "duration_ms": result.duration_ms,
                    }, component="CopilotEngine", thread_id=state.thread_id)
                    yield context_status_event(
                        status="compacted",
                        tokens=result.tokens_after,
                        max_tokens=max_tokens,
                        usage_pct=result.tokens_after / max_tokens * 100 if max_tokens else 0,
                        compacted=True,
                        tokens_before=result.tokens_before,
                        tokens_after=result.tokens_after,
                    )
                else:
                    yield context_status_event(
                        status=ctx_status.value,
                        tokens=ctx_tokens,
                        max_tokens=max_tokens,
                        usage_pct=usage_pct,
                    )
            elif ctx_status == ContextStatus.CIRCUIT_BREAK:
                from backend.copilot.agent_logger import get_agent_logger
                get_agent_logger(state.mode).error(
                    f"[stage:token_governor] CIRCUIT_BREAK thread={state.thread_id} tokens={ctx_tokens}"
                )
                yield context_status_event(
                    status="circuit_break",
                    tokens=ctx_tokens,
                    max_tokens=max_tokens,
                    usage_pct=usage_pct,
                )
                yield text_delta_event("⚠️ 当前对话过长，建议开启新对话。")
                # 注: 保持与原 run 一致，CIRCUIT_BREAK 不阻断，仅提示
            else:
                yield context_status_event(
                    status="healthy",
                    tokens=ctx_tokens,
                    max_tokens=max_tokens,
                    usage_pct=usage_pct,
                )
        except Exception as e:
            from backend.copilot.agent_logger import get_agent_logger
            get_agent_logger(state.mode).warning(
                f"[stage:token_governor] failed (non-fatal): {e}"
            )
