# -*- coding: utf-8 -*-
"""backend/schemas/review.py — HITL 审核 schema"""
from __future__ import annotations
import uuid
from enum import Enum
from typing import Any, Dict, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ReviewType(str, Enum):
    FRAUD_HITL      = "fraud_hitl"
    REFUND_HITL     = "refund_hitl"
    POLICY_CHANGE   = "policy_change"
    PROMPT_RELEASE  = "prompt_release"
    ORDER_FREEZE    = "order_freeze"
    RISK_STATUS     = "risk_status"


class ReviewStatus(str, Enum):
    PENDING    = "pending"
    IN_REVIEW  = "in_review"
    APPROVED   = "approved"
    EDITED     = "edited"      # 审核人修改后通过
    REJECTED   = "rejected"
    EXPIRED    = "expired"


class ReviewPriority(str, Enum):
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


class ReviewActionType(str, Enum):
    APPROVE   = "approve"
    EDIT      = "edit"
    REJECT    = "reject"
    REASSIGN  = "reassign"
    COMMENT   = "comment"


# ── 审核案例 ──────────────────────────────────────────────────────

class ReviewCaseCreate(BaseModel):
    run_id:       uuid.UUID
    step_id:      Optional[uuid.UUID] = None
    review_type:  ReviewType
    priority:     ReviewPriority = ReviewPriority.HIGH
    subject:      str
    context:      Dict[str, Any] = Field(default_factory=dict)
    created_by:   str = "system"
    assigned_to:  Optional[str] = None


class ReviewCase(BaseModel):
    case_id:      uuid.UUID = Field(default_factory=uuid.uuid4)
    run_id:       uuid.UUID
    step_id:      Optional[uuid.UUID] = None
    review_type:  ReviewType
    priority:     ReviewPriority = ReviewPriority.HIGH
    status:       ReviewStatus = ReviewStatus.PENDING
    subject:      str
    context:      Dict[str, Any] = Field(default_factory=dict)
    created_by:   str = "system"
    assigned_to:  Optional[str] = None
    created_at:   datetime = Field(default_factory=_utcnow)
    updated_at:   datetime = Field(default_factory=_utcnow)

    model_config = ConfigDict(use_enum_values=True)


# ── 审核动作 ──────────────────────────────────────────────────────

class ReviewActionCreate(BaseModel):
    case_id:          uuid.UUID
    action_type:      ReviewActionType
    decision_by:      str
    decision_note:    Optional[str] = None
    override_payload: Optional[Dict[str, Any]] = None  # edit 时提供修改后的数据


class ReviewAction(BaseModel):
    action_id:        uuid.UUID = Field(default_factory=uuid.uuid4)
    case_id:          uuid.UUID
    action_type:      ReviewActionType
    decision_by:      str
    decision_note:    Optional[str] = None
    override_payload: Optional[Dict[str, Any]] = None
    created_at:       datetime = Field(default_factory=_utcnow)

    model_config = ConfigDict(use_enum_values=True)


# ── API 响应 ──────────────────────────────────────────────────────

class ReviewCaseResponse(BaseModel):
    case_id:     str
    review_type: str
    priority:    str
    status:      str
    subject:     str
    created_by:  str
    assigned_to: Optional[str]
    created_at:  datetime
    updated_at:  datetime
