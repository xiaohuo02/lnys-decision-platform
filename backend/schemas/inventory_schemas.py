# -*- coding: utf-8 -*-
"""backend/schemas/inventory_schemas.py — 库存管理 Pydantic 模型"""
from pydantic import BaseModel, Field
from typing import Optional, List


# ── 库存整体状态 ──────────────────────────────────────────────
class InventoryStatusResponse(BaseModel):
    total_skus:         int
    healthy_count:      int
    warning_count:      int
    critical_count:     int
    overall_health_pct: float
    avg_turnover_days:  float


# ── 补货预警 ──────────────────────────────────────────────────
class InventoryAlertItem(BaseModel):
    sku_code:      str
    sku_name:      Optional[str] = None
    store_id:      Optional[str] = None
    current_stock: int
    safety_stock:  int
    reorder_qty:   Optional[int] = None
    eoq:           Optional[int] = None
    alert_level:   str           = Field(..., example="critical")
    urgency_days:  Optional[int] = None
    stock_history_7d: Optional[List[float]] = Field(None, description="7天库存历史（用于 Sparkline）")


# ── ABC-XYZ 矩阵 ──────────────────────────────────────────────
class AbcXyzItem(BaseModel):
    sku_code:               str
    sku_name:               Optional[str]   = None
    abc_class:              str
    xyz_class:              Optional[str]   = None
    matrix_cell:            Optional[str]   = None
    strategy:               Optional[str]   = None
    sales_contribution_pct: Optional[float] = None


# ── 库存趋势 ──────────────────────────────────────────────────
class InventoryTrendItem(BaseModel):
    date:           str
    health_pct:     float
    warning_count:  int = 0
    critical_count: int = 0
