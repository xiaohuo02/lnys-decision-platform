# -*- coding: utf-8 -*-
"""backend/governance/eval_center/graders/llm_judge_grader.py — LLM-as-Judge 评分器

利用 qwen3.5-plus-2026-02-15 的 thinking mode 进行多维度综合评分。
支持 thinking tokens 流式输出（通过 SSE 推送到前端）。
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from loguru import logger

from backend.governance.eval_center.graders.base_grader import BaseGrader, GraderResult

JUDGE_SYSTEM_PROMPT = """你是一个严格的 AI 输出质量评审员。你需要根据以下维度对 AI 的回答进行评分。

## 评估维度（各 0-1 分）
1. **Groundedness（忠实性）**：回答是否基于提供的数据/tool_result，有无编造数字或事实
2. **Task Completion（任务完成度）**：是否真正回答了用户的问题，是否完整
3. **Answer Quality（回答质量）**：相关性、准确性、简洁度、可读性
4. **Tool Consistency（工具一致性）**：tool_result 数据与最终回答中的数字/结论是否一致

## 评分规则
- 每个维度 0.0-1.0，精确到小数点后 2 位
- 最终分数 = 四个维度的算术平均
- verdict: 最终分数 >= 0.8 为 PASS，否则 FAIL

## 输出格式（严格 JSON）
```json
{
  "groundedness": 0.85,
  "task_completion": 0.90,
  "answer_quality": 0.80,
  "tool_consistency": 0.95,
  "final_score": 0.875,
  "verdict": "PASS",
  "reasoning": "简短的评估理由（1-3 句话）"
}
```"""

JUDGE_USER_TEMPLATE = """## 用户问题
{question}

## 期望输出（参考答案）
{expected}

## AI 实际输出
{actual}

## tool_result 原始数据（如有）
{tool_result}

请严格按照 JSON 格式输出评分结果。"""


class LLMJudgeGrader(BaseGrader):
    """LLM-as-Judge 评分器

    使用 qwen3.5 thinking mode 进行综合质量评估。
    thinking 过程会被捕获并返回，支持前端流式展示。
    """

    grader_name = "llm_judge"

    def __init__(self, pass_threshold: float = 0.8, model: str = "", **kwargs):
        super().__init__(pass_threshold=pass_threshold, **kwargs)
        self.model = model

    async def grade(
        self,
        input_json: Dict[str, Any],
        expected_json: Dict[str, Any],
        actual_output: Dict[str, Any],
        evaluator_config: Dict[str, Any] = None,
    ) -> GraderResult:
        from backend.config import settings

        config = evaluator_config or {}
        model = self.model or config.get("model") or settings.LLM_MODEL_NAME

        question = input_json.get("question", json.dumps(input_json, ensure_ascii=False))
        expected_str = json.dumps(expected_json, ensure_ascii=False, indent=2)
        actual_str = self._format_actual(actual_output)
        tool_result_str = self._extract_tool_results(actual_output)

        user_msg = JUDGE_USER_TEMPLATE.format(
            question=question,
            expected=expected_str,
            actual=actual_str,
            tool_result=tool_result_str or "（无 tool_result）",
        )

        try:
            result = await self._call_llm(model, JUDGE_SYSTEM_PROMPT, user_msg)
        except Exception as exc:
            logger.error(f"[LLMJudgeGrader] LLM 调用失败: {exc}")
            return self._make_result(
                0.0,
                reasoning=f"LLM Judge 调用失败: {type(exc).__name__}: {exc}",
            )

        thinking = result.get("thinking", "")
        content = result.get("content", "")

        parsed = self._parse_judge_output(content)
        if parsed is None:
            return self._make_result(
                0.0,
                reasoning=f"LLM Judge 输出解析失败: {content[:200]}",
                thinking=thinking,
            )

        final_score = parsed.get("final_score", 0.0)
        return self._make_result(
            final_score,
            reasoning=parsed.get("reasoning", ""),
            thinking=thinking,
            groundedness=parsed.get("groundedness", 0),
            task_completion=parsed.get("task_completion", 0),
            answer_quality=parsed.get("answer_quality", 0),
            tool_consistency=parsed.get("tool_consistency", 0),
            verdict=parsed.get("verdict", "FAIL"),
        )

    async def _call_llm(self, model: str, system: str, user: str) -> Dict[str, Any]:
        """调用 LLM，支持 thinking mode"""
        from openai import AsyncOpenAI
        from backend.config import settings

        client = AsyncOpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
        )

        extra_params = {}
        # qwen3.5 thinking mode: 通过 enable_thinking 参数启用
        if "qwen" in model.lower():
            extra_params["extra_body"] = {"enable_thinking": True}

        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.1,
            max_tokens=2048,
            **extra_params,
        )

        choice = response.choices[0]
        content = choice.message.content or ""

        # 提取 thinking（qwen3.5 返回在 reasoning_content 字段）
        thinking = ""
        if hasattr(choice.message, "reasoning_content") and choice.message.reasoning_content:
            thinking = choice.message.reasoning_content

        return {"content": content, "thinking": thinking}

    @staticmethod
    def _parse_judge_output(content: str) -> Optional[Dict[str, Any]]:
        """从 LLM 输出中解析 JSON 评分"""
        # 尝试直接解析
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # 尝试从 markdown code block 中提取
        import re
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
        if json_match:
            try:
                return json.loads(json_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # 尝试从文本中找到第一个 { ... } 块
        brace_match = re.search(r'\{[\s\S]*\}', content)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    @staticmethod
    def _format_actual(actual_output: Dict[str, Any]) -> str:
        """格式化 actual_output 为可读文本"""
        text = actual_output.get("text", "")
        if text:
            return text
        # 排除 events 等大字段
        filtered = {k: v for k, v in actual_output.items() if k not in ("events",)}
        return json.dumps(filtered, ensure_ascii=False, indent=2)

    @staticmethod
    def _extract_tool_results(actual_output: Dict[str, Any]) -> str:
        """从 actual_output 中提取 tool_results"""
        tool_results = actual_output.get("tool_results", [])
        if tool_results:
            return json.dumps(tool_results, ensure_ascii=False, indent=2)
        return ""
