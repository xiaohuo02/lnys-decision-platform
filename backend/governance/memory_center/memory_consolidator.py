# -*- coding: utf-8 -*-
"""backend/governance/memory_center/memory_consolidator.py — 3层上下文压缩

设计来源: Claude Code artifact summary + LangChain ConversationSummaryMemory

3 层压缩:
  Layer 1 微压缩: compress_artifact(content, max_tokens=2000)
    → 纯 Python 截断，不调 LLM，保留首尾关键信息
  
  Layer 2 自动压缩: compact_conversation(messages, keep_recent=3)
    → 用 LLM 将前 N 轮压缩为摘要，保留最近 keep_recent 轮原文
  
  Layer 3 记忆整合: consolidate_run(run_id, steps_summary)
    → 用 LLM 提取本次 run 的关键学习 → 返回结构化记忆条目

用法:
    from backend.governance.memory_center.memory_consolidator import memory_consolidator

    # Layer 1: 截断过长 artifact
    short = memory_consolidator.compress_artifact(long_text, max_tokens=2000)

    # Layer 2: 压缩多轮对话
    compressed = await memory_consolidator.compact_conversation(messages, keep_recent=3)

    # Layer 3: 整合 run 学习
    memories = await memory_consolidator.consolidate_run(run_id, steps_summary)
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

from loguru import logger
from pydantic import BaseModel, Field


# ── 数据结构 ──────────────────────────────────────────────────────

class CompressedConversation(BaseModel):
    """Layer 2 压缩结果"""
    summary: str                           # 前 N 轮的压缩摘要
    recent_messages: List[Dict[str, str]]  # 保留的最近几轮原文
    original_count: int = 0                # 原始消息总数
    compressed_count: int = 0              # 被压缩的消息数


class MemoryEntry(BaseModel):
    """Layer 3 记忆条目"""
    run_id: str
    category: str = "general"              # general / pattern / error / preference
    content: str
    confidence: float = 0.5
    tags: List[str] = Field(default_factory=list)


class ConsolidationResult(BaseModel):
    """Layer 3 整合结果"""
    run_id: str
    entries: List[MemoryEntry] = Field(default_factory=list)
    summary: str = ""


# ── MemoryConsolidator 实现 ──────────────────────────────────────

class MemoryConsolidator:
    """3 层上下文压缩与记忆整合器"""

    # ── Layer 1: 微压缩 (纯 Python，无 LLM) ──────────────────

    def compress_artifact(
        self,
        content: str,
        max_tokens: int = 2000,
        preserve_head: int = 500,
        preserve_tail: int = 300,
    ) -> str:
        """
        Layer 1 微压缩：对过长的 artifact 内容进行智能截断。
        
        策略:
        - 如果 content 在 max_tokens 以内，原样返回
        - 否则保留头部 preserve_head 字符 + 尾部 preserve_tail 字符
        - 中间插入截断标记，标注省略长度
        - 优先在句子边界截断
        """
        # 粗略估算: 1 token ≈ 1.5 中文字符 ≈ 4 英文字符
        char_limit = int(max_tokens * 1.5)

        if len(content) <= char_limit:
            return content

        head = content[:preserve_head]
        tail = content[-preserve_tail:]

        # 在句子边界截断 head
        for sep in ["。", ".", "\n", "；", ";", "，", ","]:
            last_sep = head.rfind(sep)
            if last_sep > preserve_head * 0.6:
                head = head[:last_sep + 1]
                break

        # 在句子边界截断 tail
        for sep in ["。", ".", "\n", "；", ";", "，", ","]:
            first_sep = tail.find(sep)
            if 0 < first_sep < preserve_tail * 0.4:
                tail = tail[first_sep + 1:]
                break

        omitted = len(content) - len(head) - len(tail)
        marker = f"\n\n... [已省略 {omitted} 字符 / 约 {omitted // 2} tokens] ...\n\n"

        result = head + marker + tail
        logger.debug(
            f"[MemoryConsolidator] L1 compress: "
            f"{len(content)} → {len(result)} chars "
            f"(omitted {omitted})"
        )
        return result

    # ── Layer 2: 自动压缩 (LLM 摘要) ────────────────────────

    async def compact_conversation(
        self,
        messages: List[Dict[str, str]],
        keep_recent: int = 3,
    ) -> CompressedConversation:
        """
        Layer 2 自动压缩：将多轮对话的早期部分压缩为摘要。
        
        策略:
        - 保留最近 keep_recent 轮消息原文
        - 将更早的消息用 LLM 压缩为摘要
        - LLM 不可用时，使用纯 Python 截断降级
        """
        total = len(messages)

        if total <= keep_recent * 2:
            # 消息数不多，不需要压缩
            return CompressedConversation(
                summary="",
                recent_messages=messages,
                original_count=total,
                compressed_count=0,
            )

        # 分割: 早期 + 最近
        recent = messages[-(keep_recent * 2):]  # 每轮 user+assistant = 2条
        early = messages[:-(keep_recent * 2)]

        # 尝试 LLM 压缩
        summary = await self._llm_summarize_messages(early)

        if not summary:
            # 降级: 纯 Python 截断
            summary = self._fallback_summarize(early)

        logger.info(
            f"[MemoryConsolidator] L2 compact: "
            f"{total} msgs → summary({len(summary)}c) + {len(recent)} recent"
        )

        return CompressedConversation(
            summary=summary,
            recent_messages=recent,
            original_count=total,
            compressed_count=len(early),
        )

    async def _llm_summarize_messages(
        self, messages: List[Dict[str, str]]
    ) -> Optional[str]:
        """用 COMPACT 模型压缩多轮对话为摘要"""
        try:
            from langchain_openai import ChatOpenAI
            from backend.core.model_selector import model_selector, ModelRole
            from backend.core.telemetry import telemetry, TelemetryEventType

            spec = model_selector.get_spec(ModelRole.COMPACT)
            api_key = spec.api_key or os.getenv("LLM_API_KEY", "")
            if not api_key:
                return None

            # 构造对话文本
            lines = []
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")[:200]
                lines.append(f"[{role}]: {content}")
            conversation_text = "\n".join(lines)

            if len(conversation_text) > 8000:
                conversation_text = conversation_text[:8000] + "\n..."

            prompt = (
                "请将以下多轮对话压缩为一段简明的中文摘要（150-300字），"
                "保留关键信息、用户意图和重要结论：\n\n"
                f"{conversation_text}"
            )

            telemetry.emit(TelemetryEventType.MODEL_REQUESTED, {
                "model": spec.model_name, "role": "compact",
                "task": "conversation_compaction",
            }, component="MemoryConsolidator")

            import time as _time
            _t0 = _time.time()

            llm = ChatOpenAI(
                api_key=api_key,
                base_url=spec.base_url or os.getenv("LLM_BASE_URL", ""),
                model=spec.model_name,
                max_tokens=500,
                temperature=spec.temperature,
                timeout=spec.timeout,
            )
            resp = await llm.ainvoke(prompt)
            content = resp.content.strip() if resp.content else ""

            _usage = (resp.response_metadata or {}).get('token_usage', {}) if hasattr(resp, 'response_metadata') and resp.response_metadata else {}
            _tok_in = _usage.get('prompt_tokens', 0) or 0
            _tok_out = _usage.get('completion_tokens', 0) or 0
            telemetry.emit(TelemetryEventType.MODEL_COMPLETED, {
                "model": spec.model_name, "role": "compact",
                "task": "conversation_compaction",
                "tokens_in": _tok_in, "tokens_out": _tok_out,
                "latency_ms": int((_time.time() - _t0) * 1000),
            }, component="MemoryConsolidator")

            if len(content) >= 20:
                logger.info(
                    f"[MemoryConsolidator] L2 LLM summary: {len(content)}c"
                )
                return content
            return None
        except Exception as e:
            logger.warning(f"[MemoryConsolidator] L2 LLM failed: {e}")
            return None

    def _fallback_summarize(self, messages: List[Dict[str, str]]) -> str:
        """纯 Python 降级摘要"""
        parts = []
        for msg in messages[:10]:  # 最多取前 10 条
            role = msg.get("role", "user")
            content = msg.get("content", "")[:80]
            parts.append(f"[{role}] {content}")
        return "对话历史摘要:\n" + "\n".join(parts)

    # ── Layer 3: 记忆整合 (LLM 提取关键学习) ─────────────────

    async def consolidate_run(
        self,
        run_id: str,
        steps_summary: List[Dict[str, Any]],
    ) -> ConsolidationResult:
        """
        Layer 3 记忆整合：从一次 run 的步骤摘要中提取关键学习。
        
        策略:
        - 用 LLM 分析 run 的执行结果，提取可复用的模式/教训
        - 返回结构化记忆条目，可写入 memory_records 表
        - LLM 不可用时返回空结果
        """
        entries = await self._llm_extract_memories(run_id, steps_summary)

        summary_text = ""
        if entries:
            summary_text = "; ".join(e.content[:50] for e in entries[:3])

        logger.info(
            f"[MemoryConsolidator] L3 consolidate: "
            f"run_id={run_id} entries={len(entries)}"
        )

        return ConsolidationResult(
            run_id=run_id,
            entries=entries,
            summary=summary_text,
        )

    async def _llm_extract_memories(
        self,
        run_id: str,
        steps_summary: List[Dict[str, Any]],
    ) -> List[MemoryEntry]:
        """用 REVIEW 模型提取关键记忆"""
        try:
            from langchain_openai import ChatOpenAI
            from backend.core.model_selector import model_selector, ModelRole
            from backend.core.telemetry import telemetry, TelemetryEventType

            spec = model_selector.get_spec(ModelRole.REVIEW)
            api_key = spec.api_key or os.getenv("LLM_API_KEY", "")
            if not api_key:
                return []

            # 构造步骤文本
            lines = []
            for step in steps_summary:
                name = step.get("step_name", "unknown")
                status = step.get("status", "unknown")
                output = str(step.get("output_summary", ""))[:200]
                error = step.get("error", "")
                line = f"- {name}: status={status}"
                if output:
                    line += f", output={output}"
                if error:
                    line += f", error={error}"
                lines.append(line)
            steps_text = "\n".join(lines)

            prompt = (
                "分析以下 workflow run 的执行结果，提取 1-3 条可复用的关键学习/模式。\n"
                "每条学习用一行描述，格式: [类别] 内容\n"
                "类别可选: pattern(可复用模式) / error(错误教训) / preference(用户偏好)\n\n"
                f"Run ID: {run_id}\n"
                f"步骤摘要:\n{steps_text}\n\n"
                "请提取关键学习:"
            )

            telemetry.emit(TelemetryEventType.MODEL_REQUESTED, {
                "model": spec.model_name, "role": "review",
                "task": "memory_extraction",
            }, component="MemoryConsolidator")

            import time as _time
            _t0 = _time.time()

            llm = ChatOpenAI(
                api_key=api_key,
                base_url=spec.base_url or os.getenv("LLM_BASE_URL", ""),
                model=spec.model_name,
                max_tokens=500,
                temperature=spec.temperature,
                timeout=spec.timeout,
            )
            resp = await llm.ainvoke(prompt)
            content = resp.content.strip() if resp.content else ""

            _usage = (resp.response_metadata or {}).get('token_usage', {}) if hasattr(resp, 'response_metadata') and resp.response_metadata else {}
            _tok_in = _usage.get('prompt_tokens', 0) or 0
            _tok_out = _usage.get('completion_tokens', 0) or 0
            telemetry.emit(TelemetryEventType.MODEL_COMPLETED, {
                "model": spec.model_name, "role": "review",
                "task": "memory_extraction",
                "tokens_in": _tok_in, "tokens_out": _tok_out,
                "latency_ms": int((_time.time() - _t0) * 1000),
            }, component="MemoryConsolidator")

            if not content:
                return []

            # 解析 LLM 输出
            entries = []
            for line in content.split("\n"):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                # 尝试匹配 [类别] 内容
                match = re.match(r"\[(\w+)\]\s*(.+)", line)
                if match:
                    category = match.group(1).lower()
                    text = match.group(2).strip()
                else:
                    # 去掉序号前缀
                    text = re.sub(r"^[\d\.\-\*]+\s*", "", line).strip()
                    category = "general"

                if category not in ("pattern", "error", "preference", "general"):
                    category = "general"

                if len(text) >= 10:
                    entries.append(MemoryEntry(
                        run_id=run_id,
                        category=category,
                        content=text,
                        confidence=0.7,
                    ))

            logger.info(
                f"[MemoryConsolidator] L3 LLM extracted: {len(entries)} entries"
            )
            return entries[:5]  # 最多 5 条
        except Exception as e:
            logger.warning(f"[MemoryConsolidator] L3 LLM failed: {e}")
            return []


# ── 全局单例 ──────────────────────────────────────────────────────

memory_consolidator = MemoryConsolidator()
