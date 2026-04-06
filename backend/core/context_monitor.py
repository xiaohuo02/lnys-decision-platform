# -*- coding: utf-8 -*-
"""backend/core/context_monitor.py — 上下文治理监控器

设计来源: Aco ContextMonitor + Forge 自动压缩与上下文熔断设计 (doc/13)
核心机制:
  1. ContextBudget — 定义 token 预算和阈值
  2. ContextMonitor — 三状态机 (HEALTHY / NEEDS_COMPACT / CIRCUIT_BREAK)
  3. 自动压缩 — 超阈值时用 COMPACT 模型摘要旧历史
  4. 熔断机制 — 连续 N 次无效压缩 → 停止

用法:
    from backend.core.context_monitor import context_monitor, ContextStatus

    status = context_monitor.evaluate(current_tokens=6000)
    if status == ContextStatus.NEEDS_COMPACT:
        result = await context_monitor.compact(messages, ...)
    elif status == ContextStatus.CIRCUIT_BREAK:
        raise ContextTooLongError("熔断: 连续压缩无效")
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from loguru import logger


class ContextStatus(str, Enum):
    """上下文健康状态"""
    HEALTHY = "healthy"                # < 阈值，正常
    NEEDS_COMPACT = "needs_compact"    # ≥ 阈值，需要压缩
    CIRCUIT_BREAK = "circuit_break"    # 连续无效压缩，熔断


@dataclass(frozen=True)
class ContextBudget:
    """上下文 token 预算配置 (不可变)。

    Attributes:
        max_tokens:          模型上下文窗口上限
        compact_threshold:   触发压缩的使用率阈值 (0.80)
        target_ratio:        压缩后目标使用率 (0.55)
        max_thrash_count:    最大连续无效压缩次数
        min_effective_reduction: 有效压缩的最低减少率
        recent_window:       最近不压缩的消息轮数
    """
    max_tokens: int = 32_000
    compact_threshold: float = 0.80
    target_ratio: float = 0.55
    max_thrash_count: int = 3
    min_effective_reduction: float = 0.15
    recent_window: int = 6

    @classmethod
    def for_model(cls, model_name: str) -> "ContextBudget":
        """根据模型名推导预算。"""
        model_lower = model_name.lower()

        if any(k in model_lower for k in ("gpt-4o", "gpt-4-turbo")):
            return cls(max_tokens=128_000)
        elif "gpt-4" in model_lower:
            return cls(max_tokens=8_192)
        elif "gpt-3.5" in model_lower:
            return cls(max_tokens=16_385)
        elif any(k in model_lower for k in ("claude-3", "claude-3.5")):
            return cls(max_tokens=200_000)
        elif "qwen" in model_lower and any(k in model_lower for k in ("plus", "max", "turbo")):
            return cls(max_tokens=131_072)
        elif "qwen" in model_lower:
            return cls(max_tokens=32_768)
        elif "deepseek" in model_lower:
            return cls(max_tokens=64_000)
        else:
            return cls(max_tokens=32_000)


@dataclass
class CompactionResult:
    """压缩结果"""
    tokens_before: int
    tokens_after: int
    messages_before: int
    messages_after: int
    is_effective: bool
    compacted_messages: List[dict] = field(default_factory=list)
    summary: str = ""
    duration_ms: int = 0


@dataclass
class ContextDiagnostics:
    """上下文诊断信息 (供前端展示)"""
    current_tokens: int
    max_tokens: int
    usage_ratio: float
    status: str
    thrash_count: int
    max_thrash: int
    last_compact_time: Optional[float]       # unix timestamp
    last_compact_before: int
    last_compact_after: int
    total_compactions: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_tokens": self.current_tokens,
            "max_tokens": self.max_tokens,
            "usage_ratio": round(self.usage_ratio, 4),
            "usage_percent": round(self.usage_ratio * 100, 1),
            "status": self.status,
            "thrash_count": self.thrash_count,
            "max_thrash": self.max_thrash,
            "last_compact_time": self.last_compact_time,
            "last_compact_before": self.last_compact_before,
            "last_compact_after": self.last_compact_after,
            "total_compactions": self.total_compactions,
        }


class ContextMonitor:
    """上下文治理监控器。

    三状态机:
        HEALTHY        — usage < compact_threshold → 正常
        NEEDS_COMPACT  — usage ≥ compact_threshold and thrash_count < max → 需要压缩
        CIRCUIT_BREAK  — thrash_count ≥ max → 熔断

    线程安全: 每个 thread_id 独立状态（用于 Copilot 多会话场景）。
    """

    def __init__(self, budget: Optional[ContextBudget] = None):
        self._budget = budget or ContextBudget()
        # per-thread 状态
        self._thrash_counts: Dict[str, int] = {}
        self._last_compact: Dict[str, Dict[str, Any]] = {}
        self._total_compactions: Dict[str, int] = {}

    @property
    def budget(self) -> ContextBudget:
        return self._budget

    def set_budget(self, budget: ContextBudget) -> None:
        """动态更新预算（模型切换时使用）。"""
        self._budget = budget

    def evaluate(self, current_tokens: int, thread_id: str = "_default") -> ContextStatus:
        """评估当前上下文状态。

        Args:
            current_tokens: 当前 token 数
            thread_id: 会话 ID (多会话隔离)

        Returns:
            ContextStatus
        """
        ratio = current_tokens / self._budget.max_tokens if self._budget.max_tokens > 0 else 1.0

        if ratio < self._budget.compact_threshold:
            # 健康状态: 如果回到了目标以下，重置 thrash 计数
            if ratio < self._budget.target_ratio:
                self._thrash_counts[thread_id] = 0
            return ContextStatus.HEALTHY

        # 需要压缩: 检查是否已熔断
        thrash = self._thrash_counts.get(thread_id, 0)
        if thrash >= self._budget.max_thrash_count:
            logger.error(
                f"[ContextMonitor] CIRCUIT_BREAK thread={thread_id} "
                f"thrash={thrash}/{self._budget.max_thrash_count} "
                f"tokens={current_tokens}/{self._budget.max_tokens}"
            )
            return ContextStatus.CIRCUIT_BREAK

        logger.warning(
            f"[ContextMonitor] NEEDS_COMPACT thread={thread_id} "
            f"ratio={ratio:.2%} thrash={thrash}"
        )
        return ContextStatus.NEEDS_COMPACT

    def record_compaction(
        self,
        tokens_before: int,
        tokens_after: int,
        thread_id: str = "_default",
    ) -> bool:
        """记录一次压缩的效果。

        Returns:
            True if compaction was effective
        """
        reduction = 1.0 - (tokens_after / tokens_before) if tokens_before > 0 else 0.0
        is_effective = reduction >= self._budget.min_effective_reduction

        self._last_compact[thread_id] = {
            "time": time.time(),
            "before": tokens_before,
            "after": tokens_after,
            "reduction": reduction,
        }
        self._total_compactions[thread_id] = self._total_compactions.get(thread_id, 0) + 1

        if is_effective:
            self._thrash_counts[thread_id] = 0
            logger.info(
                f"[ContextMonitor] compaction effective thread={thread_id} "
                f"reduction={reduction:.1%} ({tokens_before} → {tokens_after})"
            )
        else:
            self._thrash_counts[thread_id] = self._thrash_counts.get(thread_id, 0) + 1
            logger.warning(
                f"[ContextMonitor] compaction INEFFECTIVE thread={thread_id} "
                f"reduction={reduction:.1%} thrash={self._thrash_counts[thread_id]}"
            )

        return is_effective

    async def compact_messages(
        self,
        messages: List[dict],
        thread_id: str = "_default",
    ) -> CompactionResult:
        """用 COMPACT 模型压缩旧历史消息。

        策略:
        - 保留最近 recent_window 轮不动
        - 旧消息用 LLM 摘要成一条 system message
        - 计算压缩前后 token 数，记录效果

        Returns:
            CompactionResult
        """
        from backend.core.token_counter import token_counter
        from backend.core.model_selector import model_selector, ModelRole

        t0 = time.time()
        tokens_before = token_counter.estimate_messages(messages)
        msgs_before = len(messages)

        # 分离: 最近消息 vs 旧消息
        window = self._budget.recent_window * 2  # 每轮 user+assistant = 2 条
        if len(messages) <= window + 1:
            # 消息太少，不需要压缩
            return CompactionResult(
                tokens_before=tokens_before,
                tokens_after=tokens_before,
                messages_before=msgs_before,
                messages_after=msgs_before,
                is_effective=False,
                compacted_messages=messages,
                summary="消息太少，无需压缩",
                duration_ms=0,
            )

        # system message (index 0) 永远保留
        system_msg = messages[0] if messages and messages[0].get("role") == "system" else None
        history = messages[1:] if system_msg else messages
        old_history = history[:-window] if window > 0 else history
        recent_history = history[-window:] if window > 0 else []

        # 用 LLM 摘要旧历史
        old_text = "\n".join(
            f"[{m.get('role', '?')}]: {str(m.get('content', ''))[:200]}"
            for m in old_history
        )

        summary = ""
        try:
            llm = model_selector.get_llm(ModelRole.COMPACT)
            if llm:
                compact_prompt = (
                    "请将以下对话历史压缩为一段简洁的摘要，保留关键事实、决策和结论，"
                    "删除重复信息和过程细节。用中文回答，不超过 300 字。\n\n"
                    f"对话历史:\n{old_text[:3000]}"
                )
                resp = await llm.ainvoke(compact_prompt)
                summary = resp.content if hasattr(resp, "content") else str(resp)
                summary = summary[:500]
        except Exception as e:
            logger.warning(f"[ContextMonitor] LLM compact failed, fallback to truncation: {e}")
            # fallback: 截取旧历史的前后各 1 条
            if old_history:
                first = str(old_history[0].get("content", ""))[:100]
                last = str(old_history[-1].get("content", ""))[:100]
                summary = f"[历史摘要] 共 {len(old_history)} 条消息。首: {first}... 末: {last}..."

        # 组装压缩后的消息
        compacted: List[dict] = []
        if system_msg:
            compacted.append(system_msg)
        if summary:
            compacted.append({
                "role": "system",
                "content": f"[对话历史摘要]\n{summary}",
            })
        compacted.extend(recent_history)

        tokens_after = token_counter.estimate_messages(compacted)
        duration_ms = int((time.time() - t0) * 1000)
        is_effective = self.record_compaction(tokens_before, tokens_after, thread_id)

        result = CompactionResult(
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            messages_before=msgs_before,
            messages_after=len(compacted),
            is_effective=is_effective,
            compacted_messages=compacted,
            summary=summary,
            duration_ms=duration_ms,
        )
        logger.info(
            f"[ContextMonitor] compact done thread={thread_id} "
            f"{tokens_before}→{tokens_after} tokens "
            f"{msgs_before}→{len(compacted)} msgs "
            f"effective={is_effective} {duration_ms}ms"
        )
        return result

    def diagnostics(self, current_tokens: int, thread_id: str = "_default") -> ContextDiagnostics:
        """获取诊断信息（供 API 和前端展示）。只读，不修改任何内部状态。"""
        ratio = current_tokens / self._budget.max_tokens if self._budget.max_tokens > 0 else 1.0
        # 纯读取状态推断，不调用 evaluate() 以避免副作用（evaluate 会重置 thrash_count）
        if ratio < self._budget.compact_threshold:
            status = ContextStatus.HEALTHY.value
        elif self._thrash_counts.get(thread_id, 0) >= self._budget.max_thrash_count:
            status = ContextStatus.CIRCUIT_BREAK.value
        else:
            status = ContextStatus.NEEDS_COMPACT.value
        last = self._last_compact.get(thread_id, {})
        return ContextDiagnostics(
            current_tokens=current_tokens,
            max_tokens=self._budget.max_tokens,
            usage_ratio=ratio,
            status=status,
            thrash_count=self._thrash_counts.get(thread_id, 0),
            max_thrash=self._budget.max_thrash_count,
            last_compact_time=last.get("time"),
            last_compact_before=last.get("before", 0),
            last_compact_after=last.get("after", 0),
            total_compactions=self._total_compactions.get(thread_id, 0),
        )

    def reset(self, thread_id: str = "_default") -> None:
        """重置指定会话的状态。"""
        self._thrash_counts.pop(thread_id, None)
        self._last_compact.pop(thread_id, None)
        self._total_compactions.pop(thread_id, None)


# ── 默认单例 ──────────────────────────────────────────────────────
context_monitor = ContextMonitor()
