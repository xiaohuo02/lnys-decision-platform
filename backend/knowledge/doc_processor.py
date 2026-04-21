# -*- coding: utf-8 -*-
"""backend/knowledge/doc_processor.py — 文档处理管线编排

完整流程：
  文件解析 → OCR补充 → 文本清洗 → 质量评分 → PII检测 → 分块 → 向量化
每步内置 fallback，单步失败不影响后续（降级记录到 warnings）。
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from backend.knowledge.file_parser import ParseResult, parse_file
from backend.knowledge.text_cleaner import clean_text
from backend.knowledge.quality_scorer import QualityReport, score_quality
from backend.knowledge.content_guard import PIIReport, detect_pii, mask_pii, check_file_safety
from backend.knowledge.chunk_engine import ChunkResult, chunk_text


@dataclass
class StepLog:
    """单步审计记录"""
    step: str
    status: str        # ok / skipped / fallback / failed
    elapsed_ms: float = 0.0
    detail: str = ""


@dataclass
class ProcessResult:
    """文档处理管线结果"""
    success: bool = False
    content_raw: str = ""
    content_clean: str = ""
    quality: Optional[QualityReport] = None
    pii: Optional[PIIReport] = None
    chunks: List[ChunkResult] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    step_logs: List[StepLog] = field(default_factory=list)


def process_document(
    file_path: Optional[Path] = None,
    raw_text: Optional[str] = None,
    title: str = "",
    chunk_strategy: str = "recursive",
    chunk_max_tokens: int = 512,
    chunk_overlap: int = 64,
    min_quality_score: float = 0.3,
    skip_pii: bool = False,
    pii_policy: str = "warn",
) -> ProcessResult:
    """执行完整文档处理管线。

    支持两种输入：
      - file_path: 文件路径（走解析器）
      - raw_text: 直接提供文本（FAQ手动录入场景）

    Returns:
        ProcessResult
    """
    result = ProcessResult()

    def _log(step: str, status: str, t0: float, detail: str = ""):
        result.step_logs.append(StepLog(
            step=step, status=status,
            elapsed_ms=round((time.time() - t0) * 1000, 1),
            detail=detail,
        ))

    # ── Step 1: 获取原始文本 ─────────────────────────
    t0 = time.time()
    if raw_text:
        result.content_raw = raw_text
        result.metadata["source"] = "raw_text"
        _log("parse", "ok", t0, "raw_text")
    elif file_path:
        # ── Step 0: 文件安全校验 ──────────────────────
        t_guard = time.time()
        try:
            from backend.config import settings
            guard = check_file_safety(file_path, max_size_mb=settings.KB_MAX_FILE_SIZE_MB)
            if not guard.passed:
                result.error = f"file_safety_rejected: {'; '.join(guard.errors)}"
                result.warnings.extend(guard.warnings)
                _log("file_guard", "failed", t_guard, result.error)
                return result
            if guard.warnings:
                result.warnings.extend(guard.warnings)
            if guard.mime_type:
                result.metadata["mime_type"] = guard.mime_type
            _log("file_guard", "ok", t_guard)
        except Exception as e:
            result.warnings.append(f"file_guard_fallback:{e}")
            _log("file_guard", "fallback", t_guard, str(e))

        try:
            parsed: ParseResult = parse_file(file_path)
            result.content_raw = parsed.text
            result.warnings.extend(parsed.warnings)
            result.metadata.update(parsed.metadata)
            if parsed.tables:
                result.metadata["table_count"] = len(parsed.tables)
            _log("parse", "ok", t0)
        except Exception as e:
            result.error = f"parse_failed: {e}"
            result.warnings.append(f"parse_error:{e}")
            logger.warning(f"[DocProcessor] parse failed: {e}")
            _log("parse", "failed", t0, str(e))
            return result
    else:
        result.error = "no_input: file_path or raw_text required"
        return result

    # 标题 + 内容合并（FAQ场景）
    if title and result.content_raw:
        full_text = f"{title}\n{result.content_raw}"
    else:
        full_text = result.content_raw

    if not full_text.strip():
        result.error = "empty_content"
        result.warnings.append("empty_after_parse")
        return result

    # ── Step 2: OCR 补充（PDF扫描页）────────────────
    t0 = time.time()
    needs_ocr = any("no_text_may_need_ocr" in w for w in result.warnings)
    if needs_ocr and file_path:
        try:
            from backend.knowledge.ocr_engine import OCREngine
            from backend.config import settings
            if settings.KB_OCR_ENABLED:
                engine = OCREngine.get_instance()
                if engine.available:
                    ocr_text, ocr_conf = engine.recognize_file(file_path)
                    if ocr_text.strip():
                        full_text = full_text + "\n\n" + ocr_text
                        result.metadata["ocr_confidence"] = ocr_conf
                        result.warnings.append(f"ocr_appended:conf={ocr_conf:.2f}")
                        _log("ocr", "ok", t0, f"conf={ocr_conf:.2f}")
                    else:
                        _log("ocr", "skipped", t0, "no_ocr_text")
                else:
                    _log("ocr", "skipped", t0, "engine_unavailable")
            else:
                _log("ocr", "skipped", t0, "disabled")
        except Exception as e:
            result.warnings.append(f"ocr_fallback:{e}")
            logger.debug(f"[DocProcessor] OCR fallback: {e}")
            _log("ocr", "fallback", t0, str(e))
    else:
        _log("ocr", "skipped", t0, "not_needed")

    # ── Step 3: 文本清洗 ─────────────────────────────
    t0 = time.time()
    try:
        result.content_clean = clean_text(full_text)
        _log("clean", "ok", t0)
    except Exception as e:
        result.content_clean = full_text
        result.warnings.append(f"clean_fallback:{e}")
        _log("clean", "fallback", t0, str(e))

    # ── Step 4: 质量评分 ─────────────────────────────
    t0 = time.time()
    try:
        result.quality = score_quality(result.content_clean, min_score=min_quality_score)
        if result.quality.verdict == "reject":
            result.error = f"quality_rejected:score={result.quality.score}"
            result.warnings.append(result.error)
            _log("quality", "failed", t0, f"score={result.quality.score}")
            return result
        verdict_detail = f"score={result.quality.score},verdict={result.quality.verdict}"
        if result.quality.verdict == "warning":
            result.warnings.append(f"quality_warning:score={result.quality.score}")
        _log("quality", "ok", t0, verdict_detail)
    except Exception as e:
        result.warnings.append(f"quality_fallback:{e}")
        _log("quality", "fallback", t0, str(e))

    # ── Step 5: PII 检测 + 策略执行 ───────────────
    t0 = time.time()
    if not skip_pii:
        try:
            result.pii = detect_pii(result.content_clean)
            if result.pii.has_pii:
                result.warnings.append(f"pii_detected:{','.join(result.pii.findings)}")
                if pii_policy == "reject":
                    result.error = f"pii_rejected:{','.join(result.pii.findings)}"
                    _log("pii", "failed", t0, f"policy=reject,{','.join(result.pii.findings)}")
                    return result
                elif pii_policy == "mask":
                    result.content_clean = mask_pii(result.content_clean)
                    result.warnings.append("pii_masked")
                    _log("pii", "ok", t0, f"policy=mask,{','.join(result.pii.findings)}")
                else:
                    _log("pii", "ok", t0, f"policy=warn,{','.join(result.pii.findings)}")
            else:
                _log("pii", "ok", t0, "no_pii")
        except Exception as e:
            result.warnings.append(f"pii_fallback:{e}")
            _log("pii", "fallback", t0, str(e))
    else:
        _log("pii", "skipped", t0, "disabled")

    # ── Step 6: 分块 ────────────────────────────────
    t0 = time.time()
    try:
        result.chunks = chunk_text(
            text=result.content_clean,
            strategy=chunk_strategy,
            max_tokens=chunk_max_tokens,
            overlap_tokens=chunk_overlap,
        )
    except Exception as e:
        result.error = f"chunk_failed:{e}"
        result.warnings.append(result.error)
        logger.warning(f"[DocProcessor] chunk failed: {e}")
        _log("chunk", "failed", t0, str(e))
        return result

    if not result.chunks:
        result.error = "no_chunks_produced"
        _log("chunk", "failed", t0, "no_chunks")
        return result

    _log("chunk", "ok", t0, f"count={len(result.chunks)}")
    result.success = True
    return result
