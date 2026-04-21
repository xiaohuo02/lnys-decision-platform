# -*- coding: utf-8 -*-
"""backend/governance/eval_center/evolution/metaprompt_agent.py — MetapromptAgent

专职 prompt 优化的 Agent，分析失败原因并生成改进版 prompt。
参考 OpenAI Cookbook Self-Evolving Agents 的 MetapromptAgent 设计。

输入：
  - original_prompt: 当前 prompt
  - question:        用户问题示例
  - skill_output:    Skill 输出
  - grader_feedback: Grader 反馈
  - tool_result:     tool_result 原始数据（可选）

输出：
  - 改进后的完整 prompt 文本
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from loguru import logger


METAPROMPT_TEMPLATE = """你是一个 Prompt 优化专家。请根据评测反馈改进以下 Skill 的 prompt。

# 上下文
## 原始 Prompt
{original_prompt}

## 用户问题
{question}

## Skill 输出
{skill_output}

## tool_result 原始数据
{tool_result}

## 失败原因（来自 Grader）
{grader_feedback}

# 任务
写一个改进版的 Skill prompt，要求：
1. 直接修复 Grader 指出的具体问题
2. 保持原 prompt 的核心职责和结构不变
3. 增加具体、可执行的约束，而非泛泛而谈
4. 不改变输出格式兼容性
5. 如果存在数值幻觉问题，添加"严格引用 tool_result 原始数据"约束
6. 如果存在结构缺失问题，在输出格式示例中补全缺失字段

# 输出
只输出改进后的完整 prompt 文本，不要包含任何解释或标记。"""


class MetapromptAgent:
    """MetapromptAgent — 分析 Grader 反馈并优化 prompt

    使用 qwen3.5 thinking mode 进行深度分析：
      - thinking tokens 展示分析过程
      - 最终输出为改进后的 prompt

    Parameters:
        model:       模型名（默认从 config 读取）
        temperature: 生成温度（偏低以保证一致性）
        on_thinking: thinking tokens 回调
    """

    def __init__(
        self,
        model: str = "",
        temperature: float = 0.3,
        on_thinking: Optional[Callable] = None,
    ):
        self.model = model
        self.temperature = temperature
        self.on_thinking = on_thinking

    async def optimize(
        self,
        original_prompt: str,
        question: str,
        skill_output: str,
        grader_feedback: str,
        tool_result: str = "",
    ) -> Optional[str]:
        """分析反馈并生成改进 prompt

        Returns:
            改进后的 prompt 文本，失败返回 None
        """
        from openai import AsyncOpenAI
        from backend.config import settings

        model = self.model or settings.LLM_MODEL_NAME

        user_msg = METAPROMPT_TEMPLATE.format(
            original_prompt=original_prompt,
            question=question,
            skill_output=skill_output[:2000],
            grader_feedback=grader_feedback,
            tool_result=tool_result[:1000] if tool_result else "（无 tool_result）",
        )

        try:
            client = AsyncOpenAI(
                api_key=settings.LLM_API_KEY,
                base_url=settings.LLM_BASE_URL,
            )

            extra_params = {}
            if "qwen" in model.lower():
                extra_params["extra_body"] = {"enable_thinking": True}

            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": user_msg}],
                temperature=self.temperature,
                max_tokens=4096,
                **extra_params,
            )

            content = response.choices[0].message.content or ""

            # 提取 thinking 用于前端展示
            thinking = ""
            if hasattr(response.choices[0].message, "reasoning_content"):
                thinking = response.choices[0].message.reasoning_content or ""

            if thinking and self.on_thinking:
                try:
                    self.on_thinking(thinking)
                except Exception:
                    pass

            logger.info(f"[MetapromptAgent] 生成改进 prompt: {len(content)} 字符")
            return content.strip() if content.strip() else None

        except Exception as exc:
            logger.error(f"[MetapromptAgent] LLM 调用失败: {exc}")
            return None
