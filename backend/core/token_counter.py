# -*- coding: utf-8 -*-
"""backend/core/token_counter.py — 统一 Token 计数器

设计来源: Aco/Forge TokenCounter 跨切面统一接口
核心原则: 所有预算组件共用同一个 counter，保证全局一致性

用法:
    from backend.core.token_counter import token_counter

    n = token_counter.estimate("你好世界 Hello World")
    ok = token_counter.fits_budget("long text...", budget=4096)
    ratio = token_counter.usage_ratio(current_tokens=3200, max_tokens=4096)
"""
from __future__ import annotations

import re
from typing import List, Optional, Union


class TokenCounter:
    """统一 Token 计数器。

    策略:
    - 中文字符: 约 1.2-1.8 token/char (取 1.5)
    - 英文单词: 约 1.3 token/word (取 ~0.25 token/char)
    - 标点/空白: 约 0.5 token/char
    - 混合文本: 分段估算再累加

    精度: 对中文+英文混合文本误差 < 15%，足够用于预算控制。
    """

    # 正则: CJK 统一表意文字
    _CJK_RE = re.compile(
        r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff"
        r"\U00020000-\U0002a6df\U0002a700-\U0002ebef]"
    )
    _ASCII_WORD_RE = re.compile(r"[a-zA-Z0-9]+")

    # 每类字符的 token 系数
    CJK_FACTOR = 1.5       # 中文字符
    ASCII_FACTOR = 0.25    # 英文/数字字符
    OTHER_FACTOR = 0.5     # 标点/空白/特殊符号

    # Function Calling schema 的 token overhead (经验值)
    FC_SCHEMA_OVERHEAD = 50   # 每个 tool schema
    FC_CALL_OVERHEAD = 30     # 每次 tool call

    def estimate(self, text: str) -> int:
        """估算文本的 token 数量。"""
        if not text:
            return 0

        cjk_count = len(self._CJK_RE.findall(text))
        ascii_count = sum(len(m.group()) for m in self._ASCII_WORD_RE.finditer(text))
        other_count = max(0, len(text) - cjk_count - ascii_count)

        tokens = (
            cjk_count * self.CJK_FACTOR
            + ascii_count * self.ASCII_FACTOR
            + other_count * self.OTHER_FACTOR
        )
        return max(1, int(tokens))

    def estimate_messages(self, messages: List[dict]) -> int:
        """估算 messages 列表的总 token 数。

        每条 message 额外 4 token overhead (role + 分隔)。
        """
        total = 0
        for msg in messages:
            total += 4  # role + separators
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.estimate(content)
            elif isinstance(content, list):
                # multimodal: [{"type":"text","text":"..."}, ...]
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        total += self.estimate(part.get("text", ""))
                    elif isinstance(part, dict) and part.get("type") == "image_url":
                        total += 85  # 低分辨率图片 ~85 tokens
        total += 2  # assistant priming
        return total

    def estimate_tools_schema(self, tool_count: int) -> int:
        """估算 FC tool schema 的 token 开销。"""
        return tool_count * self.FC_SCHEMA_OVERHEAD

    def fits_budget(self, text: str, budget: int, reserved: int = 0) -> bool:
        """检查文本是否在预算内。

        Args:
            text: 待检查文本
            budget: token 上限
            reserved: 为输出预留的 token 数
        """
        return self.estimate(text) <= (budget - reserved)

    def usage_ratio(self, current_tokens: int, max_tokens: int) -> float:
        """计算 token 使用率。"""
        if max_tokens <= 0:
            return 1.0
        return current_tokens / max_tokens

    def truncate_to_budget(
        self,
        text: str,
        budget: int,
        strategy: str = "head_tail",
        head_ratio: float = 0.7,
    ) -> str:
        """将文本截断到 token 预算内。

        Args:
            text: 原始文本
            budget: token 上限
            strategy: 截断策略 ("head_tail" 或 "head")
            head_ratio: head_tail 模式下头部比例
        """
        estimated = self.estimate(text)
        if estimated <= budget:
            return text

        # 反向推算字符数（粗估 1 token ≈ 1.2 chars for 中英混合）
        char_budget = int(budget * 1.2)

        if strategy == "head_tail":
            head_chars = int(char_budget * head_ratio)
            tail_chars = max(0, char_budget - head_chars)
            omitted = max(0, len(text) - head_chars - tail_chars)
            if tail_chars > 0 and omitted > 0:
                return (
                    text[:head_chars]
                    + f"\n...[已截断 {omitted} 字符]...\n"
                    + text[-tail_chars:]
                )
            else:
                return text[:char_budget] + f"\n...[已截断 {max(0, len(text) - char_budget)} 字符]"
        else:
            return text[:char_budget] + f"\n...[已截断 {max(0, len(text) - char_budget)} 字符]"

    def split_budget(
        self,
        total_budget: int,
        sections: dict[str, float],
    ) -> dict[str, int]:
        """按比例分配 token 预算给各 section。

        Args:
            total_budget: 总 token 预算
            sections: {section_name: ratio} (比例之和应为 1.0)

        Returns:
            {section_name: allocated_tokens}
        """
        ratio_sum = sum(sections.values())
        return {
            name: int(total_budget * ratio / ratio_sum)
            for name, ratio in sections.items()
        }


# ── 默认单例 ──────────────────────────────────────────────────────
token_counter = TokenCounter()
