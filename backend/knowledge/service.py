# -*- coding: utf-8 -*-
"""backend/knowledge/service.py — 知识库中台 Service 层

统一编排层，负责：
  - 知识库 CRUD
  - 文档生命周期管理（入库/处理/删除）
  - 委托 SearchEngine 执行检索
  - 向量化写入 ChromaDB
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from loguru import logger


class KnowledgeBaseService:
    """知识库中台统一服务。"""

    _instance: KnowledgeBaseService | None = None

    @classmethod
    def get_instance(cls) -> KnowledgeBaseService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ══════════════════════════════════════════════════════════
    #  知识库 CRUD
    # ══════════════════════════════════════════════════════════

    def create_library(self, db, *, name: str, display_name: str,
                       description: str = "", domain: str = "enterprise",
                       chunk_strategy: str = "recursive",
                       chunk_config: Optional[Dict] = None,
                       created_by: str = "system") -> Dict[str, Any]:
        """创建知识库 → MySQL + ChromaDB collection。"""
        from sqlalchemy import text as sa_text
        from backend.core.vector_store import VectorStoreManager

        kb_id = str(uuid.uuid4())
        col_name = f"kb_{kb_id[:8]}"

        import json
        chunk_cfg_json = json.dumps(chunk_config) if chunk_config else None

        db.execute(sa_text(
            "INSERT INTO kb_libraries "
            "(kb_id, name, display_name, description, domain, collection_name, "
            " chunk_strategy, chunk_config, created_by) "
            "VALUES (:kb_id, :name, :dn, :desc, :domain, :col, :cs, :cc, :cb)"
        ), {
            "kb_id": kb_id, "name": name, "dn": display_name,
            "desc": description, "domain": domain, "col": col_name,
            "cs": chunk_strategy, "cc": chunk_cfg_json, "cb": created_by,
        })
        db.commit()

        store = VectorStoreManager.get_instance()
        store.register_collection(col_name, owner="knowledge", description=display_name)
        logger.info(f"[KBService] created library: {name} ({kb_id})")
        return {"kb_id": kb_id, "name": name, "collection_name": col_name}

    def list_libraries(self, db, domain: Optional[str] = None,
                       active_only: bool = True) -> List[Dict]:
        from sqlalchemy import text as sa_text
        where = "WHERE 1=1"
        params: Dict[str, Any] = {}
        if active_only:
            where += " AND is_active=1"
        if domain:
            where += " AND domain=:domain"
            params["domain"] = domain
        rows = db.execute(sa_text(
            f"SELECT * FROM kb_libraries {where} ORDER BY created_at DESC"
        ), params).fetchall()
        return [dict(r._mapping) for r in rows]

    def get_library(self, db, kb_id: str) -> Optional[Dict]:
        from sqlalchemy import text as sa_text
        row = db.execute(sa_text(
            "SELECT * FROM kb_libraries WHERE kb_id=:id"
        ), {"id": kb_id}).fetchone()
        return dict(row._mapping) if row else None

    def delete_library(self, db, kb_id: str) -> bool:
        """删除知识库 → MySQL CASCADE + ChromaDB。"""
        from sqlalchemy import text as sa_text
        from backend.core.vector_store import VectorStoreManager

        lib = self.get_library(db, kb_id)
        if not lib:
            return False
        col_name = lib["collection_name"]

        db.execute(sa_text("DELETE FROM kb_libraries WHERE kb_id=:id"), {"id": kb_id})
        db.commit()

        store = VectorStoreManager.get_instance()
        store.delete_collection(col_name)
        logger.info(f"[KBService] deleted library: {kb_id}")
        return True

    # ══════════════════════════════════════════════════════════
    #  文档入库（FAQ 手动 + 文件上传通用）
    # ══════════════════════════════════════════════════════════

    async def ingest_document(
        self, db, *,
        kb_id: str, title: str,
        raw_text: Optional[str] = None,
        file_path: Optional[str] = None,
        source_type: str = "faq_manual",
        created_by: str = "system",
        group_name: str = "",
    ) -> Dict[str, Any]:
        """入库文档：处理 → 分块 → 向量化 → 写 MySQL + ChromaDB。"""
        from sqlalchemy import text as sa_text
        from pathlib import Path
        from backend.core.embedding import EmbeddingService
        from backend.core.vector_store import VectorStoreManager
        from backend.knowledge.doc_processor import process_document
        from backend.config import settings

        lib = self.get_library(db, kb_id)
        if not lib:
            return {"error": "kb_not_found", "document_id": None}

        col_name = lib["collection_name"]
        chunk_strategy = lib.get("chunk_strategy", "recursive")
        chunk_config = lib.get("chunk_config") or {}
        if isinstance(chunk_config, str):
            import json
            chunk_config = json.loads(chunk_config)
        max_tokens = chunk_config.get("max_tokens", settings.KB_DEFAULT_CHUNK_MAX_TOKENS)
        overlap = chunk_config.get("overlap", settings.KB_DEFAULT_CHUNK_OVERLAP)

        doc_id = str(uuid.uuid4())

        # 运行处理管线
        fp = Path(file_path) if file_path else None
        proc = process_document(
            file_path=fp, raw_text=raw_text, title=title,
            chunk_strategy=chunk_strategy,
            chunk_max_tokens=max_tokens, chunk_overlap=overlap,
            min_quality_score=settings.KB_QUALITY_MIN_SCORE,
            pii_policy=settings.KB_PII_POLICY,
        )

        status = "ready" if proc.success else "failed"
        quality_score = proc.quality.score if proc.quality else None

        # 写文档记录
        db.execute(sa_text(
            "INSERT INTO kb_documents "
            "(document_id, kb_id, title, source_type, content_raw, content_clean, "
            " status, quality_score, chunk_count, error_msg, created_by) "
            "VALUES (:did, :kid, :t, :st, :cr, :cc, :s, :qs, :cnt, :err, :cb)"
        ), {
            "did": doc_id, "kid": kb_id, "t": title, "st": source_type,
            "cr": proc.content_raw[:65000] if proc.content_raw else None,
            "cc": proc.content_clean[:65000] if proc.content_clean else None,
            "s": status, "qs": quality_score,
            "cnt": len(proc.chunks), "err": proc.error, "cb": created_by,
        })

        if not proc.success:
            db.commit()
            return {"document_id": doc_id, "status": status,
                    "error": proc.error, "warnings": proc.warnings}

        # 写 chunks + 向量化
        embedding = EmbeddingService.get_instance()
        store = VectorStoreManager.get_instance()
        col = store.get_collection(col_name)

        chunk_texts = [c.content for c in proc.chunks]
        try:
            vectors = embedding.embed(chunk_texts)
        except Exception as e:
            logger.warning(f"[KBService] embedding failed: {e}")
            db.execute(sa_text(
                "UPDATE kb_documents SET status='failed', error_msg=:e WHERE document_id=:did"
            ), {"e": f"embedding_failed:{e}", "did": doc_id})
            db.commit()
            return {"document_id": doc_id, "status": "failed", "error": str(e)}

        chroma_ids = []
        for i, chunk in enumerate(proc.chunks):
            chunk_id = str(uuid.uuid4())
            chromadb_id = f"{doc_id}__{i}"
            chroma_ids.append(chromadb_id)

            db.execute(sa_text(
                "INSERT INTO kb_chunks "
                "(chunk_id, document_id, kb_id, chunk_index, content, "
                " token_count, char_count, heading_path, chunk_type, "
                " chromadb_id, embedding_status) "
                "VALUES (:cid, :did, :kid, :idx, :content, "
                " :tc, :cc, :hp, :ct, :chid, 'done')"
            ), {
                "cid": chunk_id, "did": doc_id, "kid": kb_id, "idx": i,
                "content": chunk.content, "tc": chunk.token_count,
                "cc": chunk.char_count, "hp": chunk.heading_path,
                "ct": chunk.chunk_type, "chid": chromadb_id,
            })

        # 写入 ChromaDB
        metadatas = [
            {
                "document_id": doc_id, "kb_id": kb_id, "title": title,
                "chunk_index": i, "heading_path": c.heading_path or "",
                "chunk_type": c.chunk_type, "group_name": group_name,
            }
            for i, c in enumerate(proc.chunks)
        ]

        try:
            col.upsert(
                ids=chroma_ids,
                embeddings=vectors,
                documents=chunk_texts,
                metadatas=metadatas,
            )
        except Exception as e:
            logger.warning(f"[KBService] ChromaDB upsert failed: {e}")
            db.execute(sa_text(
                "UPDATE kb_documents SET status='failed', error_msg=:e WHERE document_id=:did"
            ), {"e": f"chromadb_failed:{e}", "did": doc_id})

        # 更新知识库计数
        db.execute(sa_text(
            "UPDATE kb_libraries SET doc_count=doc_count+1, "
            "chunk_count=chunk_count+:cc WHERE kb_id=:kid"
        ), {"cc": len(proc.chunks), "kid": kb_id})
        db.commit()

        # 清除 BM25 缓存（§2.1 Layer 3：cache key 已按 kb_id）
        try:
            from backend.knowledge.search_engine import SearchEngine
            SearchEngine.get_instance().invalidate_bm25_cache(kb_id)
        except Exception:
            pass

        logger.info(f"[KBService] ingested doc={doc_id} chunks={len(proc.chunks)}")
        return {
            "document_id": doc_id, "status": status,
            "chunk_count": len(proc.chunks),
            "quality_score": quality_score,
            "warnings": proc.warnings,
        }

    # ══════════════════════════════════════════════════════════
    #  文档删除
    # ══════════════════════════════════════════════════════════

    async def delete_document(self, db, document_id: str) -> bool:
        """删除文档 → MySQL CASCADE + ChromaDB 向量。"""
        from sqlalchemy import text as sa_text
        from backend.core.vector_store import VectorStoreManager

        # 查文档所属库
        row = db.execute(sa_text(
            "SELECT d.kb_id, d.chunk_count, l.collection_name "
            "FROM kb_documents d JOIN kb_libraries l ON d.kb_id=l.kb_id "
            "WHERE d.document_id=:did"
        ), {"did": document_id}).fetchone()
        if not row:
            return False

        info = dict(row._mapping)
        col_name = info["collection_name"]
        kb_id = info["kb_id"]
        chunk_cnt = info["chunk_count"]

        # 获取 chromadb_ids
        chunks = db.execute(sa_text(
            "SELECT chromadb_id FROM kb_chunks WHERE document_id=:did"
        ), {"did": document_id}).fetchall()
        chroma_ids = [r._mapping["chromadb_id"] for r in chunks if r._mapping.get("chromadb_id")]

        # 删 MySQL（CASCADE 删 chunks）
        db.execute(sa_text("DELETE FROM kb_documents WHERE document_id=:did"), {"did": document_id})
        db.execute(sa_text(
            "UPDATE kb_libraries SET doc_count=GREATEST(doc_count-1,0), "
            "chunk_count=GREATEST(chunk_count-:cc,0) WHERE kb_id=:kid"
        ), {"cc": chunk_cnt, "kid": kb_id})
        db.commit()

        # 删 ChromaDB
        if chroma_ids:
            try:
                store = VectorStoreManager.get_instance()
                col = store.get_collection(col_name)
                col.delete(ids=chroma_ids)
            except Exception as e:
                logger.warning(f"[KBService] ChromaDB delete failed: {e}")

        # 清 BM25 缓存（§2.1 Layer 3：cache key 已按 kb_id）
        try:
            from backend.knowledge.search_engine import SearchEngine
            SearchEngine.get_instance().invalidate_bm25_cache(kb_id)
        except Exception:
            pass

        logger.info(f"[KBService] deleted doc={document_id}")
        return True

    # ══════════════════════════════════════════════════════════
    #  文档列表 / 详情
    # ══════════════════════════════════════════════════════════

    def list_documents(self, db, kb_id: str, status: Optional[str] = None,
                       limit: int = 50, offset: int = 0) -> Dict:
        from sqlalchemy import text as sa_text
        where = "WHERE kb_id=:kid"
        params: Dict[str, Any] = {"kid": kb_id, "lim": limit, "off": offset}
        if status:
            where += " AND status=:s"
            params["s"] = status
        total = db.execute(sa_text(
            f"SELECT COUNT(*) FROM kb_documents {where}"
        ), params).scalar() or 0
        rows = db.execute(sa_text(
            f"SELECT document_id, kb_id, title, source_type, file_name, "
            f"status, version, quality_score, chunk_count, error_msg, "
            f"created_by, created_at, updated_at "
            f"FROM kb_documents {where} ORDER BY created_at DESC LIMIT :lim OFFSET :off"
        ), params).fetchall()
        return {"items": [dict(r._mapping) for r in rows], "total": total}

    def get_document(self, db, document_id: str) -> Optional[Dict]:
        from sqlalchemy import text as sa_text
        row = db.execute(sa_text(
            "SELECT * FROM kb_documents WHERE document_id=:did"
        ), {"did": document_id}).fetchone()
        return dict(row._mapping) if row else None

    def list_chunks(self, db, document_id: str) -> Dict:
        from sqlalchemy import text as sa_text
        rows = db.execute(sa_text(
            "SELECT chunk_id, document_id, kb_id, chunk_index, content, "
            "token_count, char_count, heading_path, chunk_type, "
            "chromadb_id, embedding_status, created_at "
            "FROM kb_chunks WHERE document_id=:did ORDER BY chunk_index"
        ), {"did": document_id}).fetchall()
        return {"items": [dict(r._mapping) for r in rows]}

    # ══════════════════════════════════════════════════════════
    #  版本管理
    # ══════════════════════════════════════════════════════════

    def _snapshot_version(self, db, document_id: str) -> Optional[str]:
        """将文档当前内容快照到 kb_document_versions 表。返回 version_id。"""
        from sqlalchemy import text as sa_text
        doc = self.get_document(db, document_id)
        if not doc:
            return None
        ver_id = str(uuid.uuid4())
        db.execute(sa_text(
            "INSERT INTO kb_document_versions "
            "(version_id, document_id, version, content_raw, content_clean, "
            " quality_score, chunk_count, created_by) "
            "VALUES (:vid, :did, :ver, :cr, :cc, :qs, :cnt, :cb)"
        ), {
            "vid": ver_id, "did": document_id, "ver": doc.get("version", 1),
            "cr": doc.get("content_raw"), "cc": doc.get("content_clean"),
            "qs": doc.get("quality_score"), "cnt": doc.get("chunk_count", 0),
            "cb": doc.get("created_by", "system"),
        })
        return ver_id

    def list_versions(self, db, document_id: str) -> Dict:
        from sqlalchemy import text as sa_text
        rows = db.execute(sa_text(
            "SELECT version_id, document_id, version, quality_score, "
            "chunk_count, created_by, created_at "
            "FROM kb_document_versions WHERE document_id=:did "
            "ORDER BY version DESC"
        ), {"did": document_id}).fetchall()
        return {"items": [dict(r._mapping) for r in rows]}

    def get_version_detail(self, db, version_id: str) -> Optional[Dict]:
        from sqlalchemy import text as sa_text
        row = db.execute(sa_text(
            "SELECT * FROM kb_document_versions WHERE version_id=:vid"
        ), {"vid": version_id}).fetchone()
        return dict(row._mapping) if row else None

    def rollback_document(self, db, document_id: str,
                          target_version: int,
                          user: str = "system") -> Dict[str, Any]:
        """回退文档到指定版本：快照当前 → 恢复旧内容 → version+1。"""
        from sqlalchemy import text as sa_text

        doc = self.get_document(db, document_id)
        if not doc:
            return {"error": "document_not_found"}

        ver_row = db.execute(sa_text(
            "SELECT * FROM kb_document_versions "
            "WHERE document_id=:did AND version=:ver"
        ), {"did": document_id, "ver": target_version}).fetchone()
        if not ver_row:
            return {"error": f"version {target_version} not found"}
        old = dict(ver_row._mapping)

        self._snapshot_version(db, document_id)

        new_version = doc.get("version", 1) + 1
        db.execute(sa_text(
            "UPDATE kb_documents SET "
            "content_raw=:cr, content_clean=:cc, quality_score=:qs, "
            "version=:ver, updated_at=NOW(3) "
            "WHERE document_id=:did"
        ), {
            "cr": old.get("content_raw"), "cc": old.get("content_clean"),
            "qs": old.get("quality_score"), "ver": new_version,
            "did": document_id,
        })
        db.commit()

        logger.info(f"[KBService] rollback doc={document_id} to v{target_version}, now v{new_version}")
        return {
            "document_id": document_id,
            "rolled_back_to": target_version,
            "new_version": new_version,
        }

    async def reprocess_document(self, db, document_id: str,
                                 user: str = "system") -> Dict[str, Any]:
        """重新处理文档：快照当前 → 用 content_raw 重新走 pipeline → version+1。"""
        from sqlalchemy import text as sa_text

        doc = self.get_document(db, document_id)
        if not doc:
            return {"error": "document_not_found"}

        self._snapshot_version(db, document_id)

        kb_id = doc["kb_id"]
        new_version = doc.get("version", 1) + 1
        raw_text = doc.get("content_raw") or ""
        title = doc.get("title", "")

        lib = self.get_library(db, kb_id)
        if not lib:
            return {"error": "kb_not_found"}

        from backend.knowledge.doc_processor import process_document
        from backend.config import settings
        import json

        chunk_config = lib.get("chunk_config") or {}
        if isinstance(chunk_config, str):
            chunk_config = json.loads(chunk_config)

        proc = process_document(
            file_path=None, raw_text=raw_text, title=title,
            chunk_strategy=lib.get("chunk_strategy", "recursive"),
            chunk_max_tokens=chunk_config.get("max_tokens", settings.KB_DEFAULT_CHUNK_MAX_TOKENS),
            chunk_overlap=chunk_config.get("overlap", settings.KB_DEFAULT_CHUNK_OVERLAP),
            min_quality_score=settings.KB_QUALITY_MIN_SCORE,
            pii_policy=settings.KB_PII_POLICY,
        )

        status = "ready" if proc.success else "failed"
        quality_score = proc.quality.score if proc.quality else None

        db.execute(sa_text(
            "UPDATE kb_documents SET content_clean=:cc, status=:s, "
            "quality_score=:qs, chunk_count=:cnt, version=:ver, "
            "error_msg=:err, updated_at=NOW(3) "
            "WHERE document_id=:did"
        ), {
            "cc": proc.content_clean[:65000] if proc.content_clean else None,
            "s": status, "qs": quality_score, "cnt": len(proc.chunks),
            "ver": new_version, "err": proc.error, "did": document_id,
        })

        # 删旧 chunks
        db.execute(sa_text(
            "DELETE FROM kb_chunks WHERE document_id=:did"
        ), {"did": document_id})

        if proc.success and proc.chunks:
            from backend.core.embedding import EmbeddingService
            from backend.core.vector_store import VectorStoreManager

            col_name = lib["collection_name"]
            embedding = EmbeddingService.get_instance()
            store = VectorStoreManager.get_instance()
            col = store.get_collection(col_name)

            chunk_texts = [c.content for c in proc.chunks]
            try:
                vectors = embedding.embed(chunk_texts)
            except Exception as e:
                logger.warning(f"[KBService] reprocess embedding failed: {e}")
                db.execute(sa_text(
                    "UPDATE kb_documents SET status='failed', error_msg=:e WHERE document_id=:did"
                ), {"e": f"embedding_failed:{e}", "did": document_id})
                db.commit()
                return {"document_id": document_id, "status": "failed", "error": str(e)}

            chroma_ids = []
            for i, chunk in enumerate(proc.chunks):
                chunk_id = str(uuid.uuid4())
                chromadb_id = f"{document_id}__{i}"
                chroma_ids.append(chromadb_id)
                db.execute(sa_text(
                    "INSERT INTO kb_chunks "
                    "(chunk_id, document_id, kb_id, chunk_index, content, "
                    " token_count, char_count, heading_path, chunk_type, "
                    " chromadb_id, embedding_status) "
                    "VALUES (:cid, :did, :kid, :idx, :content, "
                    " :tc, :cc, :hp, :ct, :chid, 'done')"
                ), {
                    "cid": chunk_id, "did": document_id, "kid": kb_id, "idx": i,
                    "content": chunk.content, "tc": chunk.token_count,
                    "cc": chunk.char_count, "hp": chunk.heading_path,
                    "ct": chunk.chunk_type, "chid": chromadb_id,
                })

            metadatas = [
                {"document_id": document_id, "kb_id": kb_id, "title": title,
                 "chunk_index": i, "heading_path": c.heading_path or "", "chunk_type": c.chunk_type}
                for i, c in enumerate(proc.chunks)
            ]
            try:
                col.upsert(ids=chroma_ids, embeddings=vectors,
                           documents=chunk_texts, metadatas=metadatas)
            except Exception as e:
                logger.warning(f"[KBService] reprocess ChromaDB upsert failed: {e}")

        # 自愈式重算 kb_libraries.chunk_count：reprocess 会改变该文档的 chunk 数，
        # 为避免冗余字段漂移（ingest 时 +cc，reprocess 时若仅 +delta 一旦历史值已漂就越漂越远），
        # 这里直接用真实 COUNT 回写。单 kb 的 COUNT 走 idx_kb_id 索引，开销可忽略。
        db.execute(sa_text(
            "UPDATE kb_libraries SET chunk_count = "
            "(SELECT COUNT(*) FROM kb_chunks WHERE kb_id=:kid) "
            "WHERE kb_id=:kid"
        ), {"kid": kb_id})

        db.commit()

        # 清 BM25 缓存（§2.1 Layer 3：reprocess 后 chunk 已换，避免旧索引参与检索）
        try:
            from backend.knowledge.search_engine import SearchEngine
            SearchEngine.get_instance().invalidate_bm25_cache(kb_id)
        except Exception:
            pass

        logger.info(f"[KBService] reprocessed doc={document_id} v{new_version}")
        return {
            "document_id": document_id, "new_version": new_version,
            "status": status, "chunk_count": len(proc.chunks),
        }

    # ══════════════════════════════════════════════════════════
    #  统一检索（委托 SearchEngine）
    # ══════════════════════════════════════════════════════════

    def search(self, query: str, kb_ids: Optional[List[str]] = None,
               top_k: int = 5, min_score: float = 0.3,
               mode: str = "hybrid") -> Dict[str, Any]:
        from backend.knowledge.search_engine import SearchEngine
        return SearchEngine.get_instance().search(
            query=query, kb_ids=kb_ids, top_k=top_k,
            min_score=min_score, mode=mode,
        )

    # ══════════════════════════════════════════════════════════
    #  统计
    # ══════════════════════════════════════════════════════════

    def get_stats(self, db, kb_id: Optional[str] = None) -> Dict[str, Any]:
        from sqlalchemy import text as sa_text
        if kb_id:
            row = db.execute(sa_text(
                "SELECT doc_count, chunk_count FROM kb_libraries WHERE kb_id=:id"
            ), {"id": kb_id}).fetchone()
            if row:
                return dict(row._mapping)
        total_docs = db.execute(sa_text(
            "SELECT COUNT(*) FROM kb_documents WHERE status='ready'"
        )).scalar() or 0
        total_chunks = db.execute(sa_text(
            "SELECT COUNT(*) FROM kb_chunks WHERE embedding_status='done'"
        )).scalar() or 0
        total_libs = db.execute(sa_text(
            "SELECT COUNT(*) FROM kb_libraries WHERE is_active=1"
        )).scalar() or 0
        return {
            "total_libraries": total_libs,
            "total_documents": total_docs,
            "total_chunks": total_chunks,
        }
