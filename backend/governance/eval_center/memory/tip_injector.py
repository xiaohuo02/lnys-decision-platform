# -*- coding: utf-8 -*-
"""backend/governance/eval_center/memory/tip_injector.py — Tips 注入 prompt

将检索到的 Tips 注入 Agent/Skill 的 prompt 中，
在 [Guidelines] 段添加历史经验指南。

接入 CopilotEngine 的方式：
  1. 在 Skill 执行前调用 TipRetriever.retrieve()
  2. 将检索到的 Tips 通过 TipInjector.inject() 注入 system_prompt
  3. Skill 执行时参考这些 Tips
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from loguru import logger


_TIP_TYPE_LABELS = {
    "strategy": "✓ 策略",
    "recovery": "⚡ 恢复",
    "optimization": "⚙ 优化",
}


class TipInjector:
    """Tips 注入器 — 将检索到的 Tips 注入 prompt

    支持两种注入模式：
      1. append:  追加到 prompt 末尾（默认）
      2. section: 在指定标记位置插入
    """

    def __init__(
        self,
        section_header: str = "【历史经验指南 — 基于过往执行轨迹自动提取】",
        max_tips: int = 5,
        mode: str = "append",
    ):
        self.section_header = section_header
        self.max_tips = max_tips
        self.mode = mode

    def inject(
        self,
        base_prompt: str,
        tips: List[Dict[str, Any]],
        task_description: str = "",
    ) -> str:
        """将 Tips 注入 prompt

        Args:
            base_prompt:      原始 prompt
            tips:             检索到的 Tips 列表
            task_description: 当前任务描述（用于日志）

        Returns:
            注入 Tips 后的 prompt
        """
        if not tips:
            return base_prompt

        selected = tips[:self.max_tips]
        guidelines = self._format_tips(selected)

        tip_ids = [t.get("tip_id", "") for t in selected if t.get("tip_id")]
        logger.debug(
            f"[TipInjector] 注入 {len(selected)} 条 Tips "
            f"(task={task_description[:50] if task_description else 'N/A'})"
        )

        if self.mode == "section":
            return self._inject_at_section(base_prompt, guidelines)
        else:
            return self._inject_append(base_prompt, guidelines)

    def _format_tips(self, tips: List[Dict[str, Any]]) -> str:
        """格式化 Tips 为可读文本"""
        lines = []
        for t in tips:
            tip_type = t.get("tip_type", "strategy")
            content = t.get("content", "")
            label = _TIP_TYPE_LABELS.get(tip_type, "💡")
            confidence = t.get("confidence", 0)
            relevance = t.get("relevance_score", 0)

            line = f"- [{label}] {content}"
            if confidence > 0:
                line += f" (置信度: {confidence:.0%})"
            lines.append(line)

        return "\n".join(lines)

    def _inject_append(self, base_prompt: str, guidelines: str) -> str:
        """追加模式：在 prompt 末尾添加"""
        return f"{base_prompt}\n\n{self.section_header}\n{guidelines}"

    def _inject_at_section(self, base_prompt: str, guidelines: str) -> str:
        """标记模式：替换指定位置的内容"""
        marker = "{{TIPS_PLACEHOLDER}}"
        if marker in base_prompt:
            return base_prompt.replace(
                marker,
                f"{self.section_header}\n{guidelines}",
            )
        # 降级到追加模式
        return self._inject_append(base_prompt, guidelines)

    @staticmethod
    def get_injected_tip_ids(tips: List[Dict[str, Any]]) -> List[str]:
        """提取注入的 Tip IDs（用于增加引用计数）"""
        return [t.get("tip_id", "") for t in tips if t.get("tip_id")]
