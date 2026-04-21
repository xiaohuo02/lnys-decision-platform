# -*- coding: utf-8 -*-
"""backend/routers/admin/team.py

团队用户管理 API
GET    /admin/team/users          — 用户列表（含角色）
GET    /admin/team/users/:id      — 用户详情
POST   /admin/team/users          — 创建用户
PUT    /admin/team/users/:id/role — 分配角色
POST   /admin/team/users/:id/disable — 禁用用户
GET    /admin/team/roles          — 角色列表
"""
import uuid

import sqlalchemy
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from backend.core.exceptions import AppError
from backend.database import get_async_db
from backend.middleware.auth import admin_user, platform_admin, CurrentUser
from backend.governance.trace_center.audit import async_write_audit_log

router = APIRouter(tags=["admin-team"])


# ── Request Bodies ────────────────────────────────────────────
class UserCreateBody(BaseModel):
    username: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    password: str
    role_name: Optional[str] = None


class RoleAssignBody(BaseModel):
    role_name: str


# ── GET /team/roles ───────────────────────────────────────────
@router.get("/team/roles")
async def admin_list_roles(user: CurrentUser = Depends(admin_user), db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(sqlalchemy.text(
        "SELECT role_id, role_name, description, created_at FROM roles ORDER BY created_at"
    ))
    return {"items": [dict(r._mapping) for r in result.fetchall()]}


# ── GET /team/users ───────────────────────────────────────────
@router.get("/team/users")
async def admin_list_users(
    is_active: Optional[int] = None,
    keyword: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    user: CurrentUser = Depends(admin_user),
    db: AsyncSession = Depends(get_async_db),
):
    filters = "WHERE 1=1"
    params = {"limit": limit, "offset": offset}
    if is_active is not None:
        filters += " AND u.is_active = :ia"
        params["ia"] = is_active
    if keyword:
        filters += " AND (u.username LIKE :kw OR u.display_name LIKE :kw OR u.email LIKE :kw)"
        params["kw"] = f"%{keyword}%"

    count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}
    count_r = await db.execute(
        sqlalchemy.text(f"SELECT COUNT(DISTINCT u.user_id) FROM users u {filters}"),
        count_params,
    )
    total = count_r.scalar() or 0

    result = await db.execute(sqlalchemy.text(f"""
        SELECT u.user_id, u.username, u.display_name, u.email, u.is_active,
               u.created_at, u.updated_at,
               GROUP_CONCAT(r.role_name) AS roles,
               GROUP_CONCAT(r.description) AS role_descriptions
        FROM users u
        LEFT JOIN user_roles ur ON u.user_id = ur.user_id
        LEFT JOIN roles r ON ur.role_id = r.role_id
        {filters}
        GROUP BY u.user_id
        ORDER BY u.created_at DESC
        LIMIT :limit OFFSET :offset
    """), params)
    rows = result.fetchall()

    items = []
    for r in rows:
        m = dict(r._mapping)
        m["roles"] = m["roles"].split(",") if m["roles"] else []
        m["role_descriptions"] = m["role_descriptions"].split(",") if m["role_descriptions"] else []
        items.append(m)

    return {"items": items, "total": total}


