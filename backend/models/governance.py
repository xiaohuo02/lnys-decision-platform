# -*- coding: utf-8 -*-
"""backend/models/governance.py — 治理域 ORM Model

对应 init.sql 中 runs / run_steps / artifacts / agents / agent_tools /
prompts / prompt_releases / policies / releases / release_items /
release_rollbacks / review_cases / review_actions / audit_logs /
action_ledgers / faq_documents / memory_records / memory_feedback。
"""
from sqlalchemy import (
    Column, String, Text, Integer, BigInteger, Boolean, SmallInteger,
    Numeric, JSON, Enum as SAEnum, Index, ForeignKey,
    UniqueConstraint, func,
)
from sqlalchemy.dialects.mysql import DATETIME as MySQLDateTime
from sqlalchemy.orm import relationship

from backend.database import Base


# ── runs：工作流执行记录 ─────────────────────────────────────────

class Run(Base):
    __tablename__ = "runs"

    run_id = Column(String(36), primary_key=True, comment="UUID")
    thread_id = Column(String(128), nullable=False, comment="LangGraph thread_id")
    request_id = Column(String(128), nullable=False, comment="业务侧 request_id")
    entrypoint = Column(String(100), nullable=False, comment="调用入口路由")
    workflow_name = Column(String(100), nullable=False)
    workflow_version = Column(String(50), default="latest")
    status = Column(
        SAEnum("pending", "running", "paused", "completed", "failed", "cancelled",
               name="run_status_enum"),
        nullable=False, default="pending",
    )
    input_summary = Column(Text, default=None)
    output_summary = Column(Text, default=None)
    total_tokens = Column(Integer, default=0)
    total_cost = Column(Numeric(10, 6), default=0)
    error_message = Column(Text, default=None)
    started_at = Column(MySQLDateTime(fsp=3), nullable=False, server_default=func.now())
    ended_at = Column(MySQLDateTime(fsp=3), default=None)
    latency_ms = Column(Integer, default=None)

    steps = relationship("RunStep", back_populates="run", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_runs_request_id", "request_id"),
        Index("idx_runs_thread_id", "thread_id"),
        Index("idx_runs_workflow_name", "workflow_name"),
        Index("idx_runs_status", "status"),
        Index("idx_runs_started_at", "started_at"),
    )


class RunStep(Base):
    __tablename__ = "run_steps"

    step_id = Column(String(36), primary_key=True, comment="UUID")
    run_id = Column(String(36), ForeignKey("runs.run_id", ondelete="CASCADE"), nullable=False)
    parent_step_id = Column(String(36), default=None)
    step_type = Column(
        SAEnum("agent_call", "tool_call", "service_call", "llm_call",
               "hitl", "handoff", "guardrail", name="step_type_enum"),
        nullable=False,
    )
    step_name = Column(String(100), nullable=False)
    agent_name = Column(String(100), default=None)
    tool_name = Column(String(100), default=None)
    model_name = Column(String(100), default=None)
    prompt_id = Column(String(36), default=None)
    prompt_version = Column(String(50), default=None)
    policy_version = Column(String(50), default=None)
    handoff_from = Column(String(100), default=None)
    handoff_to = Column(String(100), default=None)
    status = Column(
        SAEnum("pending", "running", "paused", "completed", "failed", "cancelled",
               name="step_status_enum"),
        nullable=False, default="pending",
    )
    input_summary = Column(Text, default=None)
    output_summary = Column(Text, default=None)
    guardrail_hits_json = Column(JSON, default=None)
    token_usage_json = Column(JSON, default=None)
    cost_amount = Column(Numeric(10, 6), default=0)
    retry_count = Column(SmallInteger, default=0)
    artifact_ids_json = Column(JSON, default=None)
    error_message = Column(Text, default=None)
    started_at = Column(MySQLDateTime(fsp=3), nullable=False, server_default=func.now())
    ended_at = Column(MySQLDateTime(fsp=3), default=None)

    run = relationship("Run", back_populates="steps")

    __table_args__ = (
        Index("idx_steps_run_id", "run_id"),
        Index("idx_steps_parent", "parent_step_id"),
        Index("idx_steps_agent", "agent_name"),
    )


# ── artifacts ────────────────────────────────────────────────────

