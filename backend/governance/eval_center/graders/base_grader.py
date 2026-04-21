# -*- coding: utf-8 -*-
"""backend/governance/eval_center/graders/base_grader.py — 评分器基类

Grader 负责：接收 (input, expected, actual) → 返回 (score, passed, reasoning)。
不负责执行 Agent/Skill，执行由 Runner 完成。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class GraderResult(BaseModel):
    """单个 Grader 的评分结果"""
    grader_name: str
    score: float = Field(ge=0.0, le=1.0)
    passed: bool = False
    reasoning: Optional[str] = None
    thinking: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BaseGrader(ABC):
    """评分器基类

    子类实现 grade() 方法，对 Runner 的输出进行评分。

    Attributes:
        grader_name: 评分器名称（唯一标识）
        pass_threshold: 通过阈值，score >= threshold 即 PASS
    """

    grader_name: str = "base"
    pass_threshold: float = 0.8

    def __init__(self, pass_threshold: float = 0.8, **kwargs):
        self.pass_threshold = pass_threshold

    @abstractmethod
    async def grade(
        self,
        input_json: Dict[str, Any],
        expected_json: Dict[str, Any],
        actual_output: Dict[str, Any],
        evaluator_config: Dict[str, Any] = None,
    ) -> GraderResult:
        """评分

        Args:
            input_json:       原始输入
            expected_json:    期望输出
            actual_output:    Runner 的实际输出
            evaluator_config: evaluator 的 scoring_rules 配置

        Returns:
            GraderResult
        """
        ...

    def _make_result(
        self,
        score: float,
        reasoning: str = "",
        thinking: str = "",
        **extra_meta,
    ) -> GraderResult:
        """构造 GraderResult 的便捷方法"""
        return GraderResult(
            grader_name=self.grader_name,
            score=round(min(max(score, 0.0), 1.0), 4),
            passed=score >= self.pass_threshold,
            reasoning=reasoning or None,
            thinking=thinking or None,
            metadata=extra_meta,
        )
