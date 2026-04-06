# -*- coding: utf-8 -*-
"""backend/schemas/forecast_schemas.py — 销售预测 Pydantic 模型"""
from pydantic import BaseModel, Field
from typing import Optional, List


# ── 预测点 ────────────────────────────────────────────────────
class ForecastPoint(BaseModel):
    date:      str
    predicted: float
    lower:     Optional[float] = None
    upper:     Optional[float] = None


# ── 请求 ──────────────────────────────────────────────────────
class ForecastPredictRequest(BaseModel):
    sku_code: str = Field(..., examples=["LY-TEA-001"])
    store_id: str = Field(..., examples=["NDE-001"])
    days:     int = Field(30, ge=1, le=90, description="预测天数")


# ── 响应 ──────────────────────────────────────────────────────
class ForecastPredictResponse(BaseModel):
    sku_code:      str
    store_id:      str
    model_used:    str  = "stacking"
    forecast:      List[ForecastPoint]
    reflect_passed: bool = True


class ModelComparisonItem(BaseModel):
    model: str
    mape:  float
    mae:   Optional[float] = None


class ForecastSummaryResponse(BaseModel):
    generated_at:     Optional[str] = None
    mape_stacking:    float = 19.5
    model_comparison: List[ModelComparisonItem]
    forecast_7d:      List[ForecastPoint]
