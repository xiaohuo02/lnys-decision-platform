# -*- coding: utf-8 -*-
"""backend/governance/eval_center/evolution/karpathy_loop.py — ML Agent 爬山法循环

参考 Karpathy autoresearch (2026.03)：
  - 单指标爬山 + 自动回滚
  - 每轮修改参数 → 跑 golden set → 计算指标 → KEEP / DISCARD
  - 评估器不可变，Agent 不能改评估逻辑
"""
from __future__ import annotations

import asyncio
import copy
import json
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from loguru import logger
from pydantic import BaseModel, Field

from backend.governance.eval_center.runners.ml_agent_runner import MLAgentRunner
from backend.governance.eval_center.graders.base_grader import BaseGrader, GraderResult


class LoopIteration(BaseModel):
    """单轮实验结果"""
    iteration: int
    change_desc: str = ""
    params_snapshot: Dict[str, Any] = Field(default_factory=dict)
    metric_name: str = ""
    metric_before: float = 0.0
    metric_after: float = 0.0
    decision: str = "discard"  # keep / discard / crash
    duration_ms: int = 0


class KarpathyLoopResult(BaseModel):
    """爬山法循环总结果"""
    agent_name: str
    metric_name: str
    initial_metric: float = 0.0
    best_metric: float = 0.0
    total_iterations: int = 0
    kept_count: int = 0
    discarded_count: int = 0
    iterations: List[LoopIteration] = Field(default_factory=list)


