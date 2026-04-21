# -*- coding: utf-8 -*-
"""backend/knowledge/text_cleaner.py — 文本清洗 Pipeline

8 步清洗流程，每步独立可配置：
  1. Unicode 归一化 (NFKC)
  2. 不可见字符清除
  3. 多余空白压缩
  4. 乱码行过滤
  5. 页眉页脚去除
  6. 重复段落去重
  7. URL/Email 脱敏（可选）
  8. 首尾空白修剪
"""
from __future__ import annotations

import re
import unicodedata
from typing import Callable, List, Optional

from loguru import logger


# ── 单步清洗函数 ──────────────────────────────────────────────────

def _normalize_unicode(text: str) -> str:
    """NFKC 归一化：统一全角/半角、兼容字符。"""
    return unicodedata.normalize("NFKC", text)


def _remove_invisible(text: str) -> str:
    """移除不可见控制字符（保留换行和制表符）。"""
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)


def _compress_whitespace(text: str) -> str:
    """压缩连续空白：多个空格→单空格，多个空行→双换行。"""
    text = re.sub(r"[^\S\n]+", " ", text)  # 非换行空白 → 单空格
    text = re.sub(r"\n{3,}", "\n\n", text)  # 3+ 换行 → 双换行
    return text


def _filter_garbled(text: str) -> str:
    """过滤乱码行：单行中非中日韩/ASCII/标点比例 > 40% 视为乱码。"""
    lines = text.split("\n")
    clean_lines = []
    for line in lines:
        if not line.strip():
            clean_lines.append(line)
            continue
        total = len(line.strip())
        if total == 0:
            continue
        # 保留：中文 + ASCII 字母数字 + 常见标点
        keep = len(re.findall(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffefa-zA-Z0-9\s,.;:!?()（）【】《》""''、。！？，；：—\t-]", line))
        ratio = keep / total
        if ratio >= 0.6:
            clean_lines.append(line)
    return "\n".join(clean_lines)


def _remove_headers_footers(text: str) -> str:
    """去除常见页眉页脚模式。"""
    # 匹配 "第X页" "Page X" 等
    text = re.sub(r"^[—\-\s]*第?\s*\d+\s*页?[—\-\s]*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[—\-\s]*Page\s*\d+\s*of\s*\d+[—\-\s]*$", "", text, flags=re.MULTILINE | re.IGNORECASE)
    return text


def _deduplicate_paragraphs(text: str) -> str:
    """去重连续重复的段落。"""
    paragraphs = text.split("\n\n")
    deduped = []
    prev = None
    for p in paragraphs:
        stripped = p.strip()
        if stripped and stripped != prev:
            deduped.append(p)
            prev = stripped
        elif not stripped:
            deduped.append(p)
    return "\n\n".join(deduped)


def _filter_short_lines(text: str, min_chars: int = 3) -> str:
    """过滤极短无意义行（< min_chars 字符），保留空行和标题行。"""
    lines = text.split("\n")
    result = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            result.append(line)
            continue
        # 保留标题行（以 # 或 数字. 开头）
        if stripped.startswith("#") or re.match(r"^\d+[\.\.、]", stripped):
            result.append(line)
            continue
        if len(stripped) >= min_chars:
            result.append(line)
    return "\n".join(result)


def _sanitize_urls_emails(text: str) -> str:
    """URL → [链接], Email → [邮箱]"""
    text = re.sub(r"https?://[^\s<>\"']+", "[链接]", text)
    text = re.sub(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", "[邮箱]", text)
    return text


def _trim(text: str) -> str:
    return text.strip()


# ── Pipeline 编排 ─────────────────────────────────────────────────

_DEFAULT_STEPS: List[Callable[[str], str]] = [
    _normalize_unicode,
    _remove_invisible,
    _compress_whitespace,
    _filter_garbled,
    _remove_headers_footers,
    _deduplicate_paragraphs,
    _filter_short_lines,
    _sanitize_urls_emails,
    _trim,
]


def clean_text(
    text: str,
    steps: Optional[List[Callable[[str], str]]] = None,
    skip_url_sanitize: bool = False,
) -> str:
    """执行文本清洗 Pipeline。

    Args:
        text: 原始文本
        steps: 自定义步骤列表，None=使用默认 8 步
        skip_url_sanitize: 是否跳过 URL/Email 脱敏

    Returns:
        清洗后文本
    """
    if not text:
        return ""

    pipeline = steps if steps is not None else list(_DEFAULT_STEPS)

    if skip_url_sanitize and _sanitize_urls_emails in pipeline:
        pipeline = [s for s in pipeline if s is not _sanitize_urls_emails]

    for step_fn in pipeline:
        try:
            text = step_fn(text)
        except Exception as e:
            logger.warning(f"[TextCleaner] step {step_fn.__name__} failed: {e}")

    return text
