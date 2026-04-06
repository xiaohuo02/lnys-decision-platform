# -*- coding: utf-8 -*-
"""backend/schemas/run_state.py — 工作流运行状态统一 schema"""
from __future__ import annotations
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RunStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    PAUSED    = "paused"        # HITL 中断等待
    COMPLETED = "completed"
    FAILED    = "failed"
    CANCELLED = "cancelled"


class StepType(str, Enum):
    AGENT_CALL   = "agent_call"
    TOOL_CALL    = "tool_call"
    SERVICE_CALL = "service_call"
    LLM_CALL     = "llm_call"
    HITL         = "hitl"
    HANDOFF      = "handoff"
    GUARDRAIL    = "guardrail"


class TokenUsage(BaseModel):
    prompt_tokens:     int = 0
    completion_tokens: int = 0
    total_tokens:      int = 0


class GuardrailHit(BaseModel):
    rule_name: str
    severity:  str          # info / warning / block
    message:   str
    triggered_at: datetime = Field(default_factory=_utcnow)


# ── Run（顶层执行记录）──────────────────────────────────────────────

class RunCreate(BaseModel):
    """创建一次 run 时的入参"""
    thread_id:        str
    request_id:       str
    entrypoint:       str
    workflow_name:    str
    workflow_version: str = "latest"
    input_summary:    Optional[str] = None
    triggered_by:     Optional[str] = None


class RunRecord(BaseModel):
    """run 完整记录（对应 DB runs 表）"""
    run_id:           uuid.UUID = Field(default_factory=uuid.uuid4)
    thread_id:        str
    request_id:       str
    entrypoint:       str
    workflow_name:    str
    workflow_version: str = "latest"
    status:           RunStatus = RunStatus.PENDING
    input_summary:    Optional[str] = None
    output_summary:   Optional[str] = None
    total_tokens:     int = 0
    total_cost:       float = 0.0
    error_message:    Optional[str] = None
    triggered_by:     Optional[str] = None
    started_at:       datetime = Field(default_factory=_utcnow)
    ended_at:         Optional[datetime] = None
    latency_ms:       Optional[int] = None

    model_config = ConfigDict(use_enum_values=True)


# ── Step（步骤级记录）──────────────────────────────────────────────

class StepRecord(BaseModel):
    """单个 step 记录（对应 DB run_steps 表）"""
    step_id:          uuid.UUID = Field(default_factory=uuid.uuid4)
    run_id:           uuid.UUID
    parent_step_id:   Optional[uuid.UUID] = None
    step_type:        StepType
    step_name:        str
    agent_name:       Optional[str] = None
    tool_name:        Optional[str] = None
    model_name:       Optional[str] = None
    prompt_id:        Optional[uuid.UUID] = None
    prompt_version:   Optional[str] = None
    policy_version:   Optional[str] = None
    handoff_from:     Optional[str] = None
    handoff_to:       Optional[str] = None
    status:           RunStatus = RunStatus.PENDING
    input_summary:    Optional[str] = None
    output_summary:   Optional[str] = None
    guardrail_hits:   List[GuardrailHit] = Field(default_factory=list)
    token_usage:      TokenUsage = Field(default_factory=TokenUsage)
    cost_amount:      float = 0.0
    retry_count:      int = 0
    artifact_ids:     List[str] = Field(default_factory=list)
    error_message:    Optional[str] = None
    started_at:       datetime = Field(default_factory=_utcnow)
    ended_at:         Optional[datetime] = None

    model_config = ConfigDict(use_enum_values=True)


# ── 公共响应封装 ────────────────────────────────────────────────────

class RunSummaryResponse(BaseModel):
    run_id:        str
    status:        str
    workflow_name: str
    latency_ms:    Optional[int]
    total_tokens:  int
    total_cost:    float
    error_message: Optional[str]
    started_at:    datetime
    ended_at:      Optional[datetime]
