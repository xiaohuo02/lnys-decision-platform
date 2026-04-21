# -*- coding: utf-8 -*-
"""backend/governance/eval_center/memory/tip_extractor.py — Phase 1: 从 trace 提取 Tips

分析 Agent 执行轨迹，提取 3 种可复用 Tips：
  - Strategy: 来自干净成功的执行策略
  - Recovery: 来自失败后恢复的恢复模式
  - Optimization: 来自低效成功的优化建议
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

from loguru import logger

EXTRACTION_PROMPT = """分析以下 Agent 执行轨迹，提取可复用的经验教训。

## 轨迹信息
任务类型: {workflow_name}
最终状态: {status}
总耗时: {duration_ms}ms
步骤数: {steps_count}

## 执行步骤
{steps_formatted}

## 输出格式（严格 JSON 数组）
```json
[
  {{
    "tip_type": "strategy|recovery|optimization",
    "content": "简洁的经验描述（一句话）",
    "trigger": "何时应用此经验（触发条件）",
    "steps": ["具体操作步骤1", "步骤2"],
    "confidence": 0.5-1.0
  }}
]
```

## 提取规则
- **strategy**: 从干净成功的执行中提取有效策略（做什么是对的）
- **recovery**: 从包含失败→恢复的执行中提取恢复模式（出问题后怎么办）
- **optimization**: 从低效成功的执行中提取优化建议（怎么做更快/更好）
- 只提取可泛化的经验，不包含具体用户名/ID/时间等
- 每条轨迹提取 1-3 条 Tips，不要过度提取
- 置信度反映 Tip 的可靠性：成功轨迹高，部分成功低"""


class TipExtractor:
    """Phase 1: 从 trace 提取 Tips"""

    async def extract(self, trace: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从单条 trace 提取 Tips

        Args:
            trace: trace 详情，包含 workflow_name, status, steps 等

        Returns:
            Tips 列表（dict 格式，可直接入库）
        """
        workflow_name = trace.get("workflow_name", trace.get("workflow", "unknown"))
        status = trace.get("status", "unknown")
        steps = trace.get("steps", [])
        duration_ms = trace.get("duration_ms", 0)
        run_id = trace.get("run_id", "")

        if not steps:
            return []

        steps_formatted = self._format_steps(steps)

        prompt = EXTRACTION_PROMPT.format(
            workflow_name=workflow_name,
            status=status,
            duration_ms=duration_ms,
            steps_count=len(steps),
            steps_formatted=steps_formatted,
        )

        try:
            raw_tips = await self._call_llm(prompt)
        except Exception as exc:
            logger.error(f"[TipExtractor] LLM 调用失败: {exc}")
            return []

        tips = self._parse_tips(raw_tips, run_id, workflow_name)
        logger.info(f"[TipExtractor] trace {run_id}: 提取 {len(tips)} 条 Tips")
        return tips

    async def extract_batch(self, traces: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """批量从多条 trace 提取 Tips"""
        all_tips = []
        for trace in traces:
            tips = await self.extract(trace)
            all_tips.extend(tips)
        return all_tips

    @staticmethod
    def _format_steps(steps: List[Dict[str, Any]]) -> str:
        """格式化步骤信息供 LLM 分析"""
        lines = []
        for i, step in enumerate(steps[:20]):  # 最多 20 步
            name = step.get("name", step.get("agent_name", f"step_{i}"))
            status = step.get("status", "unknown")
            duration = step.get("duration_ms", 0)
            error = step.get("error", "")

            line = f"  {i+1}. [{status}] {name} ({duration}ms)"
            if error:
                line += f" — 错误: {error}"

            # 简要输入输出
            input_summary = step.get("input_summary", "")
            output_summary = step.get("output_summary", "")
            if input_summary:
                line += f"\n     输入: {str(input_summary)[:200]}"
            if output_summary:
                line += f"\n     输出: {str(output_summary)[:200]}"

            lines.append(line)
        return "\n".join(lines)

    async def _call_llm(self, prompt: str) -> str:
        """调用 LLM 提取 Tips"""
        from openai import AsyncOpenAI
        from backend.config import settings

        client = AsyncOpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
        )

        response = await client.chat.completions.create(
            model=settings.LLM_MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=2048,
        )
        return response.choices[0].message.content or ""

    @staticmethod
    def _parse_tips(raw: str, source_trace_id: str, task_type: str) -> List[Dict[str, Any]]:
        """解析 LLM 输出为结构化 Tips"""
        import re

        # 尝试多种解析方式
        parsed = None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            pass

        if parsed is None:
            match = re.search(r'```(?:json)?\s*([\s\S]*?)```', raw)
            if match:
                try:
                    parsed = json.loads(match.group(1).strip())
                except json.JSONDecodeError:
                    pass

        if parsed is None:
            match = re.search(r'\[[\s\S]*\]', raw)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass

        if not isinstance(parsed, list):
            return []

        tips = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            tip_type = item.get("tip_type", "strategy")
            if tip_type not in ("strategy", "recovery", "optimization"):
                continue

            tips.append({
                "tip_id": str(uuid.uuid4()),
                "tip_type": tip_type,
                "content": item.get("content", ""),
                "trigger_desc": item.get("trigger", ""),
                "steps": json.dumps(item.get("steps", []), ensure_ascii=False),
                "source_trace_id": source_trace_id,
                "source_task_type": task_type,
                "confidence": min(max(item.get("confidence", 0.5), 0.0), 1.0),
                "is_active": 1,
            })

        return tips
