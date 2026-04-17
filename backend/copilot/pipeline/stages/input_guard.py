# -*- coding: utf-8 -*-
"""backend/copilot/pipeline/stages/input_guard.py — 输入守卫 Stage

对应原 engine.run 第 162-233 行:
  - run_start_event 发射（空问题场景也要发）
  - 空/过短问题快速返回（should_stop）
  - InputGuard.check() → 安全拦截 / 脱敏
  - security_check_event + PII_DETECTED 遥测
  - RUN_STARTED 遥测
"""
from __future__ import annotations

from typing import AsyncGenerator

from backend.copilot.events import (
    CopilotEvent,
    run_start_event,
    text_delta_event,
    security_check_event,
)
from backend.core.telemetry import telemetry, TelemetryEventType
from backend.copilot.pipeline.base_stage import BaseStage


class InputGuardStage(BaseStage):
    name = "input_guard"

    async def run(self, state) -> AsyncGenerator[CopilotEvent, None]:
        # 0. 去空白 + 空问题快速返回
        question = (state.question or "").strip()
        state.question = question

        # 0.1 run_start_event（无论是否空问题都要发，与原 run 语义一致）
        yield run_start_event(state.thread_id, state.mode)

        if len(question) < 1:
            yield text_delta_event("请输入您的问题，我会为您分析。")
            state.status = "completed"
            state.should_stop = True
            return

        # 1. InputGuard 检查
        try:
            from backend.governance.guardrails import input_guard
            guard_result = input_guard.check(question)
            guard_hits = [
                {"rule": h.rule, "severity": h.severity, "message": h.message}
                for h in (guard_result.hits or [])
            ]
            yield security_check_event(
                check_type="input_guard",
                passed=guard_result.passed,
                detail=guard_result.blocked_reason or f"{len(guard_result.hits or [])} checks",
                hits=guard_hits or None,
            )
            if not guard_result.passed:
                yield text_delta_event(f"⚠️ {guard_result.blocked_reason}")
                state.status = "completed"
                state.should_stop = True
                return
            if guard_result.sanitized_text:
                state.question = guard_result.sanitized_text

            # 安全遥测（仪表盘聚合）
            try:
                evt = (
                    TelemetryEventType.SECURITY_CHECK_PASSED
                    if guard_result.passed
                    else TelemetryEventType.SECURITY_CHECK_BLOCKED
                )
                telemetry.emit(evt, {
                    "check_type": "input_guard",
                    "hits_count": len(guard_result.hits or []),
                }, component="InputGuard", thread_id=state.thread_id)
                pii_hits = [h for h in (guard_result.hits or []) if h.rule.startswith("pii_")]
                if pii_hits:
                    telemetry.emit(TelemetryEventType.PII_DETECTED, {
                        "direction": "input",
                        "count": len(pii_hits),
                        "rules": [h.rule for h in pii_hits],
                    }, component="InputGuard", thread_id=state.thread_id)
            except Exception:
                pass
        except Exception as e:
            # guard 内部异常不应阻断主流程
            from backend.copilot.agent_logger import get_agent_logger
            get_agent_logger(state.mode).debug(f"[stage:input_guard] skipped: {e}")

        # 2. RUN_STARTED 遥测（与原 run 顺序保持一致）
        try:
            telemetry.emit(TelemetryEventType.RUN_STARTED, {
                "mode": state.mode, "user_id": state.user_id, "source": state.source,
            }, component="CopilotEngine", thread_id=state.thread_id)
        except Exception:
            pass
