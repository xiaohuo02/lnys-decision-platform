# -*- coding: utf-8 -*-
"""backend/copilot/grounding_filter.py — §3.1 L1 强制引用后处理

职责：
  1. 按中英文句号切分 LLM 输出文本
  2. 从每句提取 [^cid] 引用标记（Markdown 脚注风格）
  3. 过滤未引用 / 引用不在 allowed_cids 的句子
  4. 计算 grounded_ratio，供 engine / abstain 决策使用

格式约定：
  - 引用标记：``[^c_001]``、``[^c_001][^c_002]``（连续多个）
  - cid 内容允许数字、字母、下划线、短横线（为了兼容 ``c_001``、``kb1_chunk_5``）
  - 支持句末标点：`。！？!?` 以及换行（为 Markdown 列表/表格做保护）

设计约束：
  - 纯函数模块，不依赖 backend.config 或其他重型模块，便于单测
  - LLM 可能把 ``[^cid]`` 写在句中或句末，都要识别；位置不限
  - strict=True：句子所有 cid 必须 ∈ allowed_cids 才保留
    strict=False：至少一个 cid 命中即可（更宽松，灰度阶段可用）
  - 空文本、空 allowed_cids 场景全部有明确返回，**绝不抛异常**
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

# ════════════════════════════════════════════════════════════════════
# 正则
# ════════════════════════════════════════════════════════════════════

# 匹配 [^cid] 形式的引用标记；cid 允许字母数字下划线短横线
_FOOTNOTE_CITATION_RE = re.compile(r"\[\^([A-Za-z0-9_\-]+)\]")
_PLAIN_CITATION_RE = re.compile(r"\[((?:c|C)_[A-Za-z0-9_\-]+)\]")

# 中英文句末标点作为切分点（保留标点）
# 切分字符集：全角 `。！？` + 半角 `!?` + 换行。
# 刻意 **不** 把半角 `.` 放进来：避免误切小数（3.5）、英文缩写（e.g. / Ver.）、
# 文件名（config.py）。在 KB 问答场景下 LLM 以中文为主，少量英文段落保持整体
# 可读性比精细切英文句子更重要。
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?\n])")


# ════════════════════════════════════════════════════════════════════
# 公开函数
# ════════════════════════════════════════════════════════════════════

def split_sentences(text: str) -> List[str]:
    """按中英文句末标点切分为句子列表。

    规则：
      - 保留句末标点
      - 去掉前后空白
      - 空段忽略
      - Markdown 列表项（以 `-` / `*` / `1.` 开头）被视为独立"句"

    返回：非空句子列表。
    """
    if not text or not text.strip():
        return []
    parts = _SENTENCE_SPLIT_RE.split(text)
    return [p.strip() for p in parts if p and p.strip()]


def extract_citations(sentence: str) -> Set[str]:
    """从一句话里提取所有 [^cid] 引用标记，返回 cid 集合。"""
    if not sentence:
        return set()
    return set(_FOOTNOTE_CITATION_RE.findall(sentence)) | set(_PLAIN_CITATION_RE.findall(sentence))


def strip_citations(sentence: str) -> str:
    """去掉 [^cid] 标记，只保留纯文本（用于 clean_answer 展示）。"""
    if not sentence:
        return ""
    # 去标记后可能有多余空格，收尾再做 rstrip
    cleaned = _FOOTNOTE_CITATION_RE.sub("", sentence)
    cleaned = _PLAIN_CITATION_RE.sub("", cleaned)
    return cleaned.rstrip()


def _is_structural_markdown(sentence: str) -> bool:
    s = (sentence or "").strip()
    if not s:
        return True
    if "|" in s and not extract_citations(s):
        cells = [c.strip() for c in s.strip("|").split("|")]
        if cells and all(cells) and all(len(c) <= 8 for c in cells):
            if not any(re.search(r"\d|%|￥|¥|\.", c) for c in cells):
                return True
    if re.fullmatch(r"#{1,6}\s+.+", s):
        return True
    if re.fullmatch(r"\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?", s):
        return True
    if "|" in s and re.fullmatch(r"\|?\s*[:\-|\s]+\|?", s):
        return True
    return False


def _is_exempt_chatter(sentence: str) -> bool:
    s = (sentence or "").strip()
    if not s or extract_citations(s):
        return False
    if len(s) > 100:
        return False
    return s.startswith(("您好", "你好", "关于您询问")) or s.endswith(("如下：", "如下:", "处理：", "处理:"))


def filter_ungrounded(
    answer: str,
    allowed_cids: Set[str],
    *,
    strict: bool = True,
) -> Dict[str, Any]:
    """过滤未引用 / 引用非法的句子，计算 grounded_ratio。

    参数：
        answer: LLM 原始输出（应包含 [^cid] 引用标记）
        allowed_cids: 合法 cid 集合（通常来自 kb_rag_skill 的 hits）
        strict: True=句子所有 cid 必须 ∈ allowed_cids（默认，严格）；
                False=句子至少有一个 cid ∈ allowed_cids 即保留（宽松）

    返回：
        {
          "clean_answer": str,          # 剥离 [^cid] 后的纯文本答复
          "raw_answer": str,            # LLM 原始输出
          "kept_sentences": List[str],  # 保留的句子原文（含 cid）
          "dropped_sentences": List[{text, reason, ...}],
          "grounded_ratio": float,      # kept / total，四舍五入到 4 位
          "total_sentences": int,
          "citations_used": List[str],  # 实际被引用到的 cid（升序）
        }

    注意：allowed_cids 可为 set 或 list；内部统一为 set。
    """
    raw = answer or ""
    sentences = [
        s for s in split_sentences(raw)
        if not _is_structural_markdown(s) and not _is_exempt_chatter(s)
    ]
    total = len(sentences)

    allowed: Set[str] = set(allowed_cids or [])

    if total == 0:
        return {
            "clean_answer": "",
            "raw_answer": raw,
            "kept_sentences": [],
            "dropped_sentences": [],
            "grounded_ratio": 0.0,
            "total_sentences": 0,
            "citations_used": [],
        }

    kept: List[str] = []
    dropped: List[Dict[str, Any]] = []
    used_cids: Set[str] = set()

    for sent in sentences:
        cids = extract_citations(sent)

        # 未引用
        if not cids:
            dropped.append({"text": sent, "reason": "no_citation"})
            continue

        # 严格模式：所有 cid 必须合法
        if strict:
            if cids.issubset(allowed):
                kept.append(sent)
                used_cids.update(cids)
            else:
                invalid = cids - allowed
                dropped.append({
                    "text": sent,
                    "reason": "citation_not_allowed",
                    "cids": sorted(cids),
                    "invalid_cids": sorted(invalid),
                })
        # 宽松模式：至少一个 cid 合法
        else:
            overlap = cids & allowed
            if overlap:
                kept.append(sent)
                used_cids.update(overlap)
            else:
                dropped.append({
                    "text": sent,
                    "reason": "no_allowed_citation",
                    "cids": sorted(cids),
                })

    # clean_answer: 保留顺序，逐句去 cid 后用换行或空串拼接
    # 由于 split 时已保留句末标点，这里直接用空串拼，视觉接续
    clean_parts = [strip_citations(s) for s in kept]
    clean_answer = "".join(clean_parts).strip()

    return {
        "clean_answer": clean_answer,
        "raw_answer": raw,
        "kept_sentences": kept,
        "dropped_sentences": dropped,
        "grounded_ratio": round(len(kept) / total, 4) if total else 0.0,
        "total_sentences": total,
        "citations_used": sorted(used_cids),
    }


def build_citation_block(
    citations: List[Dict[str, Any]],
    max_content_chars: int = 500,
) -> str:
    """把 kb_rag_skill 传过来的 citations 列表渲染成 LLM 可读的 <chunks> 块。

    用于 engine._synthesize_answer 构造 prompt。

    参数：
        citations: [{cid, chunk_id, kb_name, doc_title, content, score}, ...]
        max_content_chars: 每段 content 截断长度，防止 prompt 过长

    返回：
        ```
        <chunks>
        [c_001] (kb=企业库A, doc=退款政策, score=0.89)
        退款将在 3-5 个工作日到账...

        [c_002] (...)
        ...
        </chunks>
        ```
    """
    if not citations:
        return ""
    lines: List[str] = ["<chunks>"]
    for c in citations:
        cid = c.get("cid") or "c_??"
        kb_name = c.get("kb_name", "") or ""
        doc_title = c.get("doc_title") or c.get("title") or ""
        score = c.get("score", 0) or 0
        content = (c.get("content") or "").strip()
        if len(content) > max_content_chars:
            content = content[:max_content_chars] + "…"
        header = f"[{cid}]"
        meta_parts = []
        if kb_name:
            meta_parts.append(f"kb={kb_name}")
        if doc_title:
            meta_parts.append(f"doc={doc_title}")
        if score:
            meta_parts.append(f"score={float(score):.2f}")
        if meta_parts:
            header += f" ({', '.join(meta_parts)})"
        lines.append(header)
        if content:
            lines.append(content)
        lines.append("")
    lines.append("</chunks>")
    return "\n".join(lines)


# 默认 Prompt 规则块（engine 使用）
DEFAULT_CITATION_RULES = (
    "\n\n## 引用规则（强制）\n"
    "1. 回答**必须仅基于下方 <chunks> 里的内容**，严禁编造或外延引申。\n"
    "2. 每一句事实陈述末尾必须用 ``[cid]`` 格式标注来源，允许多个，例如："
    "``退款在 3-5 个工作日到账 [c_001][c_002]。``\n"
    "3. 不要使用 Markdown 脚注格式 ``[^c_001]``，必须使用普通方括号 ``[c_001]``。\n"
    "4. 如果 <chunks> 里找不到能支持你答复的内容，直接写一句："
    "``现有资料未收录此信息。`` 不要带引用，也不要编造。\n"
    "5. 闲聊/打招呼/致谢类句子可不引用，但**必须放在实质答复之前或之后**，"
    "数量不超过 1 句。\n"
)
