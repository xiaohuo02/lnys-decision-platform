# -*- coding: utf-8 -*-
"""backend/routers/admin/policies.py

管理后台：Policy Center API
GET  /admin/policies         → Policy 列表
POST /admin/policies         → 新建 Policy
POST /admin/policies/{id}/activate → 激活 Policy（写 action_ledger）
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

router = APIRouter(tags=["admin-policies"])


class PolicyCreateBody(BaseModel):
    name:        str
    policy_type: str   # input_guard / output_guard / route_guard / tool_guard
    description: Optional[str] = None
    rules:       Dict[str, Any]


class PolicyActivateBody(BaseModel):
    note:         Optional[str] = None


@router.get("/policies")
async def admin_list_policies(
    policy_type: Optional[str] = None,
    status:      Optional[str] = None,
    limit:       int = 50,
    offset:      int = 0,
    user:        CurrentUser = Depends(admin_user),
    db:          AsyncSession = Depends(get_async_db),
):
    filters = "WHERE 1=1"
    params: Dict[str, Any] = {"limit": limit, "offset": offset}
    if policy_type:
        filters += " AND policy_type = :policy_type"
        params["policy_type"] = policy_type
    if status:
        filters += " AND status = :status"
        params["status"] = status

    result = await db.execute(sqlalchemy.text(
        f"SELECT policy_id, name, policy_type, version, status, created_by, updated_at "
        f"FROM policies {filters} ORDER BY updated_at DESC LIMIT :limit OFFSET :offset"
    ), params)
    rows = result.fetchall()

    try:
        count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}
        count_r = await db.execute(
            sqlalchemy.text(f"SELECT COUNT(*) FROM policies {filters}"),
            count_params,
        )
        total = count_r.scalar() or 0
    except Exception:
        total = len(rows)
    return {"items": [dict(r._mapping) for r in rows], "total": total}


@router.get("/policies/{policy_id}")
async def admin_get_policy(policy_id: str, user: CurrentUser = Depends(admin_user), db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(sqlalchemy.text(
        "SELECT * FROM policies WHERE policy_id = :id"
    ), {"id": policy_id})
    row = result.fetchone()
    if row is None:
        raise AppError(404, f"policy_id={policy_id} 不存在")
    return dict(row._mapping)


@router.post("/policies")
async def admin_create_policy(body: PolicyCreateBody, user: CurrentUser = Depends(release_operator), db: AsyncSession = Depends(get_async_db)):
    policy_id = str(uuid.uuid4())
    try:
        await db.execute(sqlalchemy.text("""
            INSERT INTO policies
                (policy_id, name, policy_type, description, rules_json, version, status, created_by)
            VALUES
                (:pid, :name, :ptype, :desc, :rules, 1, 'draft', :created_by)
        """), {
            "pid":        policy_id,
            "name":       body.name,
            "ptype":      body.policy_type,
            "desc":       body.description,
            "rules":      json.dumps(body.rules, ensure_ascii=False),
            "created_by": user.username,
        })
        await db.commit()
    except sqlalchemy.exc.IntegrityError:
        await db.rollback()
        raise AppError(409, f"策略名称 '{body.name}' 已存在，请使用其他名称")
    await async_write_audit_log(db, user.username, "create_policy", "policy", policy_id,
                                after={"name": body.name, "type": body.policy_type})
    return {"policy_id": policy_id, "status": "draft"}


@router.post("/policies/{policy_id}/activate")
async def admin_activate_policy(
    policy_id: str,
    body:      PolicyActivateBody,
    user:      CurrentUser = Depends(release_operator),
    db:        AsyncSession = Depends(get_async_db),
):
    from backend.governance.audit_center.action_ledger import (
        create_ledger_entry, complete_entry, DuplicateActionError,
    )
    result = await db.execute(sqlalchemy.text(
        "SELECT version FROM policies WHERE policy_id = :id"
    ), {"id": policy_id})
    row = result.fetchone()
    if row is None:
        raise AppError(404, f"policy_id={policy_id} 不存在")

    sync_db = SessionLocal()
    try:
        try:
            ikey = await run_in_threadpool(
                create_ledger_entry, sync_db, "activate_policy", "policy", policy_id,
                requested_by=user.username,
                idempotency_suffix=str(row[0]),
            )
        except DuplicateActionError as e:
            raise AppError(409, str(e))

        await db.execute(sqlalchemy.text(
            "UPDATE policies SET status='active', updated_at=NOW() WHERE policy_id=:id"
        ), {"id": policy_id})
        await db.commit()
        await run_in_threadpool(
            complete_entry, sync_db, ikey, approved_by=user.username,
            result_summary=f"Policy {policy_id} 已激活",
        )
    finally:
        sync_db.close()
    await async_write_audit_log(db, user.username, "activate_policy", "policy", policy_id)
    return {"policy_id": policy_id, "status": "active"}
