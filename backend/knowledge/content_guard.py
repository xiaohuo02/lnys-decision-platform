# -*- coding: utf-8 -*-
"""backend/knowledge/content_guard.py — 内容安全防护

职责：
  1. 文件 MIME 类型校验（真实类型 vs 扩展名）
  2. PII 检测（手机号/身份证/银行卡/邮箱/地址关键词）
  3. 文件大小校验
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from loguru import logger


# ── PII 正则 ─────────────────────────────────────────────────────

_PII_PATTERNS = {
    "phone": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "id_card": re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
    "bank_card": re.compile(r"(?<!\d)\d{16,19}(?!\d)"),
    "email": re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"),
}

_ADDRESS_KEYWORDS = ["省", "市", "区", "县", "街道", "路", "号", "栋", "楼", "室"]

# ── MIME 白名单 ──────────────────────────────────────────────────

_ALLOWED_MIMES = {
    "text/plain",
    "text/csv",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "image/jpeg",
    "image/png",
    "image/bmp",
    "image/tiff",
    "image/webp",
}

# 扩展名 → 期望 MIME（松散映射）
_EXT_MIME_MAP = {
    ".txt": {"text/plain"},
    ".csv": {"text/plain", "text/csv", "application/csv"},
    ".pdf": {"application/pdf"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
              "application/zip"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
              "application/zip"},
    ".xls": {"application/vnd.ms-excel"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
    ".bmp": {"image/bmp", "image/x-ms-bmp"},
    ".tiff": {"image/tiff"},
    ".webp": {"image/webp"},
}


@dataclass
class PIIReport:
    """PII 检测结果"""
    has_pii: bool = False
    findings: List[str] = field(default_factory=list)
    # 类型 → 命中数量
    counts: dict = field(default_factory=dict)


@dataclass
class FileGuardResult:
    """文件安全校验结果"""
    passed: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    mime_type: Optional[str] = None


def check_file_safety(
    file_path: Path,
    max_size_mb: int = 50,
) -> FileGuardResult:
    """文件安全校验：大小 + MIME 类型。

    Args:
        file_path: 文件路径
        max_size_mb: 最大文件大小(MB)

    Returns:
        FileGuardResult
    """
    result = FileGuardResult()

    # 1. 文件存在性
    if not file_path.exists():
        result.passed = False
        result.errors.append("file_not_found")
        return result

    # 2. 大小校验
    size_mb = file_path.stat().st_size / (1024 * 1024)
    if size_mb > max_size_mb:
        result.passed = False
        result.errors.append(f"file_too_large:{size_mb:.1f}MB>max:{max_size_mb}MB")
        return result

    # 3. MIME 类型校验（尝试使用 python-magic，fallback 跳过）
    ext = file_path.suffix.lower()
    try:
        import magic
        mime = magic.from_file(str(file_path), mime=True)
        result.mime_type = mime
        expected = _EXT_MIME_MAP.get(ext, set())
        if expected and mime not in expected:
            result.warnings.append(f"mime_mismatch:ext={ext},mime={mime}")
    except ImportError:
        result.warnings.append("python-magic not installed, skipping MIME check")
    except Exception as e:
        result.warnings.append(f"mime_check_error:{e}")

    return result


def detect_pii(text: str) -> PIIReport:
    """检测文本中的 PII 信息。

    Returns:
        PIIReport: has_pii 表示是否发现 PII
    """
    if not text:
        return PIIReport()

    report = PIIReport()
    all_matches: dict = {}
    for pii_type, pattern in _PII_PATTERNS.items():
        all_matches[pii_type] = pattern.findall(text)

    # 去重：身份证号同时匹配 bank_card → 从 bank_card 中排除
    id_set = set(all_matches.get("id_card", []))
    if id_set and all_matches.get("bank_card"):
        all_matches["bank_card"] = [
            m for m in all_matches["bank_card"]
            if m not in id_set and not any(m in idc for idc in id_set)
        ]

    for pii_type, matches in all_matches.items():
        if matches:
            report.has_pii = True
            report.counts[pii_type] = len(matches)
            report.findings.append(f"{pii_type}:{len(matches)}")

    # 地址关键词检测（简单启发式）
    addr_hits = sum(1 for kw in _ADDRESS_KEYWORDS if kw in text)
    if addr_hits >= 3:
        report.has_pii = True
        report.counts["address_hint"] = addr_hits
        report.findings.append(f"address_hint:{addr_hits}")

    return report


def mask_pii(text: str) -> str:
    """对文本中的 PII 信息进行脱敏替换。"""
    if not text:
        return ""
    text = _PII_PATTERNS["phone"].sub("[手机号]", text)
    text = _PII_PATTERNS["id_card"].sub("[身份证号]", text)
    text = _PII_PATTERNS["bank_card"].sub("[银行卡号]", text)
    text = _PII_PATTERNS["email"].sub("[邮箱]", text)
    return text
