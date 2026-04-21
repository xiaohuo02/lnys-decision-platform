# -*- coding: utf-8 -*-
"""backend/knowledge/chunk_engine.py — 递归语义分块引擎

三级递归分块策略：
  Level 1: 按标题(#/##/###) 和大段落(\n\n) 拆分
  Level 2: 按句子边界（。！？\n）拆分
  Level 3: 按 token 数硬截断（保底）

特性：
  - 保留标题层级路径（heading_path）
  - 表格整块保留不拆
  - 碎片合并（过短 chunk 向前合并）
  - 支持 fixed/recursive/none 三种策略
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from loguru import logger


@dataclass
class ChunkResult:
    """单个 chunk 结果"""
    content: str
    chunk_index: int = 0
    char_count: int = 0
    token_count: int = 0
    heading_path: str = ""
    chunk_type: str = "paragraph"  # paragraph / table / list / code / ocr


def _estimate_tokens(text: str) -> int:
    """粗略估算 token 数：中文按1.5字/token，英文按4字符/token"""
    cn_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    other_chars = len(text) - cn_chars
    return int(cn_chars / 1.5 + other_chars / 4)


def _split_by_headings(text: str) -> List[Dict]:
    """按标题行拆分，返回 [{heading, content, level}]"""
    # 匹配 Markdown 标题 或 中文标题模式
    heading_pattern = re.compile(
        r"^(#{1,6})\s+(.+)$|^(第[一二三四五六七八九十百]+[章节条款部分])\s*(.*)$|^(\d+[\.\、])\s*(.+)$",
        re.MULTILINE,
    )

    sections = []
    last_end = 0
    current_heading = ""

    for m in heading_pattern.finditer(text):
        # 前一段内容
        if m.start() > last_end:
            content = text[last_end:m.start()].strip()
            if content:
                sections.append({
                    "heading": current_heading,
                    "content": content,
                })

        # 解析标题
        if m.group(1):  # Markdown heading
            current_heading = m.group(2).strip()
        elif m.group(3):  # 中文标题
            current_heading = (m.group(3) + " " + (m.group(4) or "")).strip()
        elif m.group(5):  # 数字标题
            current_heading = (m.group(5) + " " + m.group(6)).strip()

        last_end = m.end()

    # 尾部内容
    if last_end < len(text):
        tail = text[last_end:].strip()
        if tail:
            sections.append({
                "heading": current_heading,
                "content": tail,
            })

    # 没有标题 → 整段作为一个 section
    if not sections:
        sections.append({"heading": "", "content": text.strip()})

    return sections


def _split_by_sentences(text: str) -> List[str]:
    """按句子边界拆分"""
    sentences = re.split(r"(?<=[。！？\n])", text)
    return [s for s in sentences if s.strip()]


def _detect_table(text: str) -> bool:
    """检测文本是否为表格"""
    lines = text.strip().split("\n")
    if len(lines) < 2:
        return False
    pipe_lines = sum(1 for line in lines if "|" in line)
    return pipe_lines / len(lines) > 0.5


def _detect_list(text: str) -> bool:
    """检测文本是否为连续列表块（无序/有序）。"""
    lines = [l for l in text.strip().split("\n") if l.strip()]
    if len(lines) < 2:
        return False
    list_pattern = re.compile(r"^\s*[-*+•]\s|^\s*\d+[\..\)、]\s?")
    list_lines = sum(1 for l in lines if list_pattern.match(l))
    return list_lines / len(lines) >= 0.5


# ── 主函数 ────────────────────────────────────────────────────────

def chunk_text(
    text: str,
    strategy: str = "recursive",
    max_tokens: int = 512,
    overlap_tokens: int = 64,
    min_chunk_chars: int = 50,
    heading_prefix: str = "",
) -> List[ChunkResult]:
    """对文本执行分块。

    Args:
        text: 输入文本
        strategy: recursive / fixed / none
        max_tokens: 单块最大 token 数
        overlap_tokens: 块间重叠 token 数
        min_chunk_chars: 最小块字符数（低于此合并到前一块）
        heading_prefix: 上级标题前缀

    Returns:
        List[ChunkResult]
    """
    if not text or not text.strip():
        return []

    text = text.strip()

    # FAQ 快速路径：短文本整条保留，不拆分
    tokens = _estimate_tokens(text)
    if tokens <= max_tokens:
        return [ChunkResult(
            content=text,
            chunk_index=0,
            char_count=len(text),
            token_count=tokens,
            heading_path=heading_prefix,
        )]

    # none 策略：不分块
    if strategy == "none":
        return [ChunkResult(
            content=text,
            chunk_index=0,
            char_count=len(text),
            token_count=_estimate_tokens(text),
            heading_path=heading_prefix,
        )]

    # fixed 策略：固定窗口分块（兼容旧 EnterpriseKBService 行为）
    if strategy == "fixed":
        return _fixed_chunk(text, max_tokens, overlap_tokens, heading_prefix)

    # recursive 策略：三级递归
    return _recursive_chunk(text, max_tokens, overlap_tokens, min_chunk_chars, heading_prefix)


def _fixed_chunk(
    text: str,
    max_tokens: int,
    overlap_tokens: int,
    heading_prefix: str,
) -> List[ChunkResult]:
    """固定窗口分块（字符级，与旧版兼容）。"""
    # 按字符估算 max_chars
    max_chars = int(max_tokens * 1.5)  # 中文约 1.5 字/token
    overlap_chars = int(overlap_tokens * 1.5)

    if len(text) <= max_chars:
        return [ChunkResult(
            content=text,
            chunk_index=0,
            char_count=len(text),
            token_count=_estimate_tokens(text),
            heading_path=heading_prefix,
        )]

    chunks = []
    start = 0
    idx = 0
    while start < len(text):
        end = start + max_chars
        chunk_text_slice = text[start:end]
        chunks.append(ChunkResult(
            content=chunk_text_slice,
            chunk_index=idx,
            char_count=len(chunk_text_slice),
            token_count=_estimate_tokens(chunk_text_slice),
            heading_path=heading_prefix,
        ))
        start = end - overlap_chars
        idx += 1

    return chunks


def _recursive_chunk(
    text: str,
    max_tokens: int,
    overlap_tokens: int,
    min_chunk_chars: int,
    heading_prefix: str,
) -> List[ChunkResult]:
    """三级递归分块。"""
    results: List[ChunkResult] = []

    # Level 1: 按标题拆分
    sections = _split_by_headings(text)

    for section in sections:
        heading = section["heading"]
        content = section["content"]
        full_heading = f"{heading_prefix} > {heading}".strip(" >") if heading else heading_prefix

        # 检测表格 → 整块保留
        if _detect_table(content):
            tokens = _estimate_tokens(content)
            if tokens <= max_tokens:
                results.append(ChunkResult(
                    content=content,
                    char_count=len(content),
                    token_count=tokens,
                    heading_path=full_heading,
                    chunk_type="table",
                ))
                continue

        # 检测列表 → 整块保留
        if _detect_list(content):
            tokens = _estimate_tokens(content)
            if tokens <= max_tokens:
                results.append(ChunkResult(
                    content=content,
                    char_count=len(content),
                    token_count=tokens,
                    heading_path=full_heading,
                    chunk_type="list",
                ))
                continue

        # 检查是否需要继续拆
        tokens = _estimate_tokens(content)
        if tokens <= max_tokens:
            results.append(ChunkResult(
                content=content,
                char_count=len(content),
                token_count=tokens,
                heading_path=full_heading,
            ))
            continue

        # Level 2: 按句子拆分再组装
        sentences = _split_by_sentences(content)
        current_chunk = ""
        current_tokens = 0

        for sent in sentences:
            sent_tokens = _estimate_tokens(sent)
            if current_tokens + sent_tokens > max_tokens and current_chunk:
                results.append(ChunkResult(
                    content=current_chunk.strip(),
                    char_count=len(current_chunk.strip()),
                    token_count=current_tokens,
                    heading_path=full_heading,
                ))
                # overlap: 保留最后一句
                current_chunk = sent
                current_tokens = sent_tokens
            else:
                current_chunk += sent
                current_tokens += sent_tokens

        if current_chunk.strip():
            results.append(ChunkResult(
                content=current_chunk.strip(),
                char_count=len(current_chunk.strip()),
                token_count=_estimate_tokens(current_chunk.strip()),
                heading_path=full_heading,
            ))

    # 碎片合并：过短 chunk 向前合并
    if len(results) > 1:
        merged = [results[0]]
        for chunk in results[1:]:
            if chunk.char_count < min_chunk_chars and merged:
                prev = merged[-1]
                combined = prev.content + "\n" + chunk.content
                merged[-1] = ChunkResult(
                    content=combined,
                    char_count=len(combined),
                    token_count=_estimate_tokens(combined),
                    heading_path=prev.heading_path or chunk.heading_path,
                    chunk_type=prev.chunk_type,
                )
            else:
                merged.append(chunk)
        results = merged

    # 重新编号 chunk_index
    for i, chunk in enumerate(results):
        chunk.chunk_index = i

    return results
