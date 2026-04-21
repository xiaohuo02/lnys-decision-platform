# -*- coding: utf-8 -*-
"""backend/routers/admin/releases.py

管理后台：Release Center API
GET  /admin/releases               → 发布列表
GET  /admin/releases/{id}          → 发布详情 + items
POST /admin/releases               → 创建发布批次
POST /admin/releases/{id}/rollback → 回滚（写 action_ledger）
"""
import json
import uuid
from typing import Any, Dict, List, Optional

import sqlalchemy
from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_db, SessionLocal
from backend.core.exceptions import AppError
from backend.governance.trace_center.audit import async_write_audit_log
from backend.middleware.auth import admin_user, release_operator, CurrentUser

router = APIRouter(tags=["admin-releases"])


class ReleaseItemBody(BaseModel):
    item_type:    str   # prompt / policy / workflow / config
    item_id:      str
    item_name:    str
    from_version: Optional[str] = None
    to_version:   str


class ReleaseCreateBody(BaseModel):
    name:         str
    release_type: str
    version:      str
    items:        List[ReleaseItemBody]
    note:         Optional[str] = None


class RollbackBody(BaseModel):
    target_version: str
    reason:         Optional[str] = None


@router.get("/releases")
async def admin_list_releases(
    status:       Optional[str] = None,
    release_type: Optional[str] = None,
    limit:        int = 50,
    offset:       int = 0,
    user:         CurrentUser = Depends(admin_user),
    db:           AsyncSession = Depends(get_async_db),
):
    filters = "WHERE 1=1"
    params: Dict[str, Any] = {"l": limit, "o": offset}
    if status:
        filters += " AND status = :status"
        params["status"] = status
    if release_type:
        filters += " AND release_type = :rt"
        params["rt"] = release_type

    result = await db.execute(sqlalchemy.text(
        f"SELECT release_id, name, release_type, version, status, "
        f"released_by, approved_by, released_at, created_at "
        f"FROM releases {filters} ORDER BY created_at DESC LIMIT :l OFFSET :o"
    ), params)
    return {"items": [dict(r._mapping) for r in result.fetchall()]}


@router.get("/releases/{release_id}")
async def admin_get_release(release_id: str, user: CurrentUser = Depends(admin_user), db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(sqlalchemy.text(
        "SELECT * FROM releases WHERE release_id = :id"
    ), {"id": release_id})
    row = result.fetchone()
    if row is None:
        raise AppError(404, f"release_id={release_id} 不存在")
    release = dict(row._mapping)

    r_items = await db.execute(sqlalchemy.text(
        "SELECT * FROM release_items WHERE release_id = :id"
    ), {"id": release_id})
    release["items"] = [dict(i._mapping) for i in r_items.fetchall()]

    r_rb = await db.execute(sqlalchemy.text(
        "SELECT * FROM release_rollbacks WHERE release_id = :id ORDER BY executed_at DESC"
    ), {"id": release_id})
    release["rollbacks"] = [dict(r._mapping) for r in r_rb.fetchall()]
    return release


@router.post("/releases")
async def admin_create_release(body: ReleaseCreateBody, user: CurrentUser = Depends(release_operator), db: AsyncSession = Depends(get_async_db)):
    release_id = str(uuid.uuid4())
    await db.execute(sqlalchemy.text("""
        INSERT INTO releases
            (release_id, name, release_type, version, status, released_by, note, released_at)
        VALUES
            (:rid, :name, :rtype, :ver, 'released', :by, :note, NOW())
    """), {"rid": release_id, "name": body.name, "rtype": body.release_type,
           "ver": body.version, "by": user.username, "note": body.note})

    for item in body.items:
        await db.execute(sqlalchemy.text("""
            INSERT INTO release_items
                (release_id, item_type, item_id, item_name, from_version, to_version)
            VALUES (:rid, :itype, :iid, :iname, :from_ver, :to_ver)
        """), {"rid": release_id, "itype": item.item_type, "iid": item.item_id,
               "iname": item.item_name, "from_ver": item.from_version,
               "to_ver": item.to_version})
    await db.commit()
    await async_write_audit_log(db, user.username, "create_release", "release", release_id,
                                after={"name": body.name, "version": body.version})
    return {"release_id": release_id, "status": "released"}


@router.post("/releases/{release_id}/rollback")
async def admin_rollback_release(
    release_id: str,
    body:       RollbackBody,
    user:       CurrentUser = Depends(release_operator),
    db:         AsyncSession = Depends(get_async_db),
):
    """
    回滚一次发布（高风险动作）：
    1. action_ledger 幂等保护
    2. 记录 rollback 条目
    3. 更新 release 状态
    4. 写 audit_log
    """
    from backend.governance.audit_center.action_ledger import (
        create_ledger_entry, complete_entry, DuplicateActionError,
    )
    result = await db.execute(sqlalchemy.text(
        "SELECT release_id, status FROM releases WHERE release_id = :id"
    ), {"id": release_id})
    if result.fetchone() is None:
        raise AppError(404, f"release_id={release_id} 不存在")

    sync_db = SessionLocal()
    try:
        try:
            ikey = await run_in_threadpool(
                create_ledger_entry, sync_db, "rollback_release", "release", release_id,
                requested_by=user.username,
                payload={"target_version": body.target_version, "reason": body.reason},
            )
        except DuplicateActionError as e:
            raise AppError(409, str(e))

        rb_id = str(uuid.uuid4())
        await db.execute(sqlalchemy.text("""
            INSERT INTO release_rollbacks
                (release_id, rollback_by, target_version, reason)
            VALUES (:rid, :by, :tver, :reason)
        """), {"rid": release_id, "by": user.username,
               "tver": body.target_version, "reason": body.reason})
        await db.execute(sqlalchemy.text(
            "UPDATE releases SET status='rolled_back', updated_at=NOW() WHERE release_id=:id"
        ), {"id": release_id})
        await db.commit()
        await run_in_threadpool(
            complete_entry, sync_db, ikey, approved_by=user.username,
            result_summary=f"Release {release_id} 回滚到 {body.target_version}",
        )
    finally:
        sync_db.close()
    await async_write_audit_log(db, user.username, "rollback_release", "release", release_id,
                                after={"target_version": body.target_version})
    return {"release_id": release_id, "status": "rolled_back", "target_version": body.target_version}
