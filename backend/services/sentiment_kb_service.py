# -*- coding: utf-8 -*-
"""backend/services/sentiment_kb_service.py — 舆情情报知识库服务

职责：
  1. 分析结果 → embedding → 写入 ChromaDB (sentiment_reviews)
  2. 语义检索（其他 Agent RAG 查询入口）
  3. 按实体检索近 N 天情报
  4. 知识库统计信息
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from loguru import logger

from backend.core.embedding import EmbeddingService
from backend.core.vector_store import VectorStoreManager


class SentimentKBService:
    """舆情情报知识库 — 写入 / 语义检索 / 跨 Agent 查询。"""

    _instance: SentimentKBService | None = None

    def __init__(self) -> None:
        self._embedding = EmbeddingService.get_instance()
        self._store = VectorStoreManager.get_instance()
        self._reviews = self._store.get_collection("sentiment_reviews")

    @classmethod
    def get_instance(cls) -> SentimentKBService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── 写入 ─────────────────────────────────────────────────────

    async def ingest(self, review_id: str, text: str, result: dict) -> str:
        """分析完成后，embedding + 写入知识库。

        Args:
            review_id: 唯一标识（通常为 cache_key）
            text: 原始评论文本
            result: 完整分析结果 dict

        Returns:
            写入后的 review_id
        """
        try:
            vec = self._embedding.embed_one(text)

            # ChromaDB metadata 只支持 str/int/float/bool，复杂结构需 JSON 序列化
            metadata: Dict[str, Any] = {
                "label": result.get("label", ""),
                "confidence": float(result.get("confidence", 0)),
                "model_used": result.get("model_used", ""),
                "cascade_tier": int(result.get("cascade_tier", 0)),
                "timestamp": datetime.now().isoformat(),
            }

            # 结构化信号 → JSON 字符串存储
            entity_sents = result.get("entity_sentiments", [])
            if entity_sents:
                metadata["entity_sentiments"] = json.dumps(
                    entity_sents, ensure_ascii=False
                )
                # 提取实体名索引（用于按实体过滤）
                entities = list({
                    es.get("entity", "") for es in entity_sents if es.get("entity")
                })
                metadata["entities"] = ",".join(entities)

            intent_tags = result.get("intent_tags", [])
            if intent_tags:
                metadata["intent_tags"] = json.dumps(intent_tags)

            agent_signals = result.get("agent_signals", [])
            if agent_signals:
                metadata["agent_signals"] = json.dumps(
                    agent_signals, ensure_ascii=False
                )

            self._reviews.upsert(
                ids=[review_id],
                embeddings=[vec],
                documents=[text],
                metadatas=[metadata],
            )
            logger.debug(f"[SentimentKB] ingested: {review_id}")
            return review_id

        except Exception as e:
            logger.warning(f"[SentimentKB] ingest failed: {e}")
            raise

    # ── 语义检索 ──────────────────────────────────────────────────

    async def search_similar(
        self,
        query: str,
        top_k: int = 5,
        label: Optional[str] = None,
    ) -> Dict[str, Any]:
        """语义检索相似评论。

        Args:
            query: 查询文本
            top_k: 返回数量
            label: 可选情感标签过滤

        Returns:
            {items: [{text, label, confidence, score, ...}], total: int}
        """
        vec = self._embedding.embed_query(query)
        where = {"label": label} if label else None

        try:
            results = self._reviews.query(
                query_embeddings=[vec],
                n_results=top_k,
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            logger.warning(f"[SentimentKB] search failed: {e}")
            return {"items": [], "total": 0}

        items = []
        if results and results.get("ids") and results["ids"][0]:
            ids = results["ids"][0]
            docs = results["documents"][0] if results.get("documents") else [""] * len(ids)
            metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(ids)
            dists = results["distances"][0] if results.get("distances") else [0] * len(ids)

            for i, rid in enumerate(ids):
                meta = metas[i] if i < len(metas) else {}
                # ChromaDB cosine distance → similarity score
                similarity = round(1 - dists[i], 3) if i < len(dists) else 0

                item = {
                    "id": rid,
                    "text": docs[i] if i < len(docs) else "",
                    "label": meta.get("label", ""),
                    "confidence": meta.get("confidence", 0),
                    "model_used": meta.get("model_used", ""),
                    "similarity": similarity,
                    "timestamp": meta.get("timestamp", ""),
                }

                # 反序列化结构化字段
                if meta.get("entity_sentiments"):
                    try:
                        item["entity_sentiments"] = json.loads(meta["entity_sentiments"])
                    except (json.JSONDecodeError, TypeError):
                        pass

                if meta.get("intent_tags"):
                    try:
                        item["intent_tags"] = json.loads(meta["intent_tags"])
                    except (json.JSONDecodeError, TypeError):
                        pass

                items.append(item)

        return {"items": items, "total": len(items)}

    async def search_by_entity(
        self,
        entity: str,
        days: int = 7,
        top_k: int = 20,
    ) -> Dict[str, Any]:
        """按实体语义检索近 N 天评论。"""
        vec = self._embedding.embed_query(entity)

        try:
            results = self._reviews.query(
                query_embeddings=[vec],
                n_results=top_k,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            logger.warning(f"[SentimentKB] entity search failed: {e}")
            return {"items": [], "total": 0, "entity": entity}

        # 过滤时间范围 + 实体相关性
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        items = []

        if results and results.get("ids") and results["ids"][0]:
            ids = results["ids"][0]
            docs = results["documents"][0] if results.get("documents") else []
            metas = results["metadatas"][0] if results.get("metadatas") else []
            dists = results["distances"][0] if results.get("distances") else []

            for i, rid in enumerate(ids):
                meta = metas[i] if i < len(metas) else {}
                ts = meta.get("timestamp", "")

                # 时间过滤
                if ts and ts < cutoff:
                    continue

                # 实体相关性：metadata.entities 包含目标实体，或文本包含实体名
                entities_str = meta.get("entities", "")
                doc_text = docs[i] if i < len(docs) else ""
                if entity not in entities_str and entity not in doc_text:
                    continue

                similarity = round(1 - dists[i], 3) if i < len(dists) else 0
                items.append({
                    "id": rid,
                    "text": doc_text,
                    "label": meta.get("label", ""),
                    "confidence": meta.get("confidence", 0),
                    "similarity": similarity,
                    "timestamp": ts,
                    "entities": entities_str,
                })

        return {"items": items, "total": len(items), "entity": entity}

    # ── 统计 ──────────────────────────────────────────────────────

    async def get_stats(self) -> Dict[str, Any]:
        """知识库统计信息。"""
        try:
            count = self._reviews.count()
        except Exception:
            count = 0

        return {
            "total_reviews": count,
            "collection": "sentiment_reviews",
            "embedding_model": "bge-small-zh-v1.5",
            "embedding_dim": self._embedding.dim,
        }
