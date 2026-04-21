# -*- coding: utf-8 -*-
"""backend/routers/admin/prompts.py

管理后台：Prompt Center API
GET  /admin/prompts              → Prompt 列表
GET  /admin/prompts/{id}         → Prompt 详情
POST /admin/prompts              → 新建 Prompt
POST /admin/prompts/{id}/release → 发布 Prompt（写 action_ledger）
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

router = APIRouter(tags=["admin-prompts"])


class PromptCreateBody(BaseModel):
    name:        str
    agent_name:  str
    description: Optional[str] = None
    content:     str
    variables:   Optional[List[str]] = None
    tags:        Optional[List[str]] = None


class PromptReleaseBody(BaseModel):
    note:        Optional[str] = None


@router.get("/prompts")
async def admin_list_prompts(
    agent_name: Optional[str] = None,
    status:     Optional[str] = None,
    limit:      int = 50,
    offset:     int = 0,
    user:       CurrentUser = Depends(admin_user),
    db:         AsyncSession = Depends(get_async_db),
):
    filters = "WHERE 1=1"
    params: Dict[str, Any] = {"limit": limit, "offset": offset}
    if agent_name:
        filters += " AND agent_name = :agent_name"
        params["agent_name"] = agent_name
    if status:
        filters += " AND status = :status"
        params["status"] = status

    result = await db.execute(sqlalchemy.text(
        f"SELECT prompt_id, name, agent_name, version, status, created_by, updated_at "
        f"FROM prompts {filters} ORDER BY updated_at DESC LIMIT :limit OFFSET :offset"
    ), params)
    rows = result.fetchall()

    try:
        count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}
        count_r = await db.execute(
            sqlalchemy.text(f"SELECT COUNT(*) FROM prompts {filters}"),
            count_params,
        )
        total = count_r.scalar() or 0
    except Exception:
        total = len(rows)
    return {"items": [dict(r._mapping) for r in rows], "total": total}


@router.get("/prompts/{prompt_id}")
async def admin_get_prompt(prompt_id: str, user: CurrentUser = Depends(admin_user), db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(sqlalchemy.text(
        "SELECT * FROM prompts WHERE prompt_id = :id"
    ), {"id": prompt_id})
    row = result.fetchone()
    if row is None:
        raise AppError(404, f"prompt_id={prompt_id} 不存在")
    prompt = dict(row._mapping)
    result2 = await db.execute(sqlalchemy.text(
        "SELECT * FROM prompt_releases WHERE prompt_id = :id ORDER BY released_at DESC"
    ), {"id": prompt_id})
    prompt["releases"] = [dict(r._mapping) for r in result2.fetchall()]

    # prev_content: 如果有上一个版本的发布快照，取其 content 用于 diff
    # 当前简化实现：无独立版本快照表，prev_content 置 None
    prompt["prev_content"] = None
    return prompt


@router.post("/prompts")
async def admin_create_prompt(body: PromptCreateBody, user: CurrentUser = Depends(release_operator), db: AsyncSession = Depends(get_async_db)):
    prompt_id = str(uuid.uuid4())
    try:
        await db.execute(sqlalchemy.text("""
            INSERT INTO prompts
                (prompt_id, name, agent_name, description, content, variables, tags,
                 version, status, created_by)
            VALUES
                (:prompt_id, :name, :agent_name, :desc, :content, :vars, :tags,
                 1, 'draft', :created_by)
        """), {
            "prompt_id":  prompt_id,
            "name":       body.name,
            "agent_name": body.agent_name,
            "desc":       body.description,
            "content":    body.content,
            "vars":       json.dumps(body.variables or []),
            "tags":       json.dumps(body.tags or []),
            "created_by": user.username,
        })
        await db.commit()
    except sqlalchemy.exc.IntegrityError:
        await db.rollback()
        raise AppError(409, f"Prompt 名称 '{body.name}' 已存在，请使用其他名称")
    await async_write_audit_log(db, user.username, "create_prompt", "prompt", prompt_id,
                                after={"name": body.name, "agent_name": body.agent_name})
    return {"prompt_id": prompt_id, "status": "draft"}


@router.post("/prompts/{prompt_id}/release")
async def admin_release_prompt(
    prompt_id: str,
    body:      PromptReleaseBody,
    user:      CurrentUser = Depends(release_operator),
    db:        AsyncSession = Depends(get_async_db),
):
    """
    发布 Prompt（高风险动作）：
    1. 创建 action_ledger 条目（幂等保护）
    2. 写 prompt_releases 记录
    3. 更新 prompt 状态为 active
    4. 写 audit_log
    """
    from backend.governance.audit_center.action_ledger import (
        create_ledger_entry, complete_entry, DuplicateActionError,
    )
    result = await db.execute(sqlalchemy.text(
        "SELECT version FROM prompts WHERE prompt_id = :id"
    ), {"id": prompt_id})
    row = result.fetchone()
    if row is None:
        raise AppError(404, f"prompt_id={prompt_id} 不存在")
    version = int(row[0])

    sync_db = SessionLocal()
    try:
        try:
            ikey = await run_in_threadpool(
                create_ledger_entry, sync_db, "release_prompt", "prompt", prompt_id,
                requested_by=user.username,
                payload={"version": version, "note": body.note},
                idempotency_suffix=str(version),
            )
        except DuplicateActionError as e:
            raise AppError(409, str(e))

        release_id = str(uuid.uuid4())
        await db.execute(sqlalchemy.text("""
            INSERT INTO prompt_releases (release_id, prompt_id, version, status, released_by, note)
            VALUES (:rid, :pid, :ver, 'approved', :by, :note)
        """), {"rid": release_id, "pid": prompt_id, "ver": version,
               "by": user.username, "note": body.note})
        await db.execute(sqlalchemy.text(
            "UPDATE prompts SET status='active', updated_at=NOW() WHERE prompt_id=:id"
        ), {"id": prompt_id})
        await db.commit()

        await run_in_threadpool(
            complete_entry, sync_db, ikey, approved_by=user.username,
            result_summary=f"Prompt {prompt_id} v{version} 已发布",
        )
    finally:
        sync_db.close()

    await async_write_audit_log(db, user.username, "release_prompt", "prompt", prompt_id,
                                after={"version": version, "release_id": release_id})
    return {"release_id": release_id, "status": "released", "version": version}
