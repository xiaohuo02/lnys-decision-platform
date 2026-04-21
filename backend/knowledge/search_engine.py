# -*- coding: utf-8 -*-
"""backend/knowledge/search_engine.py — 统一检索引擎

职责：
  1. 查哪些库 — 按 kb_ids / domains 路由
  2. 怎么查   — 向量检索 + BM25 关键词检索
  3. 怎么融合 — RRF (Reciprocal Rank Fusion)
  4. 怎么降级 — 五级降级链
  5. 可解释   — 返回 search_mode / degraded 标记

五级降级链:
  L1: hybrid (vector + BM25 + RRF)
  L2: vector only
  L3: BM25 only
  L4: SQL LIKE fallback
  L5: empty result + degraded=True
"""
from __future__ import annotations

import time
import threading
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional

from loguru import logger


class SearchEngine:
    """统一检索引擎单例。"""

    _instance: SearchEngine | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._embedding = None
        self._store = None
        self._bm25_cache: Dict[str, Any] = {}
        self._reranker = None
        self._reranker_loaded = False
        logger.info("[SearchEngine] initialized (lazy mode)")

    def _get_embedding(self):
        """懒加载 Embedding 服务，模型不存在时返回 None。"""
        if self._embedding is not None:
            return self._embedding
        try:
            from backend.core.embedding import EmbeddingService
            self._embedding = EmbeddingService.get_instance()
        except Exception as e:
            logger.warning(f"[SearchEngine] embedding init failed (degrading): {e}")
            self._embedding = None
        return self._embedding

    def _get_store(self):
        """懒加载 VectorStore。"""
        if self._store is not None:
            return self._store
        try:
            from backend.core.vector_store import VectorStoreManager
            self._store = VectorStoreManager.get_instance()
        except Exception as e:
            logger.warning(f"[SearchEngine] vector store init failed (degrading): {e}")
            self._store = None
        return self._store

    @classmethod
    def get_instance(cls) -> SearchEngine:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def search(
        self,
        query: str,
        kb_ids: Optional[List[str]] = None,
        top_k: int = 5,
        min_score: float = 0.3,
        mode: str = "hybrid",
    ) -> Dict[str, Any]:
        """统一检索入口。

        Args:
            query: 查询文本
            kb_ids: 知识库 ID 列表，None=全部活跃库
            top_k: 返回数量
            min_score: 最低分数阈值
            mode: hybrid / vector / keyword

        Returns:
            {query, hits, total, search_mode, degraded, degraded_reason, elapsed_ms}
        """
        start = time.time()
        result = {
            "query": query,
            "hits": [],
            "total": 0,
            "search_mode": mode,
            "degraded": False,
            "degraded_reason": None,
            "elapsed_ms": 0,
        }

        if not query or not query.strip():
            return result

        # 解析目标 collection
        collections = self._resolve_collections(kb_ids)
        if not collections:
            result["degraded"] = True
            result["degraded_reason"] = "no_active_kb"
            return result

        # 五级降级链
        hits = []
        actual_mode = mode

        if mode == "hybrid":
            # L1: hybrid
            hits = self._hybrid_search(query, collections, top_k, min_score)
            actual_mode = "hybrid"
            if not hits:
                # L2: vector only
                hits = self._vector_search(query, collections, top_k, min_score)
                actual_mode = "vector"
                result["degraded"] = True
                result["degraded_reason"] = "bm25_unavailable"
        elif mode == "vector":
            hits = self._vector_search(query, collections, top_k, min_score)
            actual_mode = "vector"
        elif mode == "keyword":
            hits = self._bm25_search(query, collections, top_k)
            actual_mode = "keyword"

        if not hits and actual_mode != "keyword":
            # L3: BM25 only
            hits = self._bm25_search(query, collections, top_k)
            if hits:
                actual_mode = "keyword"
                result["degraded"] = True
                result["degraded_reason"] = "vector_unavailable"

        if not hits:
            # L4: SQL LIKE
            hits = self._sql_fallback(query, kb_ids, top_k)
            if hits:
                actual_mode = "sql_like"
                result["degraded"] = True
                result["degraded_reason"] = "vector_and_bm25_unavailable"

        if not hits:
            # L5: empty
            result["degraded"] = True
            result["degraded_reason"] = "all_retrieval_failed"

        # ── Rerank ──────────────────────────────────
        from backend.config import settings
        if hits and settings.KB_RERANK_ENABLED:
            try:
                hits = self._rerank(query, hits, settings.KB_RERANK_TOP_N)
                result["reranked"] = True
            except Exception as e:
                logger.warning(f"[SearchEngine] rerank fallback: {e}")
                result["reranked"] = False

        final_hits = hits[:top_k]
        if final_hits and not self._has_query_term_overlap(query, final_hits):
            final_hits = []
            hits = []
            result["degraded"] = True
            result["degraded_reason"] = "no_query_term_overlap"
        result["hits"] = final_hits
        result["total"] = len(hits)
        result["search_mode"] = actual_mode

        # ── 置信度分析 ──────────────────────────
        conf = self._analyze_confidence(
            final_hits, settings, degraded=bool(result.get("degraded"))
        )
        result["confidence"] = conf["confidence"]
        result["confidence_score"] = conf["confidence_score"]
        result["ambiguous"] = conf["ambiguous"]
        result["ambiguous_reason"] = conf.get("ambiguous_reason")
        result["suggestion"] = conf["suggestion"]

        result["elapsed_ms"] = round((time.time() - start) * 1000, 1)
        return result

    # ── 内部方法 ──────────────────────────────────────

    def _resolve_collections(self, kb_ids: Optional[List[str]]) -> List[Dict]:
        """解析目标 collection 列表。"""
        from sqlalchemy import text as sa_text
        try:
            from backend.database import SessionLocal
            db = SessionLocal()
            try:
                if kb_ids:
                    placeholders = ",".join([f":id{i}" for i in range(len(kb_ids))])
                    params = {f"id{i}": kid for i, kid in enumerate(kb_ids)}
                    rows = db.execute(sa_text(
                        f"SELECT kb_id, name, collection_name FROM kb_libraries "
                        f"WHERE kb_id IN ({placeholders}) AND is_active=1"
                    ), params).fetchall()
                else:
                    rows = db.execute(sa_text(
                        "SELECT kb_id, name, collection_name FROM kb_libraries WHERE is_active=1"
                    )).fetchall()
                return [dict(r._mapping) for r in rows]
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"[SearchEngine] resolve collections failed: {e}")
            return []

    def _vector_search(
        self, query: str, collections: List[Dict], top_k: int, min_score: float
    ) -> List[Dict]:
        """向量检索。"""
        try:
            emb = self._get_embedding()
            if emb is None:
                return []
            query_vec = emb.embed_query(query)
        except Exception as e:
            logger.warning(f"[SearchEngine] embed failed: {e}")
            return []

        all_hits = []
        for col_info in collections:
            col_name = col_info["collection_name"]
            kb_id = col_info["kb_id"]
            kb_name = col_info.get("name", "")
            try:
                store = self._get_store()
                if store is None:
                    return []
                col = store.get_collection(col_name)
                results = col.query(
                    query_embeddings=[query_vec],
                    n_results=top_k,
                    include=["documents", "metadatas", "distances"],
                )
                if results and results.get("ids") and results["ids"][0]:
                    ids = results["ids"][0]
                    docs = results["documents"][0] if results.get("documents") else [""] * len(ids)
                    metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(ids)
                    dists = results["distances"][0] if results.get("distances") else [1.0] * len(ids)

                    for i, rid in enumerate(ids):
                        sim = round(1 - dists[i], 3) if i < len(dists) else 0
                        if sim < min_score:
                            continue
                        meta = metas[i] if i < len(metas) else {}
                        all_hits.append({
                            "chunk_id": rid,
                            "document_id": meta.get("document_id", meta.get("doc_id", "")),
                            "kb_id": kb_id,
                            "kb_name": kb_name,
                            "title": meta.get("title", ""),
                            "content": docs[i] if i < len(docs) else "",
                            "score": sim,
                            "heading_path": meta.get("heading_path", ""),
                            "chunk_type": meta.get("chunk_type", "paragraph"),
                            "search_mode": "vector",
                            "metadata": meta,
                        })
            except Exception as e:
                logger.warning(f"[SearchEngine] vector search {col_name} failed: {e}")

        all_hits.sort(key=lambda x: x["score"], reverse=True)
        return all_hits[:top_k]

    def _bm25_search(self, query: str, collections: List[Dict], top_k: int) -> List[Dict]:
        """BM25 关键词检索。"""
        try:
            import jieba
            from rank_bm25 import BM25Okapi
        except ImportError:
            return []

        raw_hits = []
        query_tokens = self._tokenize_for_like(query)
        if not query_tokens:
            return []

        for col_info in collections:
            col_name = col_info["collection_name"]
            kb_id = col_info["kb_id"]
            kb_name = col_info.get("name", "")

            try:
                # 获取或构建 BM25 索引（kb_id 为 key，MySQL 优先 / Chroma fallback）
                index_data = self._get_bm25_index(kb_id, fallback_collection=col_name)
                if not index_data:
                    continue

                bm25, corpus_docs, corpus_metas, corpus_ids = index_data
                scores = bm25.get_scores(query_tokens)

                top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
                for idx in top_indices:
                    if scores[idx] <= 0:
                        continue
                    meta = corpus_metas[idx] if idx < len(corpus_metas) else {}
                    raw_hits.append({
                        "chunk_id": corpus_ids[idx] if idx < len(corpus_ids) else "",
                        "document_id": meta.get("document_id", meta.get("doc_id", "")),
                        "kb_id": kb_id,
                        "kb_name": kb_name,
                        "title": meta.get("title", ""),
                        "content": corpus_docs[idx] if idx < len(corpus_docs) else "",
                        "score": float(scores[idx]),
                        "heading_path": meta.get("heading_path", ""),
                        "chunk_type": meta.get("chunk_type", "paragraph"),
                        "search_mode": "keyword",
                        "metadata": meta,
                    })
            except Exception as e:
                logger.debug(f"[SearchEngine] BM25 {col_name} failed: {e}")

        all_hits = raw_hits
        max_s = max((h["score"] for h in all_hits), default=0.0)
        if max_s > 0:
            for hit in all_hits:
                hit["score"] = round(hit["score"] / max_s, 3)

        all_hits.sort(key=lambda x: x["score"], reverse=True)
        return all_hits[:top_k]

    def _get_bm25_index(self, kb_id: str, fallback_collection: Optional[str] = None):
        """获取或构建 BM25 索引（LRU 缓存，kb_id 为 key）。

        数据源优先级（§2.1 Layer 3）：
          1. MySQL ``kb_chunks`` JOIN ``kb_documents``（``embedding_status='done'``）
          2. ChromaDB ``collection.get()``（legacy fallback，仅在 MySQL 无数据时启用）

        好处：
          - Chroma 数据丢失/被清空时 BM25 仍可用
          - MySQL 是 chunk 主数据源，避免与 Chroma 双写漂移
        """
        from backend.config import settings

        if not kb_id:
            return None
        if kb_id in self._bm25_cache:
            return self._bm25_cache[kb_id]

        try:
            import jieba
            from rank_bm25 import BM25Okapi
        except ImportError:
            return None

        # 1) MySQL 优先
        docs, metas, ids = self._load_chunks_from_mysql(kb_id)
        source = "mysql"

        # 2) Chroma fallback（MySQL 无数据时）
        if not ids and fallback_collection:
            try:
                store = self._get_store()
                if store is not None:
                    col = store.get_collection(fallback_collection)
                    if col.count() > 0:
                        data = col.get(include=["documents", "metadatas"])
                        if data and data.get("ids"):
                            ids = list(data.get("ids") or [])
                            docs = list(data.get("documents") or [])
                            metas = list(data.get("metadatas") or [])
                            source = "chroma"
            except Exception as e:
                logger.debug(f"[SearchEngine] BM25 chroma fallback failed kb={kb_id}: {e}")

        if not ids:
            return None

        try:
            tokenized = [list(jieba.cut(d or "")) for d in docs]
            bm25 = BM25Okapi(tokenized)
        except Exception as e:
            logger.debug(f"[SearchEngine] BM25 build failed kb={kb_id} source={source}: {e}")
            return None

        result = (bm25, docs, metas, ids)

        # LRU: 超过限制时清除最早的
        if len(self._bm25_cache) >= settings.KB_BM25_CACHE_SIZE:
            oldest = next(iter(self._bm25_cache))
            del self._bm25_cache[oldest]

        self._bm25_cache[kb_id] = result
        logger.debug(f"[SearchEngine] BM25 index built kb={kb_id} source={source} chunks={len(ids)}")
        return result

    @staticmethod
    def _load_chunks_from_mysql(kb_id: str):
        """从 MySQL ``kb_chunks`` 加载已完成 embedding 的 chunks，供 BM25 建索引。

        Returns:
            ``(docs, metas, ids)`` —— ``ids`` 为 ``chromadb_id``（缺失时回退 ``chunk_id``），
            保持与原 ChromaDB 数据源接口一致。失败/无数据时返回 ``([], [], [])``。
        """
        try:
            from backend.database import SessionLocal  # type: ignore
            from sqlalchemy import text as sa_text  # type: ignore
        except Exception as e:
            logger.debug(f"[SearchEngine] MySQL deps unavailable kb={kb_id}: {e}")
            return [], [], []

        try:
            with SessionLocal() as db:
                rows = db.execute(sa_text(
                    "SELECT c.chunk_id, c.chromadb_id, c.document_id, c.kb_id, "
                    "c.content, c.heading_path, c.chunk_type, d.title "
                    "FROM kb_chunks c JOIN kb_documents d ON c.document_id=d.document_id "
                    "WHERE c.kb_id=:kid AND c.embedding_status='done'"
                ), {"kid": kb_id}).fetchall()
        except Exception as e:
            logger.debug(f"[SearchEngine] MySQL BM25 load failed kb={kb_id}: {e}")
            return [], [], []

        docs: List[str] = []
        metas: List[Dict[str, Any]] = []
        ids: List[str] = []
        for r in rows:
            m = r._mapping
            content = m.get("content") or ""
            if not content:
                continue
            docs.append(content)
            metas.append({
                "document_id": m.get("document_id") or "",
                "kb_id": m.get("kb_id") or "",
                "title": m.get("title") or "",
                "heading_path": m.get("heading_path") or "",
                "chunk_type": m.get("chunk_type") or "paragraph",
            })
            ids.append(m.get("chromadb_id") or m.get("chunk_id") or "")
        return docs, metas, ids

    # ── Rerank ──────────────────────────────────────────

    def _get_reranker(self):
        """懒加载 CrossEncoder 重排模型。"""
        if self._reranker_loaded:
            return self._reranker
        try:
            from sentence_transformers import CrossEncoder
            from backend.config import settings
            self._reranker = CrossEncoder(settings.KB_RERANK_MODEL)
            logger.info(f"[SearchEngine] reranker loaded: {settings.KB_RERANK_MODEL}")
        except Exception as e:
            logger.warning(f"[SearchEngine] reranker load failed: {e}")
            self._reranker = None
        self._reranker_loaded = True
        return self._reranker

    def _rerank(self, query: str, hits: List[Dict], top_n: int) -> List[Dict]:
        """使用 CrossEncoder 对候选结果精排。"""
        reranker = self._get_reranker()
        if reranker is None or not hits:
            return hits

        pairs = [[query, h["content"]] for h in hits]
        scores = reranker.predict(pairs)

        for i, h in enumerate(hits):
            h["rerank_score"] = float(scores[i])

        hits.sort(key=lambda x: x["rerank_score"], reverse=True)
        return hits[:top_n]

    # ── Tokenize for SQL LIKE ─────────────────────────────

    _STOPWORDS_CN = {
        "的", "了", "和", "是", "在", "有", "我", "你", "他", "她", "它",
        "我们", "你们", "他们", "这", "那", "什么", "怎么", "怎样", "如何",
        "吗", "呢", "啊", "呀", "吧", "嘛", "公司", "我们公司", "本公司",
        "贵公司", "多少", "多久", "能", "可以", "请问", "一下", "相关", "信息",
    }

    @classmethod
    def _tokenize_for_like(cls, query: str) -> List[str]:
        """将 query 切分为用于 SQL LIKE 的 token 列表。

        - 用 jieba 做中文分词；不可用时按空格切
        - 过滤 ≤1 字 token、停用词、纯空白
        - 去重，保持原顺序
        - 最多保留 8 个 token，避免 SQL 过长
        """
        if not query or not query.strip():
            return []
        try:
            import jieba  # type: ignore
            raw = list(jieba.cut(query))
        except Exception:
            raw = []
            for part in re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]{2,}", query):
                if re.fullmatch(r"[\u4e00-\u9fff]+", part) and len(part) > 4:
                    raw.extend(part[i:i + 2] for i in range(len(part) - 1))
                else:
                    raw.append(part)

        seen = set()
        tokens: List[str] = []
        for t in raw:
            t = t.strip()
            if not t or len(t) <= 1:
                continue
            if t in cls._STOPWORDS_CN:
                continue
            if t in seen:
                continue
            seen.add(t)
            tokens.append(t)
            if len(tokens) >= 8:
                break
        return tokens

    @classmethod
    def _has_query_term_overlap(cls, query: str, hits: List[Dict]) -> bool:
        terms = cls._tokenize_for_like(query)
        if not terms:
            return True
        haystack = "\n".join(
            f"{h.get('title', '')}\n{h.get('heading_path', '')}\n{h.get('content', '')}"
            for h in hits
        ).lower()
        return any(term.lower() in haystack for term in terms)

    # ── 置信度分析 ────────────────────────────────────────

    @staticmethod
    def _analyze_confidence(
        hits: List[Dict], settings, degraded: bool = False
    ) -> Dict[str, Any]:
        """根据 top 结果分数分析置信度（v2 §2.2）。

        变更点：
          1. 新增 low 档（LOW 下界 <= score < MEDIUM）和 none 档（score < LOW）
          2. ambiguous 升级为独立的 confidence 类型，不再仅做 bool 标志
          3. degraded=True 时 score 扣 KB_DEGRADED_CONF_PENALTY
          4. top1/top2 跨 kb_id 且 gap < AMBIGUOUS_GAP → ambiguous(reason=cross_kb_tie)
          5. 返回新增 ambiguous_reason 字段（None / "small_gap" / "cross_kb_tie"）
        """
        if not hits:
            return {
                "confidence": "none",
                "confidence_score": 0.0,
                "ambiguous": False,
                "ambiguous_reason": None,
                "suggestion": "transfer_human",
            }

        top1_score = hits[0].get("rerank_score", hits[0].get("score", 0))
        top2_score = hits[1].get("rerank_score", hits[1].get("score", 0)) if len(hits) >= 2 else 0.0
        gap = top1_score - top2_score

        # degraded 扣分：来自 SQL LIKE / BM25-only 等降级路径的结果把最终 score 压低
        penalty = settings.KB_DEGRADED_CONF_PENALTY if degraded else 0.0
        score = max(top1_score - penalty, 0.0)

        # 跨库检测：top1 vs top2 来自不同 kb_id 且分差小 → 跨库干扰
        top1_kb = hits[0].get("kb_id")
        top2_kb = hits[1].get("kb_id") if len(hits) >= 2 else None
        cross_kb = bool(top1_kb and top2_kb and top1_kb != top2_kb)

        # ambiguous 判定（优先级高于阈值档）
        if len(hits) >= 2 and gap < settings.KB_AMBIGUOUS_GAP:
            ambiguous_reason = "cross_kb_tie" if cross_kb else "small_gap"
            return {
                "confidence": "ambiguous",
                "confidence_score": round(score, 4),
                "ambiguous": True,
                "ambiguous_reason": ambiguous_reason,
                "suggestion": "disambiguate",
            }

        # 阈值档判定（用扣分后的 score）
        if score >= settings.KB_CONFIDENCE_HIGH:
            confidence, suggestion = "high", "direct_answer"
        elif score >= settings.KB_CONFIDENCE_MEDIUM:
            confidence, suggestion = "medium", "show_candidates"
        elif score >= settings.KB_CONFIDENCE_LOW:
            confidence, suggestion = "low", "fallback_faq"
        else:
            confidence, suggestion = "none", "transfer_human"

        return {
            "confidence": confidence,
            "confidence_score": round(score, 4),
            "ambiguous": False,
            "ambiguous_reason": None,
            "suggestion": suggestion,
        }

    def invalidate_bm25_cache(self, kb_id: Optional[str] = None):
        """清除 BM25 缓存（§2.1 Layer 3：cache key 已改为 ``kb_id``）。

        - ``kb_id`` 给定 → 仅清该 kb 的索引
        - ``kb_id=None`` → 全清
        """
        if kb_id:
            self._bm25_cache.pop(kb_id, None)
        else:
            self._bm25_cache.clear()

    def _hybrid_search(
        self, query: str, collections: List[Dict], top_k: int, min_score: float
    ) -> List[Dict]:
        """混合检索: vector + BM25 + RRF 融合。"""
        vec_hits = self._vector_search(query, collections, top_k * 2, min_score)
        bm25_hits = self._bm25_search(query, collections, top_k * 2)

        if not vec_hits and not bm25_hits:
            return []
        if not bm25_hits:
            return vec_hits[:top_k]
        if not vec_hits:
            return bm25_hits[:top_k]

        # RRF 融合
        return self._rrf_merge(vec_hits, bm25_hits, top_k)

    @staticmethod
    def _rrf_merge(list_a: List[Dict], list_b: List[Dict], top_k: int, k: int = 60) -> List[Dict]:
        """Reciprocal Rank Fusion（v2 §2.2 B）。

        变更：若 top_k 候选全部来自同一 kb_id，每个 score * 1.1 作为同库 bonus；
        跨库混合不加 bonus。避免“多库分数都不高但 RRF 后错排第一”的案例。
        """
        scores: Dict[str, float] = {}
        items: Dict[str, Dict] = {}
        relevance_scores: Dict[str, float] = {}

        for rank, hit in enumerate(list_a):
            key = hit.get("chunk_id", str(rank))
            scores[key] = scores.get(key, 0) + 1 / (k + rank + 1)
            items[key] = hit
            relevance_scores[key] = max(relevance_scores.get(key, 0.0), float(hit.get("score", 0) or 0))

        for rank, hit in enumerate(list_b):
            key = hit.get("chunk_id", str(rank))
            scores[key] = scores.get(key, 0) + 1 / (k + rank + 1)
            if key not in items:
                items[key] = hit
            relevance_scores[key] = max(relevance_scores.get(key, 0.0), float(hit.get("score", 0) or 0))

        sorted_keys = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        top_keys = sorted_keys[:top_k]

        # 同库 bonus：top_k 候选全部同 kb_id 时轻微加权（折合 1.1）
        if top_keys:
            top_kb_ids = {items[key].get("kb_id") for key in top_keys if items[key].get("kb_id")}
            same_kb_bonus = 1.1 if len(top_kb_ids) == 1 else 1.0
        else:
            same_kb_bonus = 1.0

        result = []
        for key in top_keys:
            hit = items[key]
            hit["rrf_score"] = round(scores[key], 4)
            hit["score"] = round(min(relevance_scores.get(key, hit.get("score", 0)) * same_kb_bonus, 1.0), 4)
            hit["search_mode"] = "hybrid"
            result.append(hit)
        return result

    def _sql_fallback(self, query: str, kb_ids: Optional[List[str]], top_k: int) -> List[Dict]:
        """SQL LIKE 降级检索。

        改进：用 jieba 分词后逐 token OR 匹配，避免"整串 LIKE"遇到
        LLM 扩展多词 query 时全部 miss。按 (命中 token 占比 × 最长 token 密度)
        综合打分。
        """
        from sqlalchemy import text as sa_text
        try:
            from backend.database import SessionLocal
            db = SessionLocal()
            try:
                tokens = self._tokenize_for_like(query)
                if tokens:
                    # 分词 OR 匹配：每个 token 独立 LIKE，OR 连接
                    like_clauses = " OR ".join([f"c.content LIKE :tok{i}" for i in range(len(tokens))])
                    params: Dict[str, Any] = {f"tok{i}": f"%{tok}%" for i, tok in enumerate(tokens)}
                    params["lim"] = top_k * 3  # 多召回一些，Python 侧重排后截断

                    if kb_ids:
                        ph = ",".join([f":id{i}" for i in range(len(kb_ids))])
                        for i, kid in enumerate(kb_ids):
                            params[f"id{i}"] = kid
                        sql = (
                            f"SELECT c.chunk_id, c.document_id, c.kb_id, c.content, "
                            f"c.heading_path, c.chunk_type, d.title "
                            f"FROM kb_chunks c JOIN kb_documents d ON c.document_id=d.document_id "
                            f"WHERE c.kb_id IN ({ph}) AND ({like_clauses}) "
                            f"LIMIT :lim"
                        )
                    else:
                        sql = (
                            f"SELECT c.chunk_id, c.document_id, c.kb_id, c.content, "
                            f"c.heading_path, c.chunk_type, d.title "
                            f"FROM kb_chunks c JOIN kb_documents d ON c.document_id=d.document_id "
                            f"WHERE ({like_clauses}) LIMIT :lim"
                        )
                    rows = db.execute(sa_text(sql), params).fetchall()
                else:
                    # 分词失败（纯符号等）→ 回退到原整串 LIKE
                    tokens = [query[:30]]
                    q = query[:30]
                    if kb_ids:
                        ph = ",".join([f":id{i}" for i in range(len(kb_ids))])
                        params = {f"id{i}": kid for i, kid in enumerate(kb_ids)}
                        params["q"] = f"%{q}%"
                        params["lim"] = top_k
                        rows = db.execute(sa_text(
                            f"SELECT c.chunk_id, c.document_id, c.kb_id, c.content, "
                            f"c.heading_path, c.chunk_type, d.title "
                            f"FROM kb_chunks c JOIN kb_documents d ON c.document_id=d.document_id "
                            f"WHERE c.kb_id IN ({ph}) AND c.content LIKE :q "
                            f"LIMIT :lim"
                        ), params).fetchall()
                    else:
                        rows = db.execute(sa_text(
                            "SELECT c.chunk_id, c.document_id, c.kb_id, c.content, "
                            "c.heading_path, c.chunk_type, d.title "
                            "FROM kb_chunks c JOIN kb_documents d ON c.document_id=d.document_id "
                            "WHERE c.content LIKE :q LIMIT :lim"
                        ), {"q": f"%{q}%", "lim": top_k}).fetchall()

                hits = []
                total_tokens = len(tokens)
                for r in rows:
                    content = r._mapping["content"]
                    c_lower = content.lower()
                    # 综合打分：命中 token 占比 × 0.6 + 最长 token 密度 × 0.4
                    hit_count = sum(1 for t in tokens if t.lower() in c_lower)
                    coverage = hit_count / max(total_tokens, 1)
                    longest = max(tokens, key=len) if tokens else ""
                    density = min(
                        c_lower.count(longest.lower()) * len(longest) / max(len(content), 1),
                        1.0,
                    ) if longest else 0
                    # v2 §2.2 C：保底分降低（0.3 → 0.15）且增量系数降低（0.5 → 0.45）
                    # 配合 MEDIUM=0.55，sql_like 结果幾乎不会进入 medium 以上，避免误导
                    score = round(0.15 + 0.45 * (coverage * 0.6 + density * 0.4), 3)
                    hits.append({
                        "chunk_id": r._mapping["chunk_id"],
                        "document_id": r._mapping["document_id"],
                        "kb_id": r._mapping["kb_id"],
                        "kb_name": "",
                        "title": r._mapping.get("title", ""),
                        "content": content,
                        "score": score,
                        "heading_path": r._mapping.get("heading_path", ""),
                        "chunk_type": r._mapping.get("chunk_type", "paragraph"),
                        "search_mode": "sql_like",
                        "metadata": {},
                    })
                hits.sort(key=lambda x: x["score"], reverse=True)
                return hits[:top_k]
            finally:
                db.close()
        except Exception as e:
            logger.debug(f"[SearchEngine] SQL fallback failed: {e}")
            return []
