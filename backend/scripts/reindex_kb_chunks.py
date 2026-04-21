# -*- coding: utf-8 -*-
"""backend/scripts/reindex_kb_chunks.py — 为 pending chunks 生成向量并写入 Chroma。

使用场景：
  - seed SQL 只写了 MySQL 三张表（kb_libraries / kb_documents / kb_chunks），
    但未跑 embedding 导致 kb_chunks.embedding_status='pending'、chromadb_id=NULL
  - 模型加载修复后，需要一次性把所有 pending chunks 补索引到 Chroma

流程：
  1. 查 kb_chunks WHERE embedding_status='pending'
  2. 按 kb_id 分组，取 kb_libraries.collection_name
  3. 批量生成 embedding（bge-small-zh-v1.5）
  4. col.upsert(ids, embeddings, documents, metadatas)
  5. UPDATE kb_chunks SET embedding_status='done', chromadb_id=...

用法（容器内）：
  python -m backend.scripts.reindex_kb_chunks           # 只补 pending
  python -m backend.scripts.reindex_kb_chunks --all     # 全量重建（含 failed/done）
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from typing import Dict, List

from loguru import logger
from sqlalchemy import text as sa_text

from backend.core.embedding import EmbeddingService
from backend.core.vector_store import VectorStoreManager
from backend.database import SessionLocal


def fetch_chunks(db, only_pending: bool) -> List[Dict]:
    """获取需要重建索引的 chunks。"""
    where = "WHERE embedding_status='pending' OR embedding_status='failed' OR chromadb_id IS NULL" \
        if only_pending else "WHERE 1=1"
    rows = db.execute(sa_text(
        f"SELECT c.chunk_id, c.document_id, c.kb_id, c.chunk_index, c.content, "
        f"c.heading_path, c.chunk_type, d.title "
        f"FROM kb_chunks c JOIN kb_documents d ON c.document_id=d.document_id "
        f"{where} ORDER BY c.kb_id, c.document_id, c.chunk_index"
    )).fetchall()
    return [dict(r._mapping) for r in rows]


def fetch_kb_collections(db) -> Dict[str, Dict]:
    """kb_id -> {collection_name, name}"""
    rows = db.execute(sa_text(
        "SELECT kb_id, name, collection_name FROM kb_libraries"
    )).fetchall()
    return {r._mapping["kb_id"]: dict(r._mapping) for r in rows}


def reindex(only_pending: bool = True) -> Dict[str, int]:
    """执行重建索引。返回各 kb_id 下处理的 chunk 数。"""
    embedding = EmbeddingService.get_instance()
    store = VectorStoreManager.get_instance()

    db = SessionLocal()
    try:
        kb_map = fetch_kb_collections(db)
        chunks = fetch_chunks(db, only_pending)
        if not chunks:
            logger.info("[reindex] 没有需要处理的 chunks")
            return {}
        logger.info(f"[reindex] 待处理 chunks: {len(chunks)}")

        # 按 kb_id 分组
        by_kb: Dict[str, List[Dict]] = defaultdict(list)
        for c in chunks:
            by_kb[c["kb_id"]].append(c)

        result: Dict[str, int] = {}
        for kb_id, items in by_kb.items():
            kb = kb_map.get(kb_id)
            if not kb:
                logger.warning(f"[reindex] kb_id={kb_id} 未在 kb_libraries，跳过 {len(items)} chunks")
                continue

            col_name = kb["collection_name"]
            col = store.get_collection(col_name)

            # 批量生成 embedding
            texts = [c["content"] for c in items]
            logger.info(f"[reindex] embedding {len(texts)} chunks for kb={kb_id} col={col_name} ...")
            vectors = embedding.embed(texts)

            # 构造 Chroma 入库数据
            chroma_ids = [f"{c['document_id']}__{c['chunk_index']}" for c in items]
            metadatas = [
                {
                    "document_id": c["document_id"],
                    "kb_id": c["kb_id"],
                    "title": c.get("title") or "",
                    "chunk_index": c["chunk_index"],
                    "heading_path": c.get("heading_path") or "",
                    "chunk_type": c.get("chunk_type") or "paragraph",
                }
                for c in items
            ]
            col.upsert(ids=chroma_ids, embeddings=vectors, documents=texts, metadatas=metadatas)
            logger.info(f"[reindex] upserted {len(items)} vectors → {col_name}")

            # 更新 MySQL chunks 状态
            for c, chid in zip(items, chroma_ids):
                db.execute(sa_text(
                    "UPDATE kb_chunks SET embedding_status='done', chromadb_id=:chid "
                    "WHERE chunk_id=:cid"
                ), {"chid": chid, "cid": c["chunk_id"]})
            db.commit()
            result[kb_id] = len(items)

        return result
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Reindex kb_chunks into Chroma")
    parser.add_argument("--all", action="store_true",
                        help="全量重建（含 done 状态），默认只处理 pending/failed")
    args = parser.parse_args()

    try:
        result = reindex(only_pending=not args.all)
        total = sum(result.values())
        logger.info(f"[reindex] ✅ 完成，共处理 {total} chunks，分布: {result}")
        return 0
    except Exception as e:
        logger.exception(f"[reindex] 失败: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
