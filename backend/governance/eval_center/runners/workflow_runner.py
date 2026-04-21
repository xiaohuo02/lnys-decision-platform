# -*- coding: utf-8 -*-
"""backend/governance/eval_center/runners/workflow_runner.py — Workflow 端到端执行器

通过 SupervisorAgent 路由 → Orchestrator → DAG 执行完整 workflow。
用于评测端到端任务完成率和路由准确性。
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from loguru import logger

from backend.governance.eval_center.runners.base_runner import BaseRunner, RunnerResult


class WorkflowRunner(BaseRunner):
    """Workflow 端到端评测执行器

    Parameters:
        supervisor_agent: SupervisorAgent 实例
        timeout: 完整 workflow 超时秒数（默认 120s，workflow 通常较慢）
    """

    runner_type = "workflow"

    def __init__(
        self,
        supervisor_agent: Any = None,
        timeout: float = 120.0,
    ):
        self.supervisor_agent = supervisor_agent
        self.timeout = timeout

    async def execute(self, input_json: Dict[str, Any], **kwargs) -> RunnerResult:
        if self.supervisor_agent is None:
            return RunnerResult(
                error="SupervisorAgent 未就绪",
            )

        question = input_json.get("question", "")
        if not question:
            return RunnerResult(error="input_json 缺少 'question' 字段")

        try:
            result = await asyncio.wait_for(
                self.supervisor_agent.run({"question": question, **input_json}),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            return RunnerResult(
                error=f"Workflow 超时（{self.timeout}s）",
                metadata={"timeout": self.timeout},
            )
        except Exception as exc:
            logger.error(f"[WorkflowRunner] {type(exc).__name__}: {exc}")
            return RunnerResult(
                error=f"Workflow 执行异常: {type(exc).__name__}: {exc}",
            )

        if not isinstance(result, dict):
            return RunnerResult(
                error=f"Workflow 返回非 dict: {type(result).__name__}",
            )

        routed_workflow = result.get("workflow_name", result.get("routed_to", "unknown"))
        return RunnerResult(
            actual_output=result,
            metadata={
                "routed_workflow": routed_workflow,
                "steps_count": len(result.get("steps", [])),
            },
        )
