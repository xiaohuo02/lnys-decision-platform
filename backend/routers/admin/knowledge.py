# -*- coding: utf-8 -*-
"""backend/routers/admin/knowledge.py

管理后台：Knowledge Center（FAQ 知识库）API
GET  /admin/knowledge/faqs           → FAQ 列表
POST /admin/knowledge/faqs           → 新建 FAQ
POST /admin/knowledge/faqs/{id}/disable → 停用 FAQ
"""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy
from loguru import logger

from backend.database import get_async_db
from backend.core.exceptions import AppError
from backend.governance.trace_center.audit import async_write_audit_log
from backend.middleware.auth import admin_user, CurrentUser

router = APIRouter(tags=["admin-knowledge"])


# ── ChromaDB 同步辅助函数 ─────────────────────────────────────

async def _kb_ingest(doc_id: str, title: str, content: str, group_name: str):
    """后台任务：将新建/更新的 FAQ embed 到 ChromaDB"""
    try:
        from backend.services.enterprise_kb_service import EnterpriseKBService
        kb = EnterpriseKBService.get_instance()
        n = await kb.ingest(doc_id=doc_id, title=title, content=content, group_name=group_name)
        logger.info(f"[KnowledgeAPI] ingest doc_id={doc_id} chunks={n}")
    except Exception as e:
        logger.warning(f"[KnowledgeAPI] ingest failed doc_id={doc_id}: {e}")


async def _kb_remove(doc_id: str):
    """后台任务：从 ChromaDB 删除停用的 FAQ"""
    try:
        from backend.services.enterprise_kb_service import EnterpriseKBService
        kb = EnterpriseKBService.get_instance()
        n = await kb.remove(doc_id=doc_id)
        logger.info(f"[KnowledgeAPI] removed doc_id={doc_id} chunks={n}")
    except Exception as e:
        logger.warning(f"[KnowledgeAPI] remove failed doc_id={doc_id}: {e}")


class FAQCreateBody(BaseModel):
    group_name:  str
    title:       str
    content:     str
    source:      Optional[str] = None


@router.get("/knowledge/faqs")
async def admin_list_faqs(
    group_name: Optional[str] = None,
    is_active:  Optional[int] = None,
    limit:      int = 100,
    offset:     int = 0,
    user:       CurrentUser = Depends(admin_user),
    db:         AsyncSession = Depends(get_async_db),
):
    filters = "WHERE 1=1"
    params  = {"limit": limit, "offset": offset}
    if group_name:
        filters += " AND group_name = :gn"
        params["gn"] = group_name
    if is_active is not None:
        filters += " AND is_active = :ia"
        params["ia"] = is_active

    count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}
    count_r = await db.execute(
        sqlalchemy.text(f"SELECT COUNT(*) FROM faq_documents {filters}"), count_params
    )
    total = count_r.scalar() or 0

    result = await db.execute(sqlalchemy.text(
        f"SELECT doc_id, group_name, title, source, is_active, created_by, updated_at "
        f"FROM faq_documents {filters} "
        f"ORDER BY updated_at DESC LIMIT :limit OFFSET :offset"
    ), params)
    rows = result.fetchall()
    return {"items": [dict(r._mapping) for r in rows], "total": total}


@router.get("/knowledge/faqs/{doc_id}")
async def admin_get_faq(doc_id: str, user: CurrentUser = Depends(admin_user), db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(sqlalchemy.text(
        "SELECT * FROM faq_documents WHERE doc_id = :id"
    ), {"id": doc_id})
    row = result.fetchone()
    if row is None:
        raise AppError(404, f"doc_id={doc_id} 不存在")
    return dict(row._mapping)


@router.post("/knowledge/faqs")
async def admin_create_faq(body: FAQCreateBody, user: CurrentUser = Depends(admin_user), db: AsyncSession = Depends(get_async_db)):
    doc_id = str(uuid.uuid4())
    await db.execute(sqlalchemy.text("""
        INSERT INTO faq_documents (doc_id, group_name, title, content, source, created_by)
        VALUES (:doc_id, :gn, :title, :content, :source, :created_by)
    """), {
        "doc_id":     doc_id,
        "gn":         body.group_name,
        "title":      body.title,
        "content":    body.content,
        "source":     body.source,
        "created_by": user.username,
    })
    await db.commit()
    await async_write_audit_log(db, user.username, "create_faq", "faq_document", doc_id,
                                after={"title": body.title, "group": body.group_name})
    return {"doc_id": doc_id, "status": "active"}


@router.post("/knowledge/faqs/{doc_id}/disable")
async def admin_disable_faq(doc_id: str, user: CurrentUser = Depends(admin_user), db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(sqlalchemy.text(
        "SELECT doc_id FROM faq_documents WHERE doc_id = :id"
    ), {"id": doc_id})
    if result.fetchone() is None:
        raise AppError(404, f"doc_id={doc_id} 不存在")
    await db.execute(sqlalchemy.text(
        "UPDATE faq_documents SET is_active=0, updated_at=NOW() WHERE doc_id=:id"
    ), {"id": doc_id})
    await db.commit()
    await async_write_audit_log(db, user.username, "disable_faq", "faq_document", doc_id)
    return {"doc_id": doc_id, "status": "disabled"}


# ── 知识库管理接口 ───────────────────────────────────────────

@router.post("/knowledge/sync")
async def admin_sync_knowledge(
    user: CurrentUser = Depends(admin_user),
    db: AsyncSession = Depends(get_async_db),
):
    """手动触发全量同步：MySQL faq_documents → ChromaDB"""
    try:
        from backend.services.enterprise_kb_service import EnterpriseKBService
        kb = EnterpriseKBService.get_instance()
        stats = await kb.sync_all(db)
        await async_write_audit_log(db, user.username, "sync_knowledge", "enterprise_kb", "",
                                    after=stats)
        return {"status": "ok", **stats}
    except Exception as e:
        logger.error(f"[KnowledgeAPI] sync failed: {e}")
        return {"status": "error", "error": str(e)}


@router.get("/knowledge/kb-stats")
async def admin_kb_stats(user: CurrentUser = Depends(admin_user)):
    """知识库统计信息"""
    try:
        from backend.services.enterprise_kb_service import EnterpriseKBService
        kb = EnterpriseKBService.get_instance()
        return await kb.get_stats()
    except Exception as e:
        return {"error": str(e), "total_chunks": 0}
