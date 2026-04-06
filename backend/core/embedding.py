# -*- coding: utf-8 -*-
"""backend/core/embedding.py — 向量 Embedding 单例服务

共建层：舆情知识库 + 企业知识库共享同一模型实例。
模型：BAAI/bge-small-zh-v1.5（33M params, 512d, ~200MB RAM, ~15ms/句 CPU）
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import List

from loguru import logger


class EmbeddingService:
    """线程安全的 Embedding 单例。全局只加载一次模型。"""

    _instance: EmbeddingService | None = None
    _lock = threading.Lock()

    # 当本地路径不存在时回退的 HuggingFace 模型名
    _HF_FALLBACK = "BAAI/bge-small-zh-v1.5"

    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer
        from backend.config import settings

        configured = settings.BGE_MODEL_NAME
        # 若配置为绝对路径但实际不存在 → 回退到 HF 模型名，由 SentenceTransformer
        # 自动下载并缓存到 ~/.cache/huggingface/hub。该回退机制与 reranker 一致。
        if os.path.isabs(configured) and not Path(configured).exists():
            logger.warning(
                f"[Embedding] local path not found: {configured}, "
                f"falling back to HF hub: {self._HF_FALLBACK}"
            )
            model_name = self._HF_FALLBACK
        else:
            model_name = configured

        logger.info(f"[Embedding] loading model: {model_name} ...")
        self._model = SentenceTransformer(model_name)
        self._dim = self._model.get_sentence_embedding_dimension()
        logger.info(f"[Embedding] loaded. dim={self._dim}")

    @classmethod
    def get_instance(cls) -> EmbeddingService:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: List[str]) -> List[List[float]]:
        """批量编码，返回归一化向量列表。"""
        if not texts:
            return []
        vectors = self._model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vectors.tolist()

    def embed_one(self, text: str) -> List[float]:
        """单句编码（用于文档入库）。"""
        return self.embed([text])[0]

    def embed_query(self, query: str) -> List[float]:
        """查询编码。短文本场景下与 embed_one 相同；
        若后续切换 bge-base/large 可在此添加检索指令前缀。"""
        return self.embed([query])[0]
