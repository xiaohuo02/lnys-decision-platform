# -*- coding: utf-8 -*-
"""backend/knowledge/ocr_engine.py — RapidOCR 轻量级 OCR 引擎封装

单例模式，首次调用时加载模型（~50MB ONNX 模型自动缓存）。
支持图片文件和 PDF 扫描页的文字识别。
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Tuple

from loguru import logger


class OCREngine:
    """线程安全 RapidOCR 单例。"""

    _instance: OCREngine | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._engine = None
        self._available = False
        try:
            from rapidocr_onnxruntime import RapidOCR
            self._engine = RapidOCR()
            self._available = True
            logger.info("[OCR] RapidOCR engine loaded")
        except ImportError:
            logger.warning("[OCR] rapidocr_onnxruntime not installed, OCR disabled")
        except Exception as e:
            logger.warning(f"[OCR] engine init failed: {e}")

    @classmethod
    def get_instance(cls) -> OCREngine:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @property
    def available(self) -> bool:
        return self._available

    def recognize_file(self, file_path: Path, timeout: int = 30) -> Tuple[str, float]:
        """识别图片文件，返回 (text, avg_confidence)。

        Args:
            file_path: 图片文件路径
            timeout: 超时秒数（预留，当前不做线程级超时）

        Returns:
            (extracted_text, average_confidence)
            confidence 范围 0~1, 无结果时返回 ("", 0.0)
        """
        if not self._available:
            return ("", 0.0)

        try:
            result, _ = self._engine(str(file_path))
            if not result:
                return ("", 0.0)

            lines = []
            confidences = []
            for item in result:
                # RapidOCR 返回格式: [bbox, text, confidence]
                text = item[1] if len(item) > 1 else ""
                conf = float(item[2]) if len(item) > 2 else 0.0
                if text.strip():
                    lines.append(text.strip())
                    confidences.append(conf)

            full_text = "\n".join(lines)
            avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
            return (full_text, round(avg_conf, 3))

        except Exception as e:
            logger.warning(f"[OCR] recognize failed for {file_path}: {e}")
            return ("", 0.0)
