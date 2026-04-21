# -*- coding: utf-8 -*-
"""测试知识库文档处理管线 5 项优化。

覆盖：
  1. text_cleaner — 极短行过滤
  2. quality_scorer — 黑名单词检测
  3. content_guard — PII 脱敏 mask_pii
  4. doc_processor — 文件安全校验 / PII 策略 / 审计日志
"""
import sys
import os
from pathlib import Path

import pytest

# 保证 backend 包可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


# ═══════════════════════════════════════════════════════════
#  1. text_cleaner: _filter_short_lines
# ═══════════════════════════════════════════════════════════

from backend.knowledge.text_cleaner import clean_text, _filter_short_lines


class TestFilterShortLines:
    def test_removes_single_char_lines(self):
        text = "正常内容行\n。\n另一行正常内容"
        result = _filter_short_lines(text)
        assert "。" not in result.split("\n")

    def test_keeps_empty_lines(self):
        text = "第一行\n\n第三行"
        result = _filter_short_lines(text)
        assert result == text

    def test_keeps_heading_lines(self):
        text = "# 标\n1. A\n正文内容正常"
        result = _filter_short_lines(text)
        assert "# 标" in result
        assert "1. A" in result

    def test_keeps_normal_short_line(self):
        text = "你好啊\n这很正常"
        result = _filter_short_lines(text)
        assert "你好啊" in result

    def test_integrated_in_pipeline(self):
        text = "正常的段落内容，足够长。\n，\n另一段正常内容也足够长。"
        cleaned = clean_text(text)
        lines = [l for l in cleaned.split("\n") if l.strip()]
        # 单独的 "，" 应该被过滤
        assert all(len(l.strip()) >= 3 for l in lines)


# ═══════════════════════════════════════════════════════════
#  2. quality_scorer: 黑名单词
# ═══════════════════════════════════════════════════════════

from backend.knowledge.quality_scorer import score_quality


class TestBlacklistScoring:
    def test_clean_text_no_penalty(self):
        text = "这是一段关于客户退款政策的正式文档内容。" * 10
        report = score_quality(text)
        assert report.blacklist_score == 1.0
        assert report.blacklist_hits is None

    def test_single_blacklist_hit(self):
        text = "这是测试数据，仅用于验证功能。" * 10
        report = score_quality(text)
        assert report.blacklist_score < 1.0
        assert "测试数据" in report.blacklist_hits

    def test_multiple_blacklist_hits(self):
        text = "TODO 此处填写待补充内容，请忽略本段。" * 5
        report = score_quality(text)
        # 命中 4+ 个词，score 应该接近 0
        assert report.blacklist_score <= 0.2
        assert len(report.blacklist_hits) >= 4

    def test_blacklist_case_insensitive(self):
        text = "这段包含 todo 和 fixme 标记的内容需要清理。" * 10
        report = score_quality(text)
        assert report.blacklist_hits is not None
        lowered = [h.lower() for h in report.blacklist_hits]
        assert "todo" in lowered or "fixme" in lowered


# ═══════════════════════════════════════════════════════════
#  3. content_guard: mask_pii
# ═══════════════════════════════════════════════════════════

from backend.knowledge.content_guard import detect_pii, mask_pii


class TestMaskPII:
    def test_mask_phone(self):
        text = "联系电话：13812345678，请拨打。"
        masked = mask_pii(text)
        assert "13812345678" not in masked
        assert "[手机号]" in masked

    def test_mask_id_card(self):
        text = "身份证号：110101199001011234。"
        masked = mask_pii(text)
        assert "110101199001011234" not in masked
        assert "[身份证号]" in masked

    def test_mask_email(self):
        text = "邮箱是 test@example.com 请联系。"
        masked = mask_pii(text)
        assert "test@example.com" not in masked
        assert "[邮箱]" in masked

    def test_mask_bank_card(self):
        text = "银行卡号 6222021234567890123 转账。"
        masked = mask_pii(text)
        assert "6222021234567890123" not in masked
        assert "[银行卡号]" in masked

    def test_no_pii_unchanged(self):
        text = "这是一段没有任何敏感信息的正常文本。"
        assert mask_pii(text) == text

    def test_empty_input(self):
        assert mask_pii("") == ""


