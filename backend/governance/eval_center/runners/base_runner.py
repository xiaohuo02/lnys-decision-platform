# -*- coding: utf-8 -*-
"""backend/governance/eval_center/runners/base_runner.py — 评测执行器基类

Runner 负责：接收一条 eval_case → 调用真实目标（Agent / Skill / Workflow）→ 返回实际输出。
不负责评分，评分由 Grader 完成。
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class RunnerResult(BaseModel):
    """Runner 执行结果"""
    actual_output: Dict[str, Any] = Field(default_factory=dict)
    latency_ms: int = 0
    tokens_used: int = 0
    cost: float = 0.0
    error: Optional[str] = None
    trace_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.error is None and bool(self.actual_output)


class BaseRunner(ABC):
    """评测执行器基类

    子类实现 execute()，BaseRunner 提供统一的计时和错误处理。
    """

    runner_type: str = "base"

    async def run(self, input_json: Dict[str, Any], **kwargs) -> RunnerResult:
        """统一入口：计时 + 错误捕获"""
        t0 = time.perf_counter()
        try:
            result = await self.execute(input_json, **kwargs)
            result.latency_ms = int((time.perf_counter() - t0) * 1000)
            return result
        except Exception as exc:
            return RunnerResult(
                error=f"{type(exc).__name__}: {exc}",
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )

    @abstractmethod
    async def execute(self, input_json: Dict[str, Any], **kwargs) -> RunnerResult:
        """子类实现：执行真实调用并返回 RunnerResult"""
        ...
