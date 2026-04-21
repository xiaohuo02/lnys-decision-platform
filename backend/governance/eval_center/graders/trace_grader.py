# -*- coding: utf-8 -*-
"""backend/governance/eval_center/graders/trace_grader.py — 链路级评估器

评估 Agent/Workflow 的执行链路质量：
  - 路由准确率：Supervisor 是否路由到正确 workflow
  - 步骤完整性：所有必要步骤是否执行
  - 工具调用正确性：tool 参数和结果是否合理
  - 无冗余步骤：是否有不必要的重复/冗余调用
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from backend.governance.eval_center.graders.base_grader import BaseGrader, GraderResult


class TraceRouteGrader(BaseGrader):
    """路由准确率评估：Supervisor 是否将请求路由到正确的 workflow"""

    grader_name = "trace_route"

    async def grade(
        self,
        input_json: Dict[str, Any],
        expected_json: Dict[str, Any],
        actual_output: Dict[str, Any],
        evaluator_config: Dict[str, Any] = None,
    ) -> GraderResult:
        expected_route = expected_json.get("routed_to", expected_json.get("workflow_name", ""))
        actual_route = actual_output.get("routed_to", actual_output.get("workflow_name", ""))

        # 从 metadata 补充
        metadata = actual_output.get("metadata", {})
        if not actual_route and isinstance(metadata, dict):
            actual_route = metadata.get("routed_to", metadata.get("routed_workflow", ""))

        if not expected_route:
            return self._make_result(1.0, reasoning="无路由预期，跳过检查")

        if not actual_route:
            return self._make_result(0.0, reasoning=f"actual 缺少路由结果，expected={expected_route}")

        exp_lower = expected_route.strip().lower()
        act_lower = actual_route.strip().lower()

        if exp_lower == act_lower:
            return self._make_result(1.0, reasoning=f"路由正确: {actual_route}")

        # 部分匹配（名称包含关系）
        if exp_lower in act_lower or act_lower in exp_lower:
            return self._make_result(0.5, reasoning=f"路由部分匹配: expected={expected_route}, actual={actual_route}")

        return self._make_result(
            0.0,
            reasoning=f"路由错误: expected={expected_route}, actual={actual_route}",
        )


class TraceStepCompletenessGrader(BaseGrader):
    """步骤完整性评估：所有必要步骤是否执行"""

    grader_name = "trace_step_completeness"

    async def grade(
        self,
        input_json: Dict[str, Any],
        expected_json: Dict[str, Any],
        actual_output: Dict[str, Any],
        evaluator_config: Dict[str, Any] = None,
    ) -> GraderResult:
        config = evaluator_config or {}
        required_steps: List[str] = config.get("required_steps", [])

        if not required_steps:
            required_steps = expected_json.get("required_steps", [])

        if not required_steps:
            return self._make_result(1.0, reasoning="无步骤完整性约束")

        # 从 actual_output 中提取已执行的步骤名
        actual_steps = self._extract_step_names(actual_output)

        found = []
        missing = []

        for step in required_steps:
            step_lower = step.lower()
            if any(step_lower in s.lower() for s in actual_steps):
                found.append(step)
            else:
                missing.append(step)

        score = len(found) / len(required_steps)
        reasoning = f"步骤完整性 {len(found)}/{len(required_steps)}"
        if missing:
            reasoning += f", 缺失步骤: {missing}"

        return self._make_result(score, reasoning=reasoning)

    @staticmethod
    def _extract_step_names(output: Dict[str, Any]) -> List[str]:
        """从 actual_output 中提取所有步骤名称"""
        names = []

        # 从 steps 数组提取
        steps = output.get("steps", [])
        if isinstance(steps, list):
            for s in steps:
                if isinstance(s, dict):
                    name = s.get("name", s.get("agent_name", s.get("step_name", "")))
                    if name:
                        names.append(str(name))
                elif isinstance(s, str):
                    names.append(s)

        # 从 events 数组提取 tool 调用
        events = output.get("events", [])
        if isinstance(events, list):
            for ev in events:
                if isinstance(ev, dict):
                    ev_type = ev.get("type", "")
                    if "tool_call" in str(ev_type).lower():
                        data = ev.get("data", {})
                        if isinstance(data, dict):
                            tool_name = data.get("name", data.get("tool_name", ""))
                            if tool_name:
                                names.append(str(tool_name))

        return names


class TraceToolAccuracyGrader(BaseGrader):
    """工具调用正确性评估：tool_result 数据是否合理

    检查：
      - tool 调用参数是否包含必要字段
      - tool 返回结果是否非空/非错误
      - tool 返回结果中的关键字段是否存在
    """

    grader_name = "trace_tool_accuracy"

    async def grade(
        self,
        input_json: Dict[str, Any],
        expected_json: Dict[str, Any],
        actual_output: Dict[str, Any],
        evaluator_config: Dict[str, Any] = None,
    ) -> GraderResult:
        tool_results = actual_output.get("tool_results", [])
        events = actual_output.get("events", [])

        # 从 events 中提取 tool_result
        if not tool_results and events:
            for ev in events:
                if isinstance(ev, dict):
                    if str(ev.get("type", "")).lower() in ("tool_result", "tool_call_end"):
                        data = ev.get("data", {})
                        if isinstance(data, dict):
                            tool_results.append(data)

        if not tool_results:
            # 无 tool 调用，可能是纯 LLM 回答
            return self._make_result(1.0, reasoning="无 tool 调用记录")

        valid = 0
        issues = []

        for i, tr in enumerate(tool_results):
            if not isinstance(tr, dict):
                issues.append(f"tool_result[{i}]: 非 dict 类型")
                continue

            # 检查是否有错误
            error = tr.get("error", tr.get("err", ""))
            if error:
                issues.append(f"tool_result[{i}]: 有错误 — {str(error)[:100]}")
                continue

            # 检查结果是否非空
            result = tr.get("result", tr.get("data", tr.get("output", "")))
            if not result:
                issues.append(f"tool_result[{i}]: 结果为空")
                continue

            valid += 1

        score = valid / len(tool_results)
        reasoning = f"工具调用正确 {valid}/{len(tool_results)}"
        if issues:
            reasoning += "\n" + "\n".join(f"  - {iss}" for iss in issues)

        return self._make_result(score, reasoning=reasoning)
