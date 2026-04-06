# -*- coding: utf-8 -*-
"""backend/schemas/fraud_schemas.py — 欺诈风控 Pydantic 模型（含 HITL）"""
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from enum import Enum


class RiskLevel(str, Enum):
    low    = "低"
    medium = "中"
    high   = "高"


# ── 欺诈评分请求 ──────────────────────────────────────────────
class FraudScoreRequest(BaseModel):
    transaction_id:       str   = Field(...,  examples=["TX20240315001"])
    customer_id:          str   = Field(...,  examples=["LY000088"])
    amount:               float = Field(...,  gt=0)
    hour_of_day:          int   = Field(default_factory=lambda: datetime.utcnow().hour, ge=0, le=23)
    province:             Optional[str]   = None
    ip_province:          Optional[str]   = None
    device_type:          Optional[str]   = Field(None, examples=["mobile"])
    is_new_account:       bool            = False
    same_device_1h_count: int             = Field(0, ge=0)
    payment_method:       Optional[str]   = None
    v1:                   Optional[float] = None
    v2:                   Optional[float] = None


# ── 欺诈评分响应（含 HITL 字段，方案_07 § 4.3）─────────────────
class FraudScoreResponse(BaseModel):
    transaction_id:  str
    risk_score:      float      = Field(..., ge=0.0, le=100.0)
    risk_level:      str
    rules_triggered: List[str]  = []
    lgbm_score:      Optional[float] = None
    ae_score:        Optional[float] = None
    final_score:     float
    action:          str
    hitl_required:   bool             = False
    thread_id:       Optional[str]    = None
    reflect_passed:  bool             = True


# ── 欺诈 HITL 审核请求（新增接口，方案_07 § 4.3）────────────────
class FraudReviewRequest(BaseModel):
    decision: Literal["block", "release", "monitor"]
    reviewer: str
    note:     str = ""


# ── 欺诈统计 ──────────────────────────────────────────────────
class FraudStats(BaseModel):
    today_total:     int
    today_blocked:   int
    block_rate:      float
    high_risk_count: int
    mid_risk_count:  int
    model_auc:       float = 0.9992
