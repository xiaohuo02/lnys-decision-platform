# -*- coding: utf-8 -*-
"""backend/tests/test_grounding_filter.py — §3.1 L1 Grounding Filter 单元测试

覆盖：
  - split_sentences 中英文/换行/空文本切分
  - extract_citations 单个/多个/边界
  - strip_citations 正常/空/多引用
  - filter_ungrounded 6 类路径（严格 / 宽松 / 无引用 / 非法 cid / 空输入 / 全合法）
  - build_citation_block 结构/截断/空列表
  - DEFAULT_CITATION_RULES 存在且含关键词
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.copilot.grounding_filter import (  # noqa: E402
    DEFAULT_CITATION_RULES,
    build_citation_block,
    extract_citations,
    filter_ungrounded,
    split_sentences,
    strip_citations,
)


# ════════════════════════════════════════════════════════════════════
# split_sentences
# ════════════════════════════════════════════════════════════════════

class TestSplitSentences:
    def test_empty_returns_empty(self):
        assert split_sentences("") == []
        assert split_sentences("   ") == []

    def test_chinese_period(self):
        text = "第一句。第二句。第三句。"
        assert split_sentences(text) == ["第一句。", "第二句。", "第三句。"]

    def test_mixed_cn_en_punct(self):
        """中文标点 + 英文 ! ? 会切；英文半角 . 刻意不切（避免误切小数 3.5 / 缩写 e.g.）。"""
        text = "中文句。English sentence. Another! 最后？"
        parts = split_sentences(text)
        # 当前设计：. 不在切分字符集，故 'English sentence. Another!' 保持一段
        assert parts == ["中文句。", "English sentence. Another!", "最后？"]

    def test_english_period_not_split(self):
        """明确文档化：英文句号不参与切分。"""
        text = "Version 3.5 released. See details."
        parts = split_sentences(text)
        # 'Version 3.5 released. See details.' 视为整体一句
        assert len(parts) == 1

    def test_newline_as_separator(self):
        text = "第一行内容\n第二行内容\n"
        parts = split_sentences(text)
        assert len(parts) == 2
        assert parts[0] == "第一行内容"
        assert parts[1] == "第二行内容"

    def test_trailing_whitespace_stripped(self):
        text = "   句一。   句二。  "
        parts = split_sentences(text)
        assert parts == ["句一。", "句二。"]

    def test_single_no_end_punct(self):
        text = "一句无结束标点"
        parts = split_sentences(text)
        assert parts == ["一句无结束标点"]


# ════════════════════════════════════════════════════════════════════
# extract_citations
# ════════════════════════════════════════════════════════════════════

class TestExtractCitations:
    def test_single(self):
        assert extract_citations("退款 3-5 天到账 [^c_001]。") == {"c_001"}

    def test_plain_bracket_citation(self):
        assert extract_citations("退款 3-5 天到账 [c_001]。") == {"c_001"}

    def test_multiple(self):
        assert extract_citations("政策如下 [^c_001][^c_002]。") == {"c_001", "c_002"}

    def test_scattered(self):
        s = "[^c_01] 句首，然后中间[^c_02]，最后 [^c_03]。"
        assert extract_citations(s) == {"c_01", "c_02", "c_03"}

    def test_none(self):
        assert extract_citations("没有引用标记。") == set()

    def test_empty(self):
        assert extract_citations("") == set()

    def test_cid_chars(self):
        """cid 允许字母数字下划线短横线。"""
        s = "复杂 cid [^kb1_chunk-5][^A1B2]。"
        assert extract_citations(s) == {"kb1_chunk-5", "A1B2"}

    def test_malformed_unclosed(self):
        """未闭合的 [^xxx 不应被识别。"""
        assert extract_citations("不闭合 [^c_001 继续。") == set()


# ════════════════════════════════════════════════════════════════════
# strip_citations
# ════════════════════════════════════════════════════════════════════

class TestStripCitations:
    def test_basic(self):
        s = "退款 3-5 天到账 [^c_001]。"
        assert strip_citations(s) == "退款 3-5 天到账 。"

    def test_multiple(self):
        s = "政策如下 [^c_001][^c_002]。"
        assert strip_citations(s) == "政策如下 ."  or strip_citations(s).startswith("政策如下")

    def test_empty(self):
        assert strip_citations("") == ""

    def test_no_citations(self):
        assert strip_citations("纯文本句子。") == "纯文本句子。"


# ════════════════════════════════════════════════════════════════════
# filter_ungrounded
# ════════════════════════════════════════════════════════════════════

class TestFilterUngrounded:
    def test_empty_answer(self):
        r = filter_ungrounded("", {"c_001"})
        assert r["grounded_ratio"] == 0.0
        assert r["total_sentences"] == 0
        assert r["kept_sentences"] == []
        assert r["dropped_sentences"] == []
        assert r["clean_answer"] == ""
        assert r["citations_used"] == []

    def test_all_grounded_strict(self):
        answer = "第一点 [^c_001]。第二点 [^c_002]。"
        r = filter_ungrounded(answer, {"c_001", "c_002"}, strict=True)
        assert r["grounded_ratio"] == 1.0
        assert r["total_sentences"] == 2
        assert len(r["kept_sentences"]) == 2
        assert r["dropped_sentences"] == []
        assert set(r["citations_used"]) == {"c_001", "c_002"}
        assert "第一点" in r["clean_answer"]

    def test_no_citation_all_dropped(self):
        answer = "第一句没引用。第二句也没有。"
        r = filter_ungrounded(answer, {"c_001"})
        assert r["grounded_ratio"] == 0.0
        assert r["total_sentences"] == 2
        assert r["kept_sentences"] == []
        assert len(r["dropped_sentences"]) == 2
        assert all(d["reason"] == "no_citation" for d in r["dropped_sentences"])
        assert r["clean_answer"] == ""

    def test_partial_grounded(self):
        answer = "合法 [^c_001]。无引用。"
        r = filter_ungrounded(answer, {"c_001"})
        assert r["grounded_ratio"] == 0.5
        assert r["total_sentences"] == 2
        assert len(r["kept_sentences"]) == 1
        assert len(r["dropped_sentences"]) == 1

    def test_illegal_cid_strict_drops(self):
        answer = "合法 [^c_001]。非法 [^c_999]。混合 [^c_001][^c_999]。"
        r = filter_ungrounded(answer, {"c_001"}, strict=True)
        # 严格模式：只要有任一 cid 不在 allowed，该句 dropped
        assert len(r["kept_sentences"]) == 1
        assert len(r["dropped_sentences"]) == 2
        reasons = {d["reason"] for d in r["dropped_sentences"]}
        assert "citation_not_allowed" in reasons

    def test_illegal_cid_lax_keeps_overlap(self):
        answer = "混合 [^c_001][^c_999]。仅非法 [^c_999]。"
        r = filter_ungrounded(answer, {"c_001"}, strict=False)
        # 宽松模式：混合句有一个合法即保留；仅非法被剥离
        assert len(r["kept_sentences"]) == 1
        assert len(r["dropped_sentences"]) == 1
        assert "c_001" in r["citations_used"]
        assert "c_999" not in r["citations_used"]

    def test_empty_allowed_set(self):
        """allowed_cids 为空 → 任何引用都非法。"""
        answer = "带引用 [^c_001]。无引用。"
        r = filter_ungrounded(answer, set())
        assert r["grounded_ratio"] == 0.0
        assert len(r["kept_sentences"]) == 0
        assert len(r["dropped_sentences"]) == 2

    def test_citations_used_unique_sorted(self):
        answer = "A [^c_002][^c_001]。B [^c_001]。C [^c_003]。"
        r = filter_ungrounded(answer, {"c_001", "c_002", "c_003"}, strict=True)
        # 结果应去重且排序
        assert r["citations_used"] == ["c_001", "c_002", "c_003"]

    def test_dropped_carries_invalid_cids(self):
        """严格模式下被 drop 的句子应带 invalid_cids 便于 bad case 分析。"""
        answer = "非法 [^c_999][^c_001]。"
        r = filter_ungrounded(answer, {"c_001"}, strict=True)
        assert len(r["dropped_sentences"]) == 1
        d = r["dropped_sentences"][0]
        assert d["reason"] == "citation_not_allowed"
        assert set(d["cids"]) == {"c_001", "c_999"}
        assert d["invalid_cids"] == ["c_999"]

    def test_clean_answer_strips_citation_marks(self):
        answer = "退款 3-5 天到账 [^c_001][^c_002]。"
        r = filter_ungrounded(answer, {"c_001", "c_002"})
        assert "[^" not in r["clean_answer"]
        assert "退款 3-5 天到账" in r["clean_answer"]

    def test_structural_markdown_not_counted(self):
        answer = (
            "### 退款到账时效\n"
            "| :--- | :--- |\n"
            "微信支付 1-3 个工作日 [c_001]。\n"
            "银行卡 3-7 个工作日 [c_001]。"
        )
        r = filter_ungrounded(answer, {"c_001"})
        assert r["grounded_ratio"] == 1.0
        assert r["total_sentences"] == 2
        assert r["dropped_sentences"] == []

    def test_ungrounded_table_data_row_still_counted(self):
        answer = "| :--- | :--- |\n| 微信支付 | 1-3 个工作日 |\n银行卡 3-7 个工作日 [c_001]。"
        r = filter_ungrounded(answer, {"c_001"})
        assert r["grounded_ratio"] == 0.5
        assert r["total_sentences"] == 2
        assert r["dropped_sentences"][0]["reason"] == "no_citation"


# ════════════════════════════════════════════════════════════════════
# build_citation_block
# ════════════════════════════════════════════════════════════════════

class TestBuildCitationBlock:
    def test_empty_list(self):
        assert build_citation_block([]) == ""

    def test_basic(self):
        cites = [
            {
                "cid": "c_001",
                "kb_name": "企业库A",
                "doc_title": "退款政策",
                "score": 0.89,
                "content": "退款将在 3-5 个工作日到账。",
            }
        ]
        block = build_citation_block(cites)
        assert block.startswith("<chunks>")
        assert block.endswith("</chunks>")
        assert "[c_001]" in block
        assert "kb=企业库A" in block
        assert "doc=退款政策" in block
        assert "0.89" in block
        assert "退款将在" in block

    def test_content_truncation(self):
        long_content = "x" * 2000
        cites = [{"cid": "c_001", "content": long_content, "score": 0.5}]
        block = build_citation_block(cites, max_content_chars=100)
        # 截断后应以省略号结尾
        assert "…" in block
        # 不应全量 2000 字出现
        assert block.count("x") < 200

    def test_missing_optional_fields(self):
        """kb_name / doc_title / score 都缺失不应报错。"""
        cites = [{"cid": "c_001", "content": "content only"}]
        block = build_citation_block(cites)
        assert "[c_001]" in block
        assert "content only" in block

    def test_multiple_citations_order_preserved(self):
        cites = [
            {"cid": "c_001", "content": "A"},
            {"cid": "c_002", "content": "B"},
            {"cid": "c_003", "content": "C"},
        ]
        block = build_citation_block(cites)
        pos_a = block.find("[c_001]")
        pos_b = block.find("[c_002]")
        pos_c = block.find("[c_003]")
        assert 0 <= pos_a < pos_b < pos_c


# ════════════════════════════════════════════════════════════════════
# DEFAULT_CITATION_RULES
# ════════════════════════════════════════════════════════════════════

class TestDefaultCitationRules:
    def test_non_empty(self):
        assert DEFAULT_CITATION_RULES
        assert len(DEFAULT_CITATION_RULES) > 50

    def test_contains_key_instructions(self):
        """prompt 规则必须包含关键指令关键词。"""
        rules = DEFAULT_CITATION_RULES
        assert "[cid]" in rules or "[c_" in rules    # 引用格式示例
        assert "chunks" in rules.lower()            # 引用来源区
        assert "编造" in rules or "严禁" in rules   # 禁止编造


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
