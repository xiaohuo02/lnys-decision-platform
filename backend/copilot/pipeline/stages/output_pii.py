# -*- coding: utf-8 -*-
"""backend/copilot/pipeline/stages/output_pii.py — 输出 PII 扫描 Stage

对应原 engine.run 第 455-479 行:
  - 聚合所有 text_delta 的输出（state.output_text()）
  - 调 input_guard._handle_pii 检测输出中的敏感信息
  - 命中 PII → 发 security_check_event(direction=output) + decision_step + 遥测

注意: 不对输出做修改/脱敏（只标记给前端），保持与原行为一致。
"""
from __future__ import annotations

from typing import AsyncGenerator

from backend.copilot.events import (
    CopilotEvent,
    security_check_event,
    decision_step_event,
)
from backend.core.telemetry import telemetry, TelemetryEventType
from backend.copilot.pipeline.base_stage import BaseStage


class OutputPIIStage(BaseStage):
    name = "output_pii"

    async def run(self, state) -> AsyncGenerator[CopilotEvent, None]:
        try:
            full_output = state.output_text()
            if not full_output:
                return

            from backend.governance.guardrails import input_guard as _ig
            _, pii_hits = _ig._handle_pii(full_output)
            if not pii_hits:
                return

            yield security_check_event(
                check_type="output_pii_scan",
                passed=True,
                detail=f"输出中检测到 {len(pii_hits)} 处 PII 信息",
                hits=[
                    {"rule": h.rule, "severity": h.severity, "message": h.message}
                    for h in pii_hits
                ],
            )
            yield decision_step_event(
                "output_pii", f"输出 PII 检测: {len(pii_hits)} 处已标记"
            )
            try:
                telemetry.emit(TelemetryEventType.PII_DETECTED, {
                    "direction": "output",
                    "count": len(pii_hits),
                    "rules": [h.rule for h in pii_hits],
                }, component="OutputPIIScanner", thread_id=state.thread_id)
            except Exception:
                pass
        except Exception as e:
            from backend.copilot.agent_logger import get_agent_logger
            get_agent_logger(state.mode).debug(
                f"[stage:output_pii] scan skipped: {e}"
            )
