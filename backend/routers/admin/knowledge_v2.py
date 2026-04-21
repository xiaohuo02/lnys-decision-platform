# -*- coding: utf-8 -*-
"""backend/routers/admin/knowledge_v2.py — 知识库中台 v2 API

知识库管理：
  GET    /admin/knowledge/v2/libraries            → 知识库列表
  POST   /admin/knowledge/v2/libraries            → 创建知识库
  GET    /admin/knowledge/v2/libraries/{kb_id}     → 知识库详情
  DELETE /admin/knowledge/v2/libraries/{kb_id}     → 删除知识库

文档管理：
  GET    /admin/knowledge/v2/libraries/{kb_id}/documents    → 文档列表
  POST   /admin/knowledge/v2/libraries/{kb_id}/documents    → 新增文档(FAQ)
  GET    /admin/knowledge/v2/documents/{doc_id}             → 文档详情
  GET    /admin/knowledge/v2/documents/{doc_id}/chunks     → 文档分块列表
  GET    /admin/knowledge/v2/documents/{doc_id}/versions   → 版本列表
  POST   /admin/knowledge/v2/documents/{doc_id}/rollback   → 回退到指定版本
  POST   /admin/knowledge/v2/documents/{doc_id}/reprocess  → 重新处理文档
  DELETE /admin/knowledge/v2/documents/{doc_id}             → 删除文档

统一检索：
  POST   /admin/knowledge/v2/search               → 统一检索

统计：
  GET    /admin/knowledge/v2/stats                 → 总体统计

§3.4 反馈：
  GET    /admin/knowledge/v2/feedback              → 反馈列表（分页 + 过滤）
  GET    /admin/knowledge/v2/feedback/stats        → 反馈聚合（窗口期）
"""
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from loguru import logger

from backend.database import get_db
from backend.middleware.auth import admin_user, CurrentUser
from backend.knowledge.schemas import (
    KBLibraryCreate, KBDocumentCreate, SearchRequest,
)

router = APIRouter(tags=["admin-knowledge-v2"])


# ── 知识库 CRUD ──────────────────────────────────────────────────

@router.get("/knowledge/v2/libraries")
def list_libraries(
    domain: Optional[str] = None,
    user: CurrentUser = Depends(admin_user),
    db: Session = Depends(get_db),
):
    from backend.knowledge.service import KnowledgeBaseService
    svc = KnowledgeBaseService.get_instance()
    return {"items": svc.list_libraries(db, domain=domain)}


@router.post("/knowledge/v2/libraries")
def create_library(
    body: KBLibraryCreate,
    user: CurrentUser = Depends(admin_user),
    db: Session = Depends(get_db),
):
    from backend.knowledge.service import KnowledgeBaseService
    svc = KnowledgeBaseService.get_instance()
    result = svc.create_library(
        db, name=body.name, display_name=body.display_name,
        description=body.description or "", domain=body.domain,
        chunk_strategy=body.chunk_strategy,
        chunk_config=body.chunk_config,
        created_by=user.username,
    )
    return result


@router.get("/knowledge/v2/libraries/{kb_id}")
def get_library(
    kb_id: str,
    user: CurrentUser = Depends(admin_user),
    db: Session = Depends(get_db),
):
    from backend.knowledge.service import KnowledgeBaseService
    svc = KnowledgeBaseService.get_instance()
    lib = svc.get_library(db, kb_id)
    if not lib:
        from backend.core.exceptions import AppError
        raise AppError(404, f"知识库 {kb_id} 不存在")
    return lib


@router.delete("/knowledge/v2/libraries/{kb_id}")
def delete_library(
    kb_id: str,
    user: CurrentUser = Depends(admin_user),
    db: Session = Depends(get_db),
):
    from backend.knowledge.service import KnowledgeBaseService
    svc = KnowledgeBaseService.get_instance()
    ok = svc.delete_library(db, kb_id)
    return {"deleted": ok}


# ── 文档 CRUD ────────────────────────────────────────────────────

@router.get("/knowledge/v2/libraries/{kb_id}/documents")
def list_documents(
    kb_id: str,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user: CurrentUser = Depends(admin_user),
    db: Session = Depends(get_db),
):
    from backend.knowledge.service import KnowledgeBaseService
    svc = KnowledgeBaseService.get_instance()
    return svc.list_documents(db, kb_id, status=status, limit=limit, offset=offset)


async def _bg_ingest(db_factory, kb_id, title, content, source_type, created_by, group_name):
    """后台任务：文档入库。"""
    try:
        from backend.knowledge.service import KnowledgeBaseService
        from backend.database import SessionLocal
        db = db_factory()
        try:
            svc = KnowledgeBaseService.get_instance()
            result = await svc.ingest_document(
                db, kb_id=kb_id, title=title, raw_text=content,
                source_type=source_type, created_by=created_by,
                group_name=group_name,
            )
            logger.info(f"[KnowledgeV2] bg ingest: {result}")
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"[KnowledgeV2] bg ingest failed: {e}")


@router.post("/knowledge/v2/libraries/{kb_id}/documents")
def create_document(
    kb_id: str,
    body: KBDocumentCreate,
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(admin_user),
    db: Session = Depends(get_db),
):
    from backend.database import SessionLocal
    background_tasks.add_task(
        _bg_ingest, SessionLocal, kb_id, body.title, body.content,
        body.source_type, user.username, body.group_name or "",
    )
    return {"status": "processing", "kb_id": kb_id}


