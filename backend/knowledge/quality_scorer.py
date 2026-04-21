# -*- coding: utf-8 -*-
"""backend/knowledge/quality_scorer.py — 文档质量评分

四维评分体系（每项 0~1，加权平均）：
  1. 长度充分度 (length)     — 文本长度是否足够
  2. 信息密度 (density)      — 有效中文/字母 vs 总字符
  3. 结构完整度 (structure)   — 段落数、标题标记
  4. 重复度反向 (uniqueness)  — 去重后内容占比
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class QualityReport:
    """质量评分结果"""
    score: float           # 加权总分 0~1
    length_score: float
    density_score: float
    structure_score: float
    uniqueness_score: float
    blacklist_score: float = 1.0  # 1.0=无命中, 越低越差
    blacklist_hits: list = None   # 命中的黑名单词
    char_count: int = 0
    verdict: str = "accept"       # accept / warning / reject


# ── 评分权重 ──────────────────────────────────────────────────────

_W_LENGTH = 0.15
_W_DENSITY = 0.25
_W_STRUCTURE = 0.20
_W_UNIQUENESS = 0.25
_W_BLACKLIST = 0.15

# ── 阈值 ─────────────────────────────────────────────────────────

_MIN_CHARS = 20          # 低于此长度直接 reject
_OPTIMAL_CHARS = 500     # 达到此长度 length_score = 1.0

# 黑名单词：命中越多扣分越多
_BLACKLIST_WORDS = [
    "TODO", "FIXME", "HACK", "XXX",
    "测试数据", "此处填写", "待补充", "暂无", "占位", "示例文本",
    "lorem ipsum", "hello world", "asdf", "test",
    "广告合作", "点击领取", "免费试用", "限时优惠", "扫码关注",
    "仅供参考", "请忽略", "草稿", "废弃",
]


def score_quality(text: str, min_score: float = 0.3) -> QualityReport:
    """对清洗后文本进行质量评分。

    Args:
        text: 清洗后文本
        min_score: 低于此分数为 reject

    Returns:
        QualityReport
    """
    if not text or not text.strip():
        return QualityReport(
            score=0.0, length_score=0.0, density_score=0.0,
            structure_score=0.0, uniqueness_score=0.0,
            char_count=0, verdict="reject",
        )

    text = text.strip()
    char_count = len(text)

    # 极短文本直接拒绝
    if char_count < _MIN_CHARS:
        return QualityReport(
            score=0.0, length_score=0.0, density_score=0.0,
            structure_score=0.0, uniqueness_score=0.0,
            char_count=char_count, verdict="reject",
        )

    # 1. 长度充分度（已排除 < _MIN_CHARS）
    if char_count >= _OPTIMAL_CHARS:
        length_score = 1.0
    else:
        length_score = (char_count - _MIN_CHARS) / (_OPTIMAL_CHARS - _MIN_CHARS)

    # 2. 信息密度：有效字符（中文+字母+数字）占比
    meaningful = len(re.findall(r"[\u4e00-\u9fffa-zA-Z0-9]", text))
    density_score = min(meaningful / max(char_count, 1), 1.0)

    # 3. 结构完整度
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    has_headings = bool(re.search(r"^#{1,6}\s|^第[一二三四五六七八九十]+[章节条款]|^\d+[\.\、]", text, re.MULTILINE))
    para_score = min(len(paragraphs) / 5, 1.0)
    structure_score = para_score * 0.7 + (0.3 if has_headings else 0.0)

    # 4. 去重度：按句去重后 unique 占比
    sentences = re.split(r"[。！？\n]", text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 5]
    unique_count = len(set(sentences))
    total_count = max(len(sentences), 1)
    uniqueness_score = unique_count / total_count

    # 5. 黑名单词检测
    text_lower = text.lower()
    hits = [w for w in _BLACKLIST_WORDS if w.lower() in text_lower]
    # 每命中 1 个扣 0.2，最多扣到 0
    blacklist_score = max(1.0 - len(hits) * 0.2, 0.0)

    # 加权
    score = round(
        _W_LENGTH * length_score
        + _W_DENSITY * density_score
        + _W_STRUCTURE * structure_score
        + _W_UNIQUENESS * uniqueness_score
        + _W_BLACKLIST * blacklist_score,
        3,
    )

    if score >= 0.6:
        verdict = "accept"
    elif score >= min_score:
        verdict = "warning"
    else:
        verdict = "reject"

    return QualityReport(
        score=score,
        length_score=round(length_score, 3),
        density_score=round(density_score, 3),
        structure_score=round(structure_score, 3),
        uniqueness_score=round(uniqueness_score, 3),
        blacklist_score=round(blacklist_score, 3),
        blacklist_hits=hits if hits else None,
        char_count=char_count,
        verdict=verdict,
    )