# ── GET /team/users/:id ──────────────────────────────────────
@router.get("/team/users/{user_id}")
async def admin_get_user(user_id: str, user: CurrentUser = Depends(admin_user), db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(sqlalchemy.text("""
        SELECT u.user_id, u.username, u.display_name, u.email, u.is_active,
               u.created_at, u.updated_at
        FROM users u WHERE u.user_id = :uid
    """), {"uid": user_id})
    row = result.fetchone()
    if not row:
        raise AppError(404, "用户不存在")

    user_data = dict(row._mapping)
    result2 = await db.execute(sqlalchemy.text("""
        SELECT r.role_name, r.description, ur.granted_by, ur.granted_at
        FROM user_roles ur JOIN roles r ON ur.role_id = r.role_id
        WHERE ur.user_id = :uid
    """), {"uid": user_id})
    user_data["roles"] = [dict(rr._mapping) for rr in result2.fetchall()]
    return user_data


# ── POST /team/users ─────────────────────────────────────────
@router.post("/team/users")
async def admin_create_user(body: UserCreateBody, user: CurrentUser = Depends(platform_admin), db: AsyncSession = Depends(get_async_db)):
    from passlib.context import CryptContext
    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

    role_id = None
    if body.role_name:
        result = await db.execute(sqlalchemy.text(
            "SELECT role_id FROM roles WHERE role_name = :rn"
        ), {"rn": body.role_name})
        role_row = result.fetchone()
        if not role_row:
            raise AppError(400, f"角色 '{body.role_name}' 不存在")
        role_id = role_row[0]

    user_id = str(uuid.uuid4())
    hashed = pwd_ctx.hash(body.password)

    try:
        await db.execute(sqlalchemy.text("""
            INSERT INTO users (user_id, username, display_name, email, hashed_pw)
            VALUES (:uid, :uname, :dname, :email, :pw)
        """), {
            "uid": user_id, "uname": body.username,
            "dname": body.display_name, "email": body.email, "pw": hashed,
        })
        if role_id:
            await db.execute(sqlalchemy.text("""
                INSERT IGNORE INTO user_roles (user_id, role_id, granted_by)
                VALUES (:uid, :rid, :gb)
            """), {"uid": user_id, "rid": role_id, "gb": user.username})
        await db.commit()
    except sqlalchemy.exc.IntegrityError:
        await db.rollback()
        raise AppError(409, f"用户名 '{body.username}' 已存在")

    await async_write_audit_log(
        db, operator=user.username, action="create_user",
        target_type="user", target_id=user_id,
        after={"username": body.username, "role": body.role_name},
    )
    return {"user_id": user_id, "username": body.username}


# ── PUT /team/users/:id/role ─────────────────────────────────
@router.put("/team/users/{user_id}/role")
async def admin_assign_role(user_id: str, body: RoleAssignBody, user: CurrentUser = Depends(platform_admin), db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(sqlalchemy.text(
        "SELECT role_id FROM roles WHERE role_name = :rn"
    ), {"rn": body.role_name})
    role_row = result.fetchone()
    if not role_row:
        raise AppError(404, f"角色 '{body.role_name}' 不存在")

    await db.execute(sqlalchemy.text("DELETE FROM user_roles WHERE user_id = :uid"), {"uid": user_id})
    await db.execute(sqlalchemy.text("""
        INSERT INTO user_roles (user_id, role_id, granted_by)
        VALUES (:uid, :rid, :gb)
    """), {"uid": user_id, "rid": role_row[0], "gb": user.username})
    await db.commit()
    await async_write_audit_log(
        db, operator=user.username, action="assign_role",
        target_type="user", target_id=user_id,
        after={"role_name": body.role_name},
    )
    return {"status": "ok", "role_name": body.role_name}


# ── POST /team/users/:id/disable ─────────────────────────────
@router.post("/team/users/{user_id}/disable")
async def admin_disable_user(user_id: str, user: CurrentUser = Depends(platform_admin), db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(sqlalchemy.text(
        "UPDATE users SET is_active = 0 WHERE user_id = :uid"
    ), {"uid": user_id})
    await db.commit()
    if result.rowcount == 0:
        raise AppError(404, "用户不存在")
    await async_write_audit_log(
        db, operator=user.username, action="disable_user",
        target_type="user", target_id=user_id,
    )
    return {"status": "disabled"}


# ── POST /team/users/:id/enable ──────────────────────────────
@router.post("/team/users/{user_id}/enable")
async def admin_enable_user(user_id: str, user: CurrentUser = Depends(platform_admin), db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(sqlalchemy.text(
        "UPDATE users SET is_active = 1 WHERE user_id = :uid"
    ), {"uid": user_id})
    await db.commit()
    if result.rowcount == 0:
        raise AppError(404, "用户不存在")
    await async_write_audit_log(
        db, operator=user.username, action="enable_user",
        target_type="user", target_id=user_id,
    )
    return {"status": "active"}
