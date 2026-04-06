# -*- coding: utf-8 -*-
"""backend/core/vector_store.py — ChromaDB 向量存储管理器

共建层：通过 collection 命名隔离不同业务域的数据。
命名规范: {domain}_{purpose}
  - sentiment_*   → 舆情情报模块
  - enterprise_*  → 企业知识库模块（队友负责）

各域只写自己的 collections，可跨域只读。
"""
from __future__ import annotations

import threading
from typing import Dict, Any

from loguru import logger


# ── Collection 注册表 ─────────────────────────────────────────
COLLECTION_REGISTRY: Dict[str, Dict[str, Any]] = {
    # 舆情情报域
    "sentiment_reviews": {
        "owner": "sentiment",
        "description": "每条评论的结构化分析结果 + embedding",
    },
    "sentiment_entities": {
        "owner": "sentiment",
        "description": "按产品/实体聚合的情感画像",
    },
    "sentiment_summaries": {
        "owner": "sentiment",
        "description": "周期性聚合摘要（日/周）",
    },
    # 企业知识库域
    "enterprise_documents": {
        "owner": "enterprise",
        "description": "FAQ 知识库文档 embedding（来源: faq_documents 表）",
    },
    # Copilot 动态记忆域（R5-3）
    "copilot_memory_embeddings": {
        "owner": "copilot",
        "description": "用户动态记忆 embedding（来源: copilot_memory 表，按 user_id metadata 过滤）",
    },
}


class VectorStoreManager:
    """线程安全的 ChromaDB 管理器单例。"""

    _instance: VectorStoreManager | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        import chromadb
        from backend.config import settings

        persist_dir = settings.CHROMA_PERSIST_DIR
        logger.info(f"[VectorStore] initializing ChromaDB at: {persist_dir}")
        self._client = chromadb.PersistentClient(path=persist_dir)
        logger.info("[VectorStore] ChromaDB ready")

    @classmethod
    def get_instance(cls) -> VectorStoreManager:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @property
    def client(self):
        return self._client

    def get_collection(self, name: str):
        """获取指定 collection，不存在则自动创建。

        对于未在静态 COLLECTION_REGISTRY 中的 collection（典型场景：通过 SQL seed
        直接 INSERT 的 kb_libraries 行 —— 没走 KnowledgeBaseService.create_library
        路径），自动注册为 owner='knowledge'，避免散落 warning。
        显式 register_collection 仍是首选（描述更具语义），auto-register 是兜底。
        """
        if name not in COLLECTION_REGISTRY:
            COLLECTION_REGISTRY[name] = {
                "owner": "knowledge",
                "description": "auto-registered (dynamic KB collection)",
            }
            logger.debug(
                f"[VectorStore] auto-registered collection '{name}' "
                f"(dynamic KB, prefer explicit register_collection)"
            )
        return self._client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )

    def list_collections(self):
        """列出所有已注册的 collection 及其状态。"""
        result = []
        for name, meta in COLLECTION_REGISTRY.items():
            try:
                col = self._client.get_or_create_collection(name=name)
                count = col.count()
            except Exception:
                count = -1
            result.append({
                "name": name,
                "owner": meta["owner"],
                "description": meta["description"],
                "count": count,
            })
        return result

    def list_collections_by_owner(self, owner: str):
        """按 owner 过滤 collection。"""
        return [
            c for c in self.list_collections()
            if c["owner"] == owner
        ]

    # ── 动态 collection 管理（知识库中台 v2 新增）─────────────────

    def register_collection(self, name: str, owner: str = "knowledge", description: str = ""):
        """动态注册 collection 到注册表并创建。"""
        if name not in COLLECTION_REGISTRY:
            COLLECTION_REGISTRY[name] = {
                "owner": owner,
                "description": description,
            }
            logger.info(f"[VectorStore] registered collection: {name}")
        return self.get_collection(name)

    def delete_collection(self, name: str) -> bool:
        """删除 collection（ChromaDB + 注册表）。"""
        try:
            self._client.delete_collection(name=name)
            COLLECTION_REGISTRY.pop(name, None)
            logger.info(f"[VectorStore] deleted collection: {name}")
            return True
        except Exception as e:
            logger.warning(f"[VectorStore] delete collection '{name}' failed: {e}")
            return False

    def collection_exists(self, name: str) -> bool:
        """检查 collection 是否存在。"""
        try:
            existing = self._client.list_collections()
            names = [c.name if hasattr(c, 'name') else str(c) for c in existing]
            return name in names
        except Exception:
            return False

    def get_collection_count(self, name: str) -> int:
        """获取 collection 中的向量数量。"""
        try:
            col = self._client.get_or_create_collection(name=name)
            return col.count()
        except Exception:
            return 0
