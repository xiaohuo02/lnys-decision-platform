# -*- coding: utf-8 -*-
"""backend/copilot/pipeline/stages/persist.py — 持久化 + 生命周期结束 Stage (finalize)

对应原 engine.run 第 481-544 行（包括 try 成功分支 + except 失败分支）:
  - 发 RUN_COMPLETED 或 RUN_FAILED + ERROR_CLASSIFIED 遥测
  - 发 run_end_event
  - 异步写 runs 表（fire-and-forget）

职责边界:
  - 作为 finalize Stage 放到 Pipeline 的 finalize_stages 列表，
    无论 should_stop / terminal_error 都会被执行
  - 不做任何业务判断，只根据 state.terminal_error / status 做持久化
  - state.terminal_error != None → 按失败路径走；否则成功
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from backend.copilot.events import (
    CopilotEvent,
    run_end_event,
    run_error_event,
)
from backend.core.telemetry import telemetry, TelemetryEventType
from backend.copilot.pipeline.base_stage import BaseStage


class PersistStage(BaseStage):
    name = "persist"

    async def run(self, state) -> AsyncGenerator[CopilotEvent, None]:
        elapsed_ms = state.elapsed_ms()
        from backend.copilot.agent_logger import get_agent_logger
        agent_log = get_agent_logger(state.mode)

        if state.terminal_error:
            # 失败路径
            error_msg = f"处理失败: {state.terminal_error[:120]}"
            agent_log.error(f"[stage:persist] error: {state.terminal_error}")

            try:
                telemetry.emit(TelemetryEventType.RUN_FAILED, {
                    "mode": state.mode,
                    "error": state.terminal_error[:200],
                    "latency_ms": elapsed_ms,
                }, component="CopilotEngine", thread_id=state.thread_id)
                telemetry.emit(TelemetryEventType.ERROR_CLASSIFIED, {
                    "error_type": "PipelineError",
                    "error_message": state.terminal_error[:200],
                    "severity": "high",
                }, component="CopilotEngine", thread_id=state.thread_id)
            except Exception:
                pass

            yield run_error_event(error_msg)
            yield run_end_event(state.thread_id, elapsed_ms)

            self._schedule_write(state, "failed", elapsed_ms)
            return

        # 成功路径
        agent_log.info(
            f"[stage:persist] done elapsed={elapsed_ms}ms thread={state.thread_id}"
        )
        try:
            telemetry.emit(TelemetryEventType.RUN_COMPLETED, {
                "mode": state.mode,
                "skill": state.skill_name_or_default(),
                "latency_ms": elapsed_ms,
                "tokens": state.acc_tokens,
                "stage_timings": dict(state.stage_timings),
            }, component="CopilotEngine", thread_id=state.thread_id)
        except Exception:
            pass

        yield run_end_event(state.thread_id, elapsed_ms)

        self._schedule_write(state, "completed", elapsed_ms)

    def _schedule_write(self, state, status: str, elapsed_ms: int) -> None:
        """异步写 runs 表（fire-and-forget，不阻塞事件循环）。"""
        output_summary = state.output_text()[:500]
        try:
            asyncio.ensure_future(asyncio.to_thread(
                self._engine._write_copilot_run,
                user_id=state.user_id,
                mode=state.mode,
                thread_id=state.thread_id,
                skill_name=state.skill_name_or_default(),
                input_summary=state.question[:500],
                output_summary=output_summary,
                status=status,
                latency_ms=elapsed_ms,
                error_message=(state.terminal_error or "")[:500],
                total_tokens=state.acc_tokens,
                total_cost=state.acc_cost,
            ))
        except RuntimeError:
            # 没有 running loop（测试场景），降级为直接同步写
            try:
                self._engine._write_copilot_run(
                    user_id=state.user_id,
                    mode=state.mode,
                    thread_id=state.thread_id,
                    skill_name=state.skill_name_or_default(),
                    input_summary=state.question[:500],
                    output_summary=output_summary,
                    status=status,
                    latency_ms=elapsed_ms,
                    error_message=(state.terminal_error or "")[:500],
                    total_tokens=state.acc_tokens,
                    total_cost=state.acc_cost,
                )
            except Exception:
                pass
