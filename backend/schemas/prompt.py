# -*- coding: utf-8 -*-
"""backend/schemas/prompt.py — Prompt Center schema"""
from __future__ import annotations
import uuid
from enum import Enum
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PromptStatus(str, Enum):
    DRAFT     = "draft"
    REVIEWING = "reviewing"
    ACTIVE    = "active"    # 已发布、生效中
    ARCHIVED  = "archived"


class PromptReleaseStatus(str, Enum):
    PENDING   = "pending"
    APPROVED  = "approved"
    REJECTED  = "rejected"
    ROLLED_BACK = "rolled_back"


# ── Prompt 定义 ───────────────────────────────────────────────────

class PromptCreate(BaseModel):
    name:        str
    agent_name:  str                        # 所属 Agent
    description: Optional[str] = None
    content:     str                        # Prompt 正文（支持模板变量 {var}）
    variables:   List[str] = Field(default_factory=list)   # 模板变量列表
    tags:        List[str] = Field(default_factory=list)
    created_by:  str


class PromptRecord(BaseModel):
    prompt_id:   uuid.UUID = Field(default_factory=uuid.uuid4)
    name:        str
    agent_name:  str
    description: Optional[str] = None
    content:     str
    variables:   List[str] = Field(default_factory=list)
    tags:        List[str] = Field(default_factory=list)
    version:     int = 1
    status:      PromptStatus = PromptStatus.DRAFT
    created_by:  str
    created_at:  datetime = Field(default_factory=_utcnow)
    updated_at:  datetime = Field(default_factory=_utcnow)

    model_config = ConfigDict(use_enum_values=True)


# ── Prompt 发布记录 ───────────────────────────────────────────────

class PromptReleaseCreate(BaseModel):
    prompt_id:   uuid.UUID
    version:     int
    released_by: str
    note:        Optional[str] = None


class PromptRelease(BaseModel):
    release_id:  uuid.UUID = Field(default_factory=uuid.uuid4)
    prompt_id:   uuid.UUID
    version:     int
    status:      PromptReleaseStatus = PromptReleaseStatus.PENDING
    released_by: str
    approved_by: Optional[str] = None
    note:        Optional[str] = None
    released_at: datetime = Field(default_factory=_utcnow)

    model_config = ConfigDict(use_enum_values=True)


# ── API 响应 ──────────────────────────────────────────────────────

class PromptListItem(BaseModel):
    prompt_id:  str
    name:       str
    agent_name: str
    version:    int
    status:     str
    created_by: str
    updated_at: datetime