class Artifact(Base):
    __tablename__ = "artifacts"

    artifact_id = Column(String(36), primary_key=True, comment="UUID")
    artifact_type = Column(String(50), nullable=False)
    artifact_uri = Column(String(500), nullable=False, comment="文件路径或对象存储 key")
    content_type = Column(String(100), default="application/json")
    summary = Column(Text, default=None)
    metadata_json = Column(JSON, default=None)
    run_id = Column(String(36), default=None)
    step_id = Column(String(36), default=None)
    created_at = Column(MySQLDateTime(fsp=3), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_artifacts_run_id", "run_id"),
        Index("idx_artifacts_type", "artifact_type"),
    )


# ── agents ───────────────────────────────────────────────────────

class Agent(Base):
    __tablename__ = "agents"

    agent_id = Column(String(36), primary_key=True, comment="UUID")
    agent_name = Column(String(100), nullable=False, unique=True)
    description = Column(Text, default=None)
    version = Column(String(50), default="latest")
    is_active = Column(Boolean, default=True)
    created_at = Column(MySQLDateTime(fsp=3), nullable=False, server_default=func.now())
    updated_at = Column(
        MySQLDateTime(fsp=3), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    tools = relationship("AgentTool", back_populates="agent", cascade="all, delete-orphan")


class AgentTool(Base):
    __tablename__ = "agent_tools"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    agent_id = Column(String(36), ForeignKey("agents.agent_id", ondelete="CASCADE"), nullable=False)
    tool_name = Column(String(100), nullable=False)
    description = Column(Text, default=None)
    is_active = Column(Boolean, default=True)

    agent = relationship("Agent", back_populates="tools")

    __table_args__ = (
        UniqueConstraint("agent_id", "tool_name", name="uk_agent_tool"),
    )


# ── prompts ──────────────────────────────────────────────────────

class Prompt(Base):
    __tablename__ = "prompts"

    prompt_id = Column(String(36), primary_key=True, comment="UUID")
    name = Column(String(100), nullable=False)
    agent_name = Column(String(100), nullable=False)
    description = Column(Text, default=None)
    content = Column(Text, nullable=False)
    variables = Column(JSON, default=None, comment="模板变量列表")
    tags = Column(JSON, default=None)
    version = Column(Integer, nullable=False, default=1)
    status = Column(
        SAEnum("draft", "reviewing", "active", "archived", name="prompt_status_enum"),
        nullable=False, default="draft",
    )
    created_by = Column(String(100), nullable=False)
    created_at = Column(MySQLDateTime(fsp=3), nullable=False, server_default=func.now())
    updated_at = Column(
        MySQLDateTime(fsp=3), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    releases = relationship("PromptRelease", back_populates="prompt", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_prompts_agent", "agent_name"),
        Index("idx_prompts_status", "status"),
    )


class PromptRelease(Base):
    __tablename__ = "prompt_releases"

    release_id = Column(String(36), primary_key=True, comment="UUID")
    prompt_id = Column(String(36), ForeignKey("prompts.prompt_id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer, nullable=False)
    status = Column(
        SAEnum("pending", "approved", "rejected", "rolled_back",
               name="prompt_release_status_enum"),
        nullable=False, default="pending",
    )
    released_by = Column(String(100), nullable=False)
    approved_by = Column(String(100), default=None)
    note = Column(Text, default=None)
    released_at = Column(MySQLDateTime(fsp=3), nullable=False, server_default=func.now())

    prompt = relationship("Prompt", back_populates="releases")

    __table_args__ = (
        Index("idx_prompt_releases_prompt", "prompt_id"),
    )


# ── policies ─────────────────────────────────────────────────────

class Policy(Base):
    __tablename__ = "policies"

    policy_id = Column(String(36), primary_key=True, comment="UUID")
    name = Column(String(100), nullable=False, unique=True)
    policy_type = Column(String(50), nullable=False, comment="input_guard/output_guard/route_guard/tool_guard")
    description = Column(Text, default=None)
    rules_json = Column(JSON, nullable=False, comment="策略规则定义")
    version = Column(Integer, nullable=False, default=1)
    status = Column(
        SAEnum("draft", "active", "archived", name="policy_status_enum"),
        nullable=False, default="draft",
    )
    created_by = Column(String(100), nullable=False)
    created_at = Column(MySQLDateTime(fsp=3), nullable=False, server_default=func.now())
    updated_at = Column(
        MySQLDateTime(fsp=3), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )


# ── releases ─────────────────────────────────────────────────────

class Release(Base):
    __tablename__ = "releases"

    release_id = Column(String(36), primary_key=True, comment="UUID")
    name = Column(String(200), nullable=False)
    release_type = Column(String(50), nullable=False, comment="prompt/policy/workflow/config")
    version = Column(String(50), nullable=False)
    status = Column(
        SAEnum("draft", "in_review", "released", "rolled_back", "failed",
               name="release_status_enum"),
        nullable=False, default="draft",
    )
    released_by = Column(String(100), nullable=False)
    approved_by = Column(String(100), default=None)
    note = Column(Text, default=None)
    released_at = Column(MySQLDateTime(fsp=3), default=None)
    created_at = Column(MySQLDateTime(fsp=3), nullable=False, server_default=func.now())
    updated_at = Column(
        MySQLDateTime(fsp=3), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    items = relationship("ReleaseItem", back_populates="release", cascade="all, delete-orphan")
    rollbacks = relationship("ReleaseRollback", back_populates="release", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_releases_status", "status"),
        Index("idx_releases_type", "release_type"),
    )


class ReleaseItem(Base):
    __tablename__ = "release_items"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    release_id = Column(String(36), ForeignKey("releases.release_id", ondelete="CASCADE"), nullable=False)
    item_type = Column(String(50), nullable=False, comment="prompt/policy/workflow/config")
    item_id = Column(String(36), nullable=False)
    item_name = Column(String(200), nullable=False)
    from_version = Column(String(50), default=None)
    to_version = Column(String(50), nullable=False)

    release = relationship("Release", back_populates="items")

    __table_args__ = (
        Index("idx_release_items_release", "release_id"),
    )


class ReleaseRollback(Base):
    __tablename__ = "release_rollbacks"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    release_id = Column(String(36), ForeignKey("releases.release_id", ondelete="CASCADE"), nullable=False)
    rollback_by = Column(String(100), nullable=False)
    target_version = Column(String(50), nullable=False)
    reason = Column(Text, default=None)
    result_summary = Column(Text, default=None)
    approval_id = Column(String(36), default=None)
    executed_at = Column(MySQLDateTime(fsp=3), nullable=False, server_default=func.now())

    release = relationship("Release", back_populates="rollbacks")


# ── review_cases + review_actions ────────────────────────────────

class ReviewCase(Base):
    __tablename__ = "review_cases"

    case_id = Column(String(36), primary_key=True, comment="UUID")
    run_id = Column(String(36), nullable=False)
    step_id = Column(String(36), default=None)
    review_type = Column(String(50), nullable=False)
    priority = Column(
        SAEnum("low", "medium", "high", "critical", name="review_priority_enum"),
        nullable=False, default="high",
    )
    status = Column(
        SAEnum("pending", "in_review", "approved", "edited", "rejected", "expired",
               name="review_status_enum"),
        nullable=False, default="pending",
    )
    subject = Column(String(500), nullable=False)
    context_json = Column(JSON, default=None)
    created_by = Column(String(100), nullable=False, default="system")
    assigned_to = Column(String(100), default=None)
    created_at = Column(MySQLDateTime(fsp=3), nullable=False, server_default=func.now())
    updated_at = Column(
        MySQLDateTime(fsp=3), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    actions = relationship("ReviewAction", back_populates="case", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_review_cases_status", "status"),
        Index("idx_review_cases_run_id", "run_id"),
        Index("idx_review_cases_type", "review_type"),
    )


class ReviewAction(Base):
    __tablename__ = "review_actions"

    action_id = Column(String(36), primary_key=True, comment="UUID")
    case_id = Column(String(36), ForeignKey("review_cases.case_id", ondelete="CASCADE"), nullable=False)
    action_type = Column(
        SAEnum("approve", "edit", "reject", "reassign", "comment",
               name="review_action_type_enum"),
        nullable=False,
    )
    decision_by = Column(String(100), nullable=False)
    decision_note = Column(Text, default=None)
    override_payload = Column(JSON, default=None)
    created_at = Column(MySQLDateTime(fsp=3), nullable=False, server_default=func.now())

    case = relationship("ReviewCase", back_populates="actions")

    __table_args__ = (
        Index("idx_review_actions_case", "case_id"),
    )


# ── audit_logs ───────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    operator = Column(String(100), nullable=False)
    action = Column(String(100), nullable=False, comment="操作名称")
    target_type = Column(String(50), nullable=False, comment="操作对象类型")
    target_id = Column(String(128), nullable=False)
    before_json = Column(JSON, default=None)
    after_json = Column(JSON, default=None)
    ip_address = Column(String(50), default=None)
    user_agent = Column(String(500), default=None)
    created_at = Column(MySQLDateTime(fsp=3), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_audit_target_id", "target_id"),
        Index("idx_audit_operator", "operator"),
        Index("idx_audit_created_at", "created_at"),
    )


# ── action_ledgers ───────────────────────────────────────────────

class ActionLedger(Base):
    __tablename__ = "action_ledgers"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    action_type = Column(String(100), nullable=False, comment="操作类型")
    target_type = Column(String(50), nullable=False)
    target_id = Column(String(128), nullable=False)
    idempotency_key = Column(String(256), nullable=False, unique=True, comment="幂等键")
    requested_by = Column(String(100), nullable=False)
    approved_by = Column(String(100), default=None)
    status = Column(
        SAEnum("pending", "approved", "executing", "completed", "failed", "rejected",
               name="ledger_status_enum"),
        nullable=False, default="pending",
    )
    result_summary = Column(Text, default=None)
    payload_json = Column(JSON, default=None)
    created_at = Column(MySQLDateTime(fsp=3), nullable=False, server_default=func.now())
    updated_at = Column(
        MySQLDateTime(fsp=3), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    __table_args__ = (
        Index("idx_action_ledgers_key", "idempotency_key"),
        Index("idx_action_ledgers_status", "status"),
        Index("idx_action_ledgers_type", "action_type"),
    )


# ── faq_documents ────────────────────────────────────────────────

class FaqDocument(Base):
    __tablename__ = "faq_documents"

    doc_id = Column(String(36), primary_key=True, comment="UUID")
    group_name = Column(String(100), nullable=False, comment="知识分组")
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    source = Column(String(200), default=None, comment="来源说明")
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(String(100), nullable=False)
    created_at = Column(MySQLDateTime(fsp=3), nullable=False, server_default=func.now())
    updated_at = Column(
        MySQLDateTime(fsp=3), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    __table_args__ = (
        Index("idx_faq_group", "group_name"),
        Index("idx_faq_active", "is_active"),
    )


# ── memory_records + memory_feedback ─────────────────────────────

class MemoryRecord(Base):
    __tablename__ = "memory_records"

    memory_id = Column(String(36), primary_key=True, comment="UUID")
    customer_id = Column(String(20), nullable=False)
    memory_kind = Column(
        SAEnum("semantic", "episodic", name="memory_kind_enum"),
        nullable=False, default="semantic",
    )
    source_type = Column(String(50), nullable=False, comment="agent/human/import")
    source_run_id = Column(String(36), default=None)
    source_message_id = Column(String(128), default=None)
    content_summary = Column(Text, nullable=False)
    risk_level = Column(
        SAEnum("low", "medium", "high", name="memory_risk_enum"),
        nullable=False, default="low",
    )
    pii_flag = Column(Boolean, nullable=False, default=False)
    expires_at = Column(MySQLDateTime(fsp=3), default=None)
    is_active = Column(Boolean, nullable=False, default=True)
    validated_by = Column(String(100), default=None)
    feedback_score = Column(SmallInteger, default=None, comment="-1/0/1")
    created_at = Column(MySQLDateTime(fsp=3), nullable=False, server_default=func.now())
    updated_at = Column(
        MySQLDateTime(fsp=3), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    feedbacks = relationship("MemoryFeedback", back_populates="memory", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_memory_customer", "customer_id"),
        Index("idx_memory_active", "is_active"),
        Index("idx_memory_expires", "expires_at"),
    )


class MemoryFeedback(Base):
    __tablename__ = "memory_feedback"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    memory_id = Column(String(36), ForeignKey("memory_records.memory_id", ondelete="CASCADE"), nullable=False)
    feedback_type = Column(
        SAEnum("disable", "expire", "flag_pii", "human_review", "auto",
               name="memory_feedback_type_enum"),
        nullable=False,
    )
    reason = Column(Text, default=None)
    operated_by = Column(String(100), nullable=False)
    created_at = Column(MySQLDateTime(fsp=3), nullable=False, server_default=func.now())

    memory = relationship("MemoryRecord", back_populates="feedbacks")
