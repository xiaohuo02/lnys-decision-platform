# -*- coding: utf-8 -*-
"""backend/services/enterprise_kb_service.py — 企业 FAQ 知识库服务

职责：
  1. FAQ 文档 → embedding → 写入 ChromaDB (enterprise_documents)
  2. 语义检索（OpenClaw Agent / Copilot KBRagSkill 共用）
  3. 全量同步 MySQL faq_documents → ChromaDB
  4. 单条入库 / 删除（Admin 创建/停用 FAQ 时触发）

设计要点：
  - 复用 EmbeddingService（bge-small-zh-v1.5）和 VectorStoreManager（ChromaDB）
  - 长文档自动分块（400 字 + 100 重叠），短文档不分块
  - 检索结果按相似度降序，可选 group_name 过滤
  - 任何环节失败 → 返回空结果，上层回退 SQL LIKE
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger

from backend.core.embedding import EmbeddingService
from backend.core.vector_store import VectorStoreManager

# ── 分块参数 ────────────────────────────────────────────────────
_CHUNK_SIZE = 400      # 每块最大字符数
_CHUNK_OVERLAP = 100   # 块间重叠字符数


def _chunk_text(text: str, chunk_size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> List[str]:
    """将长文本按固定窗口分块。短文本直接返回单块。"""
    text = text.strip()
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


class EnterpriseKBService:
    """企业 FAQ 知识库 — 入库 / 检索 / 同步。"""

    _instance: EnterpriseKBService | None = None

    def __init__(self) -> None:
        self._embedding = EmbeddingService.get_instance()
        self._store = VectorStoreManager.get_instance()
        self._collection = self._store.get_collection("enterprise_documents")

    @classmethod
    def get_instance(cls) -> EnterpriseKBService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── 入库 ─────────────────────────────────────────────────────

    async def ingest(
        self,
        doc_id: str,
        title: str,
        content: str,
        group_name: str = "",
    ) -> int:
        """单条 FAQ → 分块 → embed → 写入 ChromaDB。返回写入的 chunk 数。"""
        try:
            # 先清除该 doc_id 的旧分块（防止重复）
            await self.remove(doc_id)

            # 标题 + 内容合并后分块
            full_text = f"{title}\n{content}"
            chunks = _chunk_text(full_text)

            ids = []
            texts = []
            metadatas = []
            for i, chunk in enumerate(chunks):
                chunk_id = f"{doc_id}__chunk_{i}"
                ids.append(chunk_id)
                texts.append(chunk)
                metadatas.append({
                    "doc_id": doc_id,
                    "chunk_index": i,
                    "title": title,
                    "group_name": group_name,
                    "ingested_at": datetime.now().isoformat(),
                })

            # 批量 embed
            embeddings = self._embedding.embed(texts)

            # 写入 ChromaDB
            self._collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
            )
            logger.info(f"[EnterpriseKB] ingested doc_id={doc_id} chunks={len(chunks)}")
            return len(chunks)

        except Exception as e:
            logger.warning(f"[EnterpriseKB] ingest failed doc_id={doc_id}: {e}")
            return 0

    # ── 删除 ─────────────────────────────────────────────────────

    async def remove(self, doc_id: str) -> int:
        """删除指定 doc_id 的所有分块。返回删除数量。"""
        try:
            # ChromaDB where 过滤删除
            existing = self._collection.get(
                where={"doc_id": doc_id},
                include=[],
            )
            if existing and existing["ids"]:
                self._collection.delete(ids=existing["ids"])
                logger.debug(f"[EnterpriseKB] removed {len(existing['ids'])} chunks for doc_id={doc_id}")
                return len(existing["ids"])
            return 0
        except Exception as e:
            logger.warning(f"[EnterpriseKB] remove failed doc_id={doc_id}: {e}")
            return 0

    # ── 语义检索（桥接新 SearchEngine，fallback 原逻辑）──────────

    def _get_enterprise_kb_id(self) -> Optional[str]:
        """获取 enterprise_faq 知识库 ID（新系统）。"""
        try:
            from backend.database import SessionLocal
            from sqlalchemy import text as sa_text
            db = SessionLocal()
            try:
                row = db.execute(sa_text(
                    "SELECT kb_id FROM kb_libraries WHERE name='enterprise_faq' AND is_active=1"
                )).fetchone()
                return row._mapping["kb_id"] if row else None
            finally:
                db.close()
        except Exception:
            return None

    async def search(
        self,
        query: str,
        top_k: int = 3,
        group_name: Optional[str] = None,
        min_similarity: float = 0.45,
    ) -> List[Dict[str, Any]]:
        """语义检索 FAQ，返回相似度高于阈值的结果列表。

        优先委托新 SearchEngine，失败时 fallback 到原 ChromaDB 直查。

        Args:
            query: 用户问题文本
            top_k: 最多返回条数
            group_name: 可选分组过滤
            min_similarity: 最低相似度阈值

        Returns:
            [{doc_id, title, content, group_name, similarity}, ...]
        """
        # 尝试新 SearchEngine
        try:
            kb_id = self._get_enterprise_kb_id()
            if kb_id:
                from backend.knowledge.search_engine import SearchEngine
                engine = SearchEngine.get_instance()
                result = engine.search(
                    query=query,
                    kb_ids=[kb_id],
                    top_k=top_k,
                    min_score=min_similarity,
                    mode="hybrid",
                )
                if result.get("hits"):
                    seen = set()
                    items = []
                    for hit in result["hits"]:
                        did = hit.get("document_id", "")
                        if did in seen:
                            continue
                        seen.add(did)
                        items.append({
                            "doc_id": did,
                            "title": hit.get("title", ""),
                            "content": hit.get("content", ""),
                            "group_name": hit.get("metadata", {}).get("group_name", ""),
                            "similarity": hit.get("score", 0),
                        })
                    if items:
                        return items
        except Exception as e:
            logger.debug(f"[EnterpriseKB] new search engine fallback: {e}")

        # Fallback: 原 ChromaDB 直查
        try:
            query_vec = self._embedding.embed_query(query)
            where = {"group_name": group_name} if group_name else None
            results = self._collection.query(
                query_embeddings=[query_vec],
                n_results=top_k,
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            logger.warning(f"[EnterpriseKB] search failed: {e}")
            return []

        items = []
        if results and results.get("ids") and results["ids"][0]:
            ids = results["ids"][0]
            docs = results["documents"][0] if results.get("documents") else [""] * len(ids)
            metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(ids)
            dists = results["distances"][0] if results.get("distances") else [1.0] * len(ids)

            seen_docs = set()
            for i, rid in enumerate(ids):
                meta = metas[i] if i < len(metas) else {}
                similarity = round(1 - dists[i], 3) if i < len(dists) else 0
                if similarity < min_similarity:
                    continue
                doc_id = meta.get("doc_id", "")
                if doc_id in seen_docs:
                    continue
                seen_docs.add(doc_id)
                items.append({
                    "doc_id": doc_id,
                    "title": meta.get("title", ""),
                    "content": docs[i] if i < len(docs) else "",
                    "group_name": meta.get("group_name", ""),
                    "similarity": similarity,
                })
        return items

    # ── 全量同步 ──────────────────────────────────────────────────

    async def sync_all(self, db) -> Dict[str, Any]:
        """从 MySQL faq_documents 全量同步到 ChromaDB。

        Args:
            db: SQLAlchemy Session

        Returns:
            {"total": N, "ingested": M, "failed": F}
        """
        from sqlalchemy import text

        try:
            rows = db.execute(text(
                "SELECT doc_id, group_name, title, content "
                "FROM faq_documents WHERE is_active = 1"
            )).fetchall()
        except Exception as e:
            logger.error(f"[EnterpriseKB] sync_all: MySQL query failed: {e}")
            return {"total": 0, "ingested": 0, "failed": 0, "error": str(e)}

        total = len(rows)
        ingested = 0
        failed = 0

        for row in rows:
            doc = dict(row._mapping)
            chunks = await self.ingest(
                doc_id=doc["doc_id"],
                title=doc["title"],
                content=doc["content"],
                group_name=doc.get("group_name", ""),
            )
            if chunks > 0:
                ingested += 1
            else:
                failed += 1

        stats = {"total": total, "ingested": ingested, "failed": failed}
        logger.info(f"[EnterpriseKB] sync_all completed: {stats}")
        return stats

    # ── 统计 ──────────────────────────────────────────────────────

    async def get_stats(self) -> Dict[str, Any]:
        """返回知识库统计信息。"""
        try:
            count = self._collection.count()
        except Exception:
            count = 0

        return {
            "total_chunks": count,
            "collection": "enterprise_documents",
            "embedding_model": "bge-small-zh-v1.5",
            "embedding_dim": self._embedding.dim,
            "chunk_size": _CHUNK_SIZE,
            "chunk_overlap": _CHUNK_OVERLAP,
        }
