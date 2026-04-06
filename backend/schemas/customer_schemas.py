# -*- coding: utf-8 -*-
"""backend/schemas/customer_schemas.py — 客户分析 Pydantic 模型"""
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class MemberLevel(str, Enum):
    regular = "普通"
    silver  = "银卡"
    gold    = "金卡"
    diamond = "钻石"


# ── RFM ──────────────────────────────────────────────────────
class RFMRecord(BaseModel):
    customer_id:  str
    recency:      float = Field(..., description="距上次购买天数")
    frequency:    float = Field(..., description="购买频次")
    monetary:     float = Field(..., description="消费金额")
    r_score:      Optional[int] = Field(None, ge=1, le=5)
    f_score:      Optional[int] = Field(None, ge=1, le=5)
    m_score:      Optional[int] = Field(None, ge=1, le=5)
    rfm_total:    Optional[int] = None
    segment:      Optional[str] = None
    member_level: Optional[str] = None


# ── 客群分布 ──────────────────────────────────────────────────
class SegmentItem(BaseModel):
    name:  str
    count: int
    pct:   float
    color: Optional[str] = None


class SegmentsResponse(BaseModel):
    segments:         List[SegmentItem]
    silhouette_score: Optional[float] = None
    cluster_k:        Optional[int]   = None


# ── CLV ───────────────────────────────────────────────────────
class CLVRecord(BaseModel):
    customer_id:             str
    name:                    Optional[str]   = None
    member_level:            Optional[str]   = None
    predicted_purchases_90d: Optional[float] = None
    predicted_clv:           float
    clv_tier:                Optional[str]   = None


# ── 流失预测 ──────────────────────────────────────────────────
class ChurnPredictRequest(BaseModel):
    customer_id:        str   = Field(...,  examples=["LY000088"])
    recency:            float = Field(...,  description="距上次购买天数",     ge=0)
    frequency_30d:      int   = Field(...,  description="近30天购买次数",     ge=0)
    frequency_90d:      int   = Field(...,  description="近90天购买次数",     ge=0)
    monetary_trend:     float = Field(...,  description="客单价变化趋势")
    return_rate:        float = Field(...,  description="退货率",            ge=0, le=1)
    complaint_count:    int   = Field(...,  description="客服投诉次数",       ge=0)
    member_level:       str   = Field(...,  examples=["银卡"])
    register_days:      int   = Field(...,  description="注册天数",          ge=0)
    social_interaction: int   = Field(0,    description="社交媒体互动频率",   ge=0)


class ChurnPredictResponse(BaseModel):
    customer_id:        str
    churn_probability:  float = Field(..., ge=0.0, le=1.0)
    risk_level:         str   = Field(..., examples=["高"])
    top3_reasons:       Optional[List[str]] = None
    recommended_action: Optional[str]       = None
    reflect_passed:     bool = True


class ChurnRiskRecord(BaseModel):
    customer_id:        str
    churn_probability:  float
    risk_level:         str
    top3_reasons:       Optional[List[str]] = None
    recommended_action: Optional[str]       = None
    member_level:       Optional[str]       = None
    segment:            Optional[str]       = None


class ChurnRiskListData(BaseModel):
    total_high_risk: int = 0
    items:           List[ChurnRiskRecord] = Field(default_factory=list)
