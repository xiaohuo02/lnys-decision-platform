# -*- coding: utf-8 -*-
"""backend/models/copilot.py — Copilot 域 ORM Model

对应 copilot_tables.sql 中 copilot_threads / copilot_messages /
copilot_action_log / copilot_memory / copilot_rules /
copilot_skill_overrides / feishu_group_mapping 七张表。
"""
from sqlalchemy import (
    Column, String, Text, BigInteger, Boolean, Float, Integer,
    JSON, Enum as SAEnum, Index, ForeignKey, func,
)
from sqlalchemy.dialects.mysql import DATETIME as MySQLDateTime, TINYINT
from sqlalchemy.orm import relationship

from backend.database import Base


# ── 对话线程 ──────────────────────────────────────────────────────

class CopilotThread(Base):
    __tablename__ = "copilot_threads"

    id          = Column(String(36), primary_key=True, comment="UUID")
    user_id     = Column(String(64), nullable=False)
    mode        = Column(SAEnum("ops", "biz", name="copilot_mode_enum"), nullable=False)
    title       = Column(String(256), default=None, comment="自动生成标题")
    status      = Column(
        SAEnum("active", "archived", "deleted", name="thread_status_enum"),
        nullable=False, default="active",
    )
    summary     = Column(Text, default=None, comment="LLM 自动摘要")
    page_origin = Column(String(256), default=None, comment="发起对话时所在页面")
    tags        = Column(JSON, default=None)
    pinned      = Column(Boolean, default=False)
    created_at  = Column(MySQLDateTime(fsp=0), nullable=False, server_default=func.now())
    updated_at  = Column(
        MySQLDateTime(fsp=0), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    messages = relationship(
        "CopilotMessage", back_populates="thread",
        cascade="all, delete-orphan", passive_deletes=True,
    )

    __table_args__ = (
        Index("idx_user_mode", "user_id", "mode", "status"),
        Index("idx_updated", "updated_at"),
    )


# ── 对话消息 ──────────────────────────────────────────────────────

class CopilotMessage(Base):
    __tablename__ = "copilot_messages"

    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    thread_id     = Column(String(36), ForeignKey("copilot_threads.id"), nullable=False)
    role          = Column(
        SAEnum("user", "assistant", "system", "tool", name="msg_role_enum"),
        nullable=False,
    )
    content       = Column(Text, nullable=False)
    intent        = Column(String(64), default=None)
    skills_used   = Column(JSON, default=None, comment="使用的 Skill 列表")
    confidence    = Column(Float, default=None)
    thinking      = Column(Text, default=None, comment="思维链内容")
    artifacts     = Column(JSON, default=None)
    tool_calls    = Column(JSON, default=None)
    suggestions   = Column(JSON, default=None)
    actions_taken = Column(JSON, default=None)
    feedback      = Column(TINYINT, default=None, comment="1=👍 -1=👎")
    feedback_text = Column(String(512), default=None)
    elapsed_ms    = Column(Integer, default=None)
    token_usage   = Column(JSON, default=None)
    source        = Column(
        SAEnum("web", "feishu", "api", "scheduler", name="msg_source_enum"),
        nullable=False, default="web",
    )
    created_at    = Column(MySQLDateTime(fsp=0), nullable=False, server_default=func.now())

    thread = relationship("CopilotThread", back_populates="messages")

    __table_args__ = (
        Index("idx_thread", "thread_id", "created_at"),
        Index("idx_feedback", "feedback"),
        Index("idx_source", "source"),
    )


# ── 操作审计日志（不可变）──────────────────────────────────────────

class CopilotActionLog(Base):
    __tablename__ = "copilot_action_log"

    id          = Column(BigInteger, primary_key=True, autoincrement=True)
    thread_id   = Column(String(36), nullable=False)
    message_id  = Column(BigInteger, nullable=False)
    user_id     = Column(String(64), nullable=False)
    action_type = Column(String(64), nullable=False, comment="feishu_notify/export_report/...")
    target      = Column(String(256), nullable=False)
    payload     = Column(JSON, default=None)
    status      = Column(
        SAEnum("pending", "approved", "executed", "failed", "rejected", "pending_approval",
               name="action_status_enum"),
        nullable=False, default="pending",
    )
    result      = Column(JSON, default=None)
    created_at  = Column(MySQLDateTime(fsp=0), nullable=False, server_default=func.now())
    executed_at = Column(MySQLDateTime(fsp=0), default=None)

    __table_args__ = (
        Index("idx_action_thread", "thread_id"),
        Index("idx_action_user", "user_id", "created_at"),
    )


# ── 动态记忆（Agent 自主维护）─────────────────────────────────────

class CopilotMemory(Base):
    __tablename__ = "copilot_memory"

    id               = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id          = Column(String(64), nullable=False)
    domain           = Column(String(64), nullable=False, comment="user_preferences/business_context/...")
    title            = Column(String(256), nullable=False)
    content          = Column(Text, nullable=False, comment="Markdown 格式")
    importance       = Column(Float, default=0.5, comment="0~1 重要度")
    access_count     = Column(
        Integer, nullable=False, server_default="0",
        comment="访问次数（FreshnessEngine frequency 输入）",
    )
    last_accessed_at = Column(MySQLDateTime(fsp=0), default=None, comment="最后一次访问时间")
    created_at       = Column(MySQLDateTime(fsp=0), nullable=False, server_default=func.now())
    updated_at       = Column(
        MySQLDateTime(fsp=0), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )
    is_active        = Column(Boolean, default=True, comment="软删除")

    __table_args__ = (
        Index("idx_user_domain", "user_id", "domain"),
        Index("idx_importance", "importance"),
        Index("idx_memory_access", "access_count"),
        Index("idx_memory_last_accessed", "last_accessed_at"),
    )


# ── 静态规则（管理员维护）─────────────────────────────────────────

class CopilotRule(Base):
    __tablename__ = "copilot_rules"

    id         = Column(BigInteger, primary_key=True, autoincrement=True)
    scope      = Column(
        SAEnum("global", "ops", "biz", name="rule_scope_enum"), nullable=False,
    )
    title      = Column(String(256), nullable=False)
    content    = Column(Text, nullable=False)
    priority   = Column(Integer, default=0, comment="高优先级先加载")
    created_by = Column(String(64), nullable=False)
    is_active  = Column(Boolean, default=True)
    created_at = Column(MySQLDateTime(fsp=0), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_scope", "scope", "priority"),
    )


# ── Skill 权限覆盖 ───────────────────────────────────────────────

class CopilotSkillOverride(Base):
    __tablename__ = "copilot_skill_overrides"

    id         = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id    = Column(String(64), nullable=False)
    skill_name = Column(String(64), nullable=False)
    enabled    = Column(Boolean, nullable=False, default=True)
    granted_by = Column(String(64), nullable=False)
    reason     = Column(String(256), default=None)
    is_active  = Column(Boolean, default=True)
    created_at = Column(MySQLDateTime(fsp=0), nullable=False, server_default=func.now())
    updated_at = Column(
        MySQLDateTime(fsp=0), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    __table_args__ = (
        Index("idx_override_user", "user_id"),
    )


# ── 飞书群映射 ───────────────────────────────────────────────────

class FeishuGroupMapping(Base):
    __tablename__ = "feishu_group_mapping"

    id             = Column(BigInteger, primary_key=True, autoincrement=True)
    group_name     = Column(String(64), nullable=False, unique=True)
    chat_id        = Column(String(128), nullable=False, comment="飞书群 chat_id")
    mode           = Column(SAEnum("ops", "biz", name="feishu_mode_enum"), nullable=False)
    patrol_enabled = Column(Boolean, default=True)
    description    = Column(String(256), default=None)
    created_at     = Column(MySQLDateTime(fsp=0), nullable=False, server_default=func.now())
