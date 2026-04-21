# -*- coding: utf-8 -*-
"""backend/governance/eval_center/runners/ml_agent_runner.py — ML Agent 执行器

通过 AgentGateway.call() 调用真实的 BaseAgent.run()，
兼容所有 7 个 ML Agent（customer/forecast/fraud/sentiment/inventory/association/openclaw）。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from loguru import logger

from backend.agents.gateway import AgentGateway
from backend.governance.eval_center.runners.base_runner import BaseRunner, RunnerResult


class MLAgentRunner(BaseRunner):
    """ML Agent 评测执行器

    Parameters:
        agent:      BaseAgent 实例（从 app.state 或 agent_registry 获取）
        agent_name: Agent 名称（用于日志）
        timeout:    调用超时秒数
    """

    runner_type = "ml_agent"

    def __init__(
        self,
        agent: Any,
        agent_name: str = "unknown",
        timeout: float = 30.0,
    ):
        self.agent = agent
        self.agent_name = agent_name
        self.timeout = timeout

    async def execute(self, input_json: Dict[str, Any], **kwargs) -> RunnerResult:
        if self.agent is None:
            return RunnerResult(
                error=f"Agent '{self.agent_name}' 未就绪（None）",
                metadata={"agent_name": self.agent_name},
            )

        result = await AgentGateway.call(
            self.agent,
            input_json,
            agent_name=self.agent_name,
            timeout=self.timeout,
        )

        if result is None:
            return RunnerResult(
                error=f"Agent '{self.agent_name}' 返回 None（超时/异常/空结果）",
                metadata={"agent_name": self.agent_name},
            )

        logger.debug(f"[MLAgentRunner] {self.agent_name}: 执行成功")
        return RunnerResult(
            actual_output=result,
            metadata={"agent_name": self.agent_name},
        )
