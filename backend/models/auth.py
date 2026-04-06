# -*- coding: utf-8 -*-
"""backend/models/auth.py — RBAC 认证相关 ORM Model

对应 init.sql 中 users / roles / permissions / user_roles / role_permissions 五张表。
"""
from sqlalchemy import (
    Column, String, Text, Boolean, BigInteger,
    ForeignKey, UniqueConstraint, Index, func,
)
from sqlalchemy.dialects.mysql import DATETIME as MySQLDateTime
from sqlalchemy.orm import relationship

from backend.database import Base


class User(Base):
    __tablename__ = "users"

    user_id = Column(String(36), primary_key=True, comment="UUID")
    username = Column(String(100), nullable=False, unique=True)
    display_name = Column(String(200), default=None)
    email = Column(String(200), default=None)
    hashed_pw = Column(String(256), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(MySQLDateTime(fsp=3), nullable=False, server_default=func.now())
    updated_at = Column(
        MySQLDateTime(fsp=3), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    user_roles = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User {self.username}>"


class Role(Base):
    __tablename__ = "roles"

    role_id = Column(String(36), primary_key=True, comment="UUID")
    role_name = Column(String(100), nullable=False, unique=True)
    description = Column(Text, default=None)
    created_at = Column(MySQLDateTime(fsp=3), nullable=False, server_default=func.now())

    user_roles = relationship("UserRole", back_populates="role", cascade="all, delete-orphan")
    role_permissions = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Role {self.role_name}>"


class Permission(Base):
    __tablename__ = "permissions"

    perm_id = Column(String(36), primary_key=True, comment="UUID")
    perm_code = Column(String(200), nullable=False, unique=True, comment="如 admin:traces:read")
    description = Column(Text, default=None)

    role_permissions = relationship("RolePermission", back_populates="permission", cascade="all, delete-orphan")


class UserRole(Base):
    __tablename__ = "user_roles"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    role_id = Column(String(36), ForeignKey("roles.role_id", ondelete="CASCADE"), nullable=False)
    granted_by = Column(String(100), nullable=False)
    granted_at = Column(MySQLDateTime(fsp=3), nullable=False, server_default=func.now())

    user = relationship("User", back_populates="user_roles")
    role = relationship("Role", back_populates="user_roles")

    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uk_user_role"),
        Index("idx_user_roles_user", "user_id"),
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    role_id = Column(String(36), ForeignKey("roles.role_id", ondelete="CASCADE"), nullable=False)
    perm_id = Column(String(36), ForeignKey("permissions.perm_id", ondelete="CASCADE"), nullable=False)

    role = relationship("Role", back_populates="role_permissions")
    permission = relationship("Permission", back_populates="role_permissions")

    __table_args__ = (
        UniqueConstraint("role_id", "perm_id", name="uk_role_perm"),
    )
