# -*- coding: utf-8 -*-
"""backend/governance/eval_center/runners/supervisor_runner.py — Supervisor 路由测试执行器

专注于测试 SupervisorAgent 的路由准确性：
  - 输入一条用户问题
  - 验证 Supervisor 是否路由到正确的 workflow
  - 不执行完整 workflow，只验证路由决策
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from loguru import logger

from backend.governance.eval_center.runners.base_runner import BaseRunner, RunnerResult


class SupervisorRunner(BaseRunner):
    """Supervisor 路由测试执行器

    与 WorkflowRunner 的区别：
      - WorkflowRunner: 执行完整 workflow（SupervisorAgent → Orchestrator → DAG）
      - SupervisorRunner: 只测试路由决策（SupervisorAgent.classify / route）

    Parameters:
        supervisor_agent: SupervisorAgent 实例
        timeout: 路由超时秒数（默认 30s，路由比完整执行快）
    """

    runner_type = "supervisor"

    def __init__(
        self,
        supervisor_agent: Any = None,
        timeout: float = 30.0,
    ):
        self.supervisor_agent = supervisor_agent
        self.timeout = timeout

    async def execute(self, input_json: Dict[str, Any], **kwargs) -> RunnerResult:
        if self.supervisor_agent is None:
            return RunnerResult(error="SupervisorAgent 未就绪")

        question = input_json.get("question", "")
        if not question:
            return RunnerResult(error="input_json 缺少 'question' 字段")

        try:
            # 优先使用 classify/route 方法（只做路由决策）
            if hasattr(self.supervisor_agent, "classify"):
                result = await asyncio.wait_for(
                    self.supervisor_agent.classify({"question": question, **input_json}),
                    timeout=self.timeout,
                )
            elif hasattr(self.supervisor_agent, "route"):
                result = await asyncio.wait_for(
                    self.supervisor_agent.route({"question": question, **input_json}),
                    timeout=self.timeout,
                )
            else:
                # 降级到完整 run，但只取路由结果
                result = await asyncio.wait_for(
                    self.supervisor_agent.run({"question": question, **input_json}),
                    timeout=self.timeout,
                )
        except asyncio.TimeoutError:
            return RunnerResult(
                error=f"Supervisor 路由超时（{self.timeout}s）",
                metadata={"timeout": self.timeout},
            )
        except Exception as exc:
            logger.error(f"[SupervisorRunner] {type(exc).__name__}: {exc}")
            return RunnerResult(
                error=f"Supervisor 路由异常: {type(exc).__name__}: {exc}",
            )

        if not isinstance(result, dict):
            result = {"routed_to": str(result)}

        routed_to = result.get("workflow_name", result.get("routed_to", "unknown"))
        logger.debug(f"[SupervisorRunner] 路由结果: {routed_to}")

        return RunnerResult(
            actual_output=result,
            metadata={
                "routed_to": routed_to,
                "routing_only": True,
            },
        )