class KarpathyLoop:
    """ML Agent 指标爬山循环

    Parameters:
        agent:          BaseAgent 实例
        agent_name:     Agent 名称
        golden_cases:   评测用例列表
        graders:        评分器列表
        metric_name:    优化指标名（score/accuracy/precision/recall/f1/...）
        max_iterations: 最大迭代次数
        param_mutator:  参数变异函数 (current_params) → (new_params, change_desc)
        on_progress:    进度回调
    """

    def __init__(
        self,
        agent: Any,
        agent_name: str,
        golden_cases: List[Dict[str, Any]],
        graders: List[BaseGrader],
        metric_name: str = "avg_score",
        max_iterations: int = 20,
        time_budget_s: float = 300.0,
        param_mutator: Optional[Callable] = None,
        on_progress: Optional[Callable] = None,
    ):
        self.agent = agent
        self.agent_name = agent_name
        self.golden_cases = golden_cases
        self.graders = graders
        self.metric_name = metric_name
        self.max_iterations = max_iterations
        self.time_budget_s = time_budget_s
        self.param_mutator = param_mutator
        self.on_progress = on_progress

        self._best_metric: float = float("-inf")
        self._best_params: Dict[str, Any] = {}
        self._current_params: Dict[str, Any] = {}

    def _emit(self, event_type: str, data: dict):
        if self.on_progress:
            try:
                self.on_progress(event_type, data)
            except Exception:
                pass

    async def run(self) -> KarpathyLoopResult:
        """执行爬山法循环"""
        iterations: List[LoopIteration] = []
        loop_start = time.perf_counter()

        # 跑 baseline
        baseline_metric = await self._evaluate_current()
        self._best_metric = baseline_metric
        self._best_params = copy.deepcopy(self._current_params)

        self._emit("eval:loop_metric", {
            "iteration": 0,
            "metric": baseline_metric,
            "decision": "baseline",
            "agent_name": self.agent_name,
        })

        kept = 0
        discarded = 0

        for i in range(1, self.max_iterations + 1):
            elapsed = time.perf_counter() - loop_start
            if elapsed > self.time_budget_s:
                logger.info(f"[KarpathyLoop] {self.agent_name}: 时间预算耗尽 ({elapsed:.0f}s)")
                break

            iter_start = time.perf_counter()

            self._emit("eval:loop_iter_start", {
                "iteration": i,
                "agent_name": self.agent_name,
                "best_metric": self._best_metric,
            })

            # 变异参数
            if self.param_mutator:
                new_params, change_desc = self.param_mutator(copy.deepcopy(self._current_params))
            else:
                new_params = self._current_params
                change_desc = "no mutation (param_mutator not set)"

            old_params = copy.deepcopy(self._current_params)
            self._current_params = new_params
            self._apply_params(new_params)

            # 评测
            try:
                new_metric = await self._evaluate_current()
            except Exception as exc:
                logger.error(f"[KarpathyLoop] iteration {i} crash: {exc}")
                self._current_params = old_params
                self._apply_params(old_params)
                iterations.append(LoopIteration(
                    iteration=i,
                    change_desc=change_desc,
                    params_snapshot=new_params,
                    metric_name=self.metric_name,
                    metric_before=self._best_metric,
                    metric_after=0.0,
                    decision="crash",
                    duration_ms=int((time.perf_counter() - iter_start) * 1000),
                ))
                continue

            # 判定 KEEP / DISCARD
            if new_metric > self._best_metric:
                decision = "keep"
                self._best_metric = new_metric
                self._best_params = copy.deepcopy(new_params)
                kept += 1
                logger.info(
                    f"[KarpathyLoop] {self.agent_name} #{i}: KEEP "
                    f"({self._best_metric:.4f} → {new_metric:.4f})"
                )
            else:
                decision = "discard"
                self._current_params = old_params
                self._apply_params(old_params)
                discarded += 1
                logger.info(
                    f"[KarpathyLoop] {self.agent_name} #{i}: DISCARD "
                    f"({self._best_metric:.4f} vs {new_metric:.4f})"
                )

            iter_ms = int((time.perf_counter() - iter_start) * 1000)

            iteration = LoopIteration(
                iteration=i,
                change_desc=change_desc,
                params_snapshot=new_params,
                metric_name=self.metric_name,
                metric_before=self._best_metric if decision == "discard" else baseline_metric,
                metric_after=new_metric,
                decision=decision,
                duration_ms=iter_ms,
            )
            iterations.append(iteration)

            self._emit("eval:loop_iter_end", {
                "iteration": i,
                "metric_before": iteration.metric_before,
                "metric_after": new_metric,
                "decision": decision,
                "duration_ms": iter_ms,
                "best_metric": self._best_metric,
            })

        # 确保最终使用最优参数
        self._apply_params(self._best_params)

        result = KarpathyLoopResult(
            agent_name=self.agent_name,
            metric_name=self.metric_name,
            initial_metric=baseline_metric,
            best_metric=self._best_metric,
            total_iterations=len(iterations),
            kept_count=kept,
            discarded_count=discarded,
            iterations=iterations,
        )

        self._emit("eval:loop_complete", {
            "agent_name": self.agent_name,
            "initial_metric": baseline_metric,
            "best_metric": self._best_metric,
            "total_iterations": len(iterations),
            "kept": kept,
            "discarded": discarded,
        })

        return result

    async def _evaluate_current(self) -> float:
        """用当前参数在 golden set 上跑一遍，返回聚合指标"""
        runner = MLAgentRunner(
            agent=self.agent,
            agent_name=self.agent_name,
        )

        scores = []
        for case in self.golden_cases:
            input_json = case.get("input_json", case)
            expected_json = case.get("expected_json", {})

            if isinstance(input_json, str):
                input_json = json.loads(input_json)
            if isinstance(expected_json, str):
                expected_json = json.loads(expected_json)

            run_result = await runner.run(input_json)
            if not run_result.success:
                scores.append(0.0)
                continue

            grader_tasks = [
                g.grade(input_json, expected_json, run_result.actual_output, {})
                for g in self.graders
            ]
            grader_results = await asyncio.gather(*grader_tasks, return_exceptions=True)
            valid_scores = [
                gr.score for gr in grader_results
                if isinstance(gr, GraderResult)
            ]
            scores.append(sum(valid_scores) / len(valid_scores) if valid_scores else 0.0)

        return sum(scores) / len(scores) if scores else 0.0

    def _apply_params(self, params: Dict[str, Any]) -> None:
        """将参数应用到 Agent 实例"""
        if not params or self.agent is None:
            return
        for key, value in params.items():
            if hasattr(self.agent, key):
                setattr(self.agent, key, value)