@router.get("/knowledge/v2/documents/{document_id}")
def get_document(
    document_id: str,
    user: CurrentUser = Depends(admin_user),
    db: Session = Depends(get_db),
):
    from backend.knowledge.service import KnowledgeBaseService
    svc = KnowledgeBaseService.get_instance()
    doc = svc.get_document(db, document_id)
    if not doc:
        from backend.core.exceptions import AppError
        raise AppError(404, f"文档 {document_id} 不存在")
    return doc


@router.get("/knowledge/v2/documents/{document_id}/chunks")
def list_document_chunks(
    document_id: str,
    user: CurrentUser = Depends(admin_user),
    db: Session = Depends(get_db),
):
    from backend.knowledge.service import KnowledgeBaseService
    svc = KnowledgeBaseService.get_instance()
    return svc.list_chunks(db, document_id)


@router.get("/knowledge/v2/documents/{document_id}/versions")
def list_document_versions(
    document_id: str,
    user: CurrentUser = Depends(admin_user),
    db: Session = Depends(get_db),
):
    from backend.knowledge.service import KnowledgeBaseService
    svc = KnowledgeBaseService.get_instance()
    return svc.list_versions(db, document_id)


@router.post("/knowledge/v2/documents/{document_id}/rollback")
def rollback_document(
    document_id: str,
    body: dict,
    user: CurrentUser = Depends(admin_user),
    db: Session = Depends(get_db),
):
    target_version = body.get("target_version")
    if target_version is None:
        from backend.core.exceptions import AppError
        raise AppError(400, "缺少 target_version 参数")
    from backend.knowledge.service import KnowledgeBaseService
    svc = KnowledgeBaseService.get_instance()
    result = svc.rollback_document(db, document_id, int(target_version), user=user.username)
    if result.get("error"):
        from backend.core.exceptions import AppError
        raise AppError(404, result["error"])
    return result


@router.post("/knowledge/v2/documents/{document_id}/reprocess")
async def reprocess_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(admin_user),
):
    from backend.database import SessionLocal

    async def _bg_reprocess(db_factory, doc_id, username):
        try:
            from backend.knowledge.service import KnowledgeBaseService
            db = db_factory()
            try:
                svc = KnowledgeBaseService.get_instance()
                await svc.reprocess_document(db, doc_id, user=username)
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"[KnowledgeV2] bg reprocess failed: {e}")

    background_tasks.add_task(_bg_reprocess, SessionLocal, document_id, user.username)
    return {"status": "reprocessing", "document_id": document_id}


async def _bg_delete_doc(db_factory, document_id):
    try:
        from backend.knowledge.service import KnowledgeBaseService
        db = db_factory()
        try:
            svc = KnowledgeBaseService.get_instance()
            await svc.delete_document(db, document_id)
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"[KnowledgeV2] bg delete failed: {e}")


@router.delete("/knowledge/v2/documents/{document_id}")
def delete_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(admin_user),
):
    from backend.database import SessionLocal
    background_tasks.add_task(_bg_delete_doc, SessionLocal, document_id)
    return {"status": "deleting", "document_id": document_id}


# ── 统一检索 ─────────────────────────────────────────────────────

@router.post("/knowledge/v2/search")
def unified_search(
    body: SearchRequest,
    user: CurrentUser = Depends(admin_user),
):
    from backend.knowledge.service import KnowledgeBaseService
    svc = KnowledgeBaseService.get_instance()
    return svc.search(
        query=body.query, kb_ids=body.kb_ids,
        top_k=body.top_k, min_score=body.min_score,
        mode=body.search_mode,
    )


# ── 统计 ─────────────────────────────────────────────────────────

@router.get("/knowledge/v2/stats")
def kb_stats(
    kb_id: Optional[str] = None,
    user: CurrentUser = Depends(admin_user),
    db: Session = Depends(get_db),
):
    from backend.knowledge.service import KnowledgeBaseService
    svc = KnowledgeBaseService.get_instance()
    return svc.get_stats(db, kb_id=kb_id)


# ── §3.4 反馈：admin 列表 + 聚合 ──────────────────────────────────

@router.get("/knowledge/v2/feedback")
def list_kb_feedback(
    rating: Optional[int] = None,
    kb_id: Optional[str] = None,
    source: Optional[str] = None,
    days: int = 30,
    limit: int = 50,
    offset: int = 0,
    user: CurrentUser = Depends(admin_user),
    db: Session = Depends(get_db),
):
    """admin 反馈列表（分页 + 过滤）。

    - ``rating``: 1=👍 / -1=👎 / 0=中性，缺省=不过滤
    - ``kb_id``: 主命中库
    - ``source``: biz_kb / admin_kb / copilot_biz_rag / api_external
    - ``days``: 时间窗，默认 30 天，最大 365
    """
    from backend.knowledge.feedback_service import KBFeedbackService
    svc = KBFeedbackService.get_instance()
    return svc.list(
        db,
        rating=rating,
        kb_id=kb_id,
        source=source,
        days=days,
        limit=limit,
        offset=offset,
    )


@router.get("/knowledge/v2/feedback/stats")
def kb_feedback_stats(
    days: int = 7,
    user: CurrentUser = Depends(admin_user),
    db: Session = Depends(get_db),
):
    """admin 反馈聚合：窗口期内分布 + 分库 / 分原因 / 分来源。"""
    from backend.knowledge.feedback_service import KBFeedbackService
    svc = KBFeedbackService.get_instance()
    return svc.stats(db, days=days)
