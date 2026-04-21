# -*- coding: utf-8 -*-
"""backend/governance/eval_center/graders/embedding_grader.py — 语义相似度评分器

使用本地 BGE 模型计算 expected 与 actual 之间的 cosine similarity。
零远程 API 调用，纯本地推理。
"""
from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional

from loguru import logger

from backend.governance.eval_center.graders.base_grader import BaseGrader, GraderResult

# 懒加载模型，避免在 import 时加载
_model = None
_tokenizer = None


def _get_embedding_model():
    """懒加载 BGE embedding 模型"""
    global _model, _tokenizer
    if _model is not None:
        return _model, _tokenizer

    try:
        from sentence_transformers import SentenceTransformer
        from backend.config import settings

        model_path = settings.BGE_MODEL_NAME
        logger.info(f"[EmbeddingGrader] 加载模型: {model_path}")
        _model = SentenceTransformer(str(model_path))
        _tokenizer = None  # SentenceTransformer 自带 tokenizer
        logger.info("[EmbeddingGrader] 模型加载完成")
        return _model, _tokenizer
    except Exception as exc:
        logger.warning(f"[EmbeddingGrader] 模型加载失败: {exc}")
        return None, None


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """计算两个向量的 cosine similarity"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a < 1e-9 or norm_b < 1e-9:
        return 0.0
    return dot / (norm_a * norm_b)


class EmbeddingSimilarityGrader(BaseGrader):
    """语义相似度评分器

    比较 expected 文本与 actual 文本的语义相似度。
    使用本地 BGE 模型，不依赖远程 API。
    """

    grader_name = "embedding_similarity"

    async def grade(
        self,
        input_json: Dict[str, Any],
        expected_json: Dict[str, Any],
        actual_output: Dict[str, Any],
        evaluator_config: Dict[str, Any] = None,
    ) -> GraderResult:
        expected_text = self._to_text(expected_json)
        actual_text = self._to_text(actual_output)

        if not expected_text or not actual_text:
            return self._make_result(
                0.0,
                reasoning="expected 或 actual 为空文本，无法计算相似度",
            )

        model, _ = _get_embedding_model()
        if model is None:
            return self._fallback_similarity(expected_text, actual_text)

        try:
            embeddings = model.encode([expected_text, actual_text], normalize_embeddings=True)
            sim = float(_cosine_similarity(embeddings[0].tolist(), embeddings[1].tolist()))
        except Exception as exc:
            logger.error(f"[EmbeddingGrader] encode 失败: {exc}")
            return self._fallback_similarity(expected_text, actual_text)

        return self._make_result(
            max(sim, 0.0),
            reasoning=f"语义相似度: {sim:.4f}",
            method="bge_cosine",
        )

    def _fallback_similarity(self, expected: str, actual: str) -> GraderResult:
        """降级方案：基于字符级 Jaccard 相似度"""
        exp_chars = set(expected)
        act_chars = set(actual)
        if not exp_chars or not act_chars:
            return self._make_result(0.0, reasoning="降级: 空文本")

        jaccard = len(exp_chars & act_chars) / len(exp_chars | act_chars)
        return self._make_result(
            jaccard,
            reasoning=f"降级(char-jaccard): {jaccard:.4f}（BGE 模型不可用）",
            method="char_jaccard_fallback",
        )

    @staticmethod
    def _to_text(data: Dict[str, Any]) -> str:
        """将 dict 转为纯文本"""
        for key in ("text", "answer", "content", "summary", "output"):
            val = data.get(key)
            if val and isinstance(val, str):
                return val
        # 如果有 contains 列表
        if isinstance(data.get("contains"), list):
            return " ".join(str(x) for x in data["contains"])
        return json.dumps(data, ensure_ascii=False)
