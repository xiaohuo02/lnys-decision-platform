# -*- coding: utf-8 -*-
"""backend/middleware/auth.py

JWT 认证与 RBAC 权限依赖
- get_current_user: 验证 Bearer token，返回用户信息
- require_role:     角色门禁工厂函数
- 当前阶段为最小实现，后续可接入完整 RBAC 服务
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, Field

from backend.config import settings

_ALGORITHM = "HS256"
_bearer = HTTPBearer(auto_error=False)


# ── Token schema ──────────────────────────────────────────────────

class TokenPayload(BaseModel):
    sub:    str                       # username
    roles:  List[str] = Field(default_factory=list)
    exp:    Optional[int] = None


class CurrentUser(BaseModel):
    username: str
    roles:    List[str] = Field(default_factory=list)


# ── Token 生成（供登录接口使用）─────────────────────────────────────

def create_access_token(username: str, roles: List[str]) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": username, "roles": roles, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=_ALGORITHM)


# ── FastAPI 依赖项 ────────────────────────────────────────────────

def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> CurrentUser:
    """
    从 Authorization: Bearer <token> 中解析用户信息。
    如果 settings.DEV_BACKDOOR_ENABLED 且无 token，返回开发用默认管理员。
    """
    if credentials is None:
        if settings.DEV_BACKDOOR_ENABLED:
            return CurrentUser(username="dev_admin", roles=["platform_admin"])
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[_ALGORITHM])
        username: str = payload.get("sub", "")
        roles:    list = payload.get("roles", [])
        if not username:
            raise JWTError("missing sub")
        return CurrentUser(username=username, roles=roles)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_role(*required_roles: str):
    """
    角色门禁工厂：
        @router.post("/admin/prompts/{id}/release")
        def release(user: CurrentUser = Depends(require_role("platform_admin", "ml_engineer"))):
    """
    def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not any(r in user.roles for r in required_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"需要角色之一: {list(required_roles)}",
            )
        return user
    return dependency


# ── 预定义常用门禁 ────────────────────────────────────────────────

def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Optional[CurrentUser]:
    """尝试解析用户，无 token 或解析失败时返回 None（不抛异常）"""
    if credentials is None:
        return None
    try:
        payload = jwt.decode(credentials.credentials, settings.SECRET_KEY, algorithms=[_ALGORITHM])
        username: str = payload.get("sub", "")
        roles:    list = payload.get("roles", [])
        return CurrentUser(username=username, roles=roles) if username else None
    except JWTError:
        return None


def admin_user(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """所有登录后台用户可访问（最低门禁）"""
    return user


def platform_admin(user: CurrentUser = Depends(require_role("platform_admin"))) -> CurrentUser:
    return user


def release_operator(
    user: CurrentUser = Depends(require_role("platform_admin", "ml_engineer"))
) -> CurrentUser:
    return user


def risk_reviewer(
    user: CurrentUser = Depends(require_role("platform_admin", "risk_reviewer"))
) -> CurrentUser:
    return user