# ═══════════════════════════════════════════════════════════
#  4. doc_processor: 完整管线测试
# ═══════════════════════════════════════════════════════════

from backend.knowledge.doc_processor import process_document, StepLog


class TestDocProcessorPipeline:
    """纯文本输入（raw_text）场景，不依赖外部服务。"""

    def test_basic_success(self):
        text = "客户退款政策\n\n七天无理由退货适用于所有线上订单。" * 3
        r = process_document(raw_text=text, title="退款政策")
        assert r.success is True
        assert len(r.chunks) > 0
        assert r.content_clean
        assert r.quality is not None
        assert r.quality.verdict in ("accept", "warning")

    def test_step_logs_present(self):
        text = "测试审计日志功能的正常文档内容。" * 10
        r = process_document(raw_text=text)
        assert len(r.step_logs) > 0
        step_names = [sl.step for sl in r.step_logs]
        assert "parse" in step_names
        assert "clean" in step_names
        assert "quality" in step_names
        assert "chunk" in step_names
        for sl in r.step_logs:
            assert sl.elapsed_ms >= 0

    def test_step_logs_on_ocr_skip(self):
        text = "正常内容不需要 OCR 处理。" * 10
        r = process_document(raw_text=text)
        ocr_logs = [sl for sl in r.step_logs if sl.step == "ocr"]
        assert len(ocr_logs) == 1
        assert ocr_logs[0].status == "skipped"

    def test_pii_policy_warn(self):
        text = "客户电话 13900001111 请联系。" * 5
        r = process_document(raw_text=text, pii_policy="warn")
        assert r.success is True
        assert any("pii_detected" in w for w in r.warnings)
        # 原文未脱敏
        assert "13900001111" in r.content_clean

    def test_pii_policy_reject(self):
        text = "客户电话 13900001111 请联系。" * 5
        r = process_document(raw_text=text, pii_policy="reject")
        assert r.success is False
        assert "pii_rejected" in r.error
        pii_logs = [sl for sl in r.step_logs if sl.step == "pii"]
        assert any(sl.status == "failed" for sl in pii_logs)

    def test_pii_policy_mask(self):
        text = "客户电话 13900001111 需要保护。" * 5
        r = process_document(raw_text=text, pii_policy="mask")
        assert r.success is True
        assert "13900001111" not in r.content_clean
        assert any("pii_masked" in w for w in r.warnings)

    def test_empty_input_rejected(self):
        r = process_document(raw_text="")
        assert r.success is False

    def test_no_input_rejected(self):
        r = process_document()
        assert r.success is False
        assert "no_input" in r.error

    def test_quality_reject_short(self):
        r = process_document(raw_text="短")
        assert r.success is False

    def test_file_not_found(self):
        r = process_document(file_path=Path("/nonexistent/file.txt"))
        assert r.success is False
        assert "file_safety_rejected" in (r.error or "")


# ═══════════════════════════════════════════════════════════
#  5. chunk_engine: 回归测试
# ═══════════════════════════════════════════════════════════

from backend.knowledge.chunk_engine import chunk_text


class TestChunkEngine:
    def test_recursive_basic(self):
        text = "这是一段足够长的内容。" * 50
        chunks = chunk_text(text, strategy="recursive", max_tokens=64)
        assert len(chunks) > 1
        for c in chunks:
            assert c.chunk_index >= 0
            assert c.char_count > 0

    def test_none_strategy(self):
        text = "不分块的文本。" * 10
        chunks = chunk_text(text, strategy="none")
        assert len(chunks) == 1

    def test_empty_text(self):
        assert chunk_text("") == []
