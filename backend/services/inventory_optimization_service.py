# -*- coding: utf-8 -*-
"""backend/services/inventory_optimization_service.py

InventoryOptimizationService — 库存优化服务

╔══════════════════════════════════════════════════════════════════╗
║  Agent 契约                                                       ║
╠══════════════════════════════════════════════════════════════════╣
║  输入   : InventoryRequest（SKU/门店过滤、提前期、参数）           ║
║  输出   : InventoryResult（EOQ 建议、安全库存、补货预警 + ref）    ║
║  可调用 : 运筹学公式计算（EOQ/安全库存）、CSV 数据读取             ║
║  禁止   : 直接下单、直接修改库存表、调用 LLM                       ║
║  降级   : 无实时库存数据时使用快照均值做估算                        ║
║  HITL   : 不需要                                                   ║
║  依赖   : data/generated/inventory.csv                            ║
║           SalesForecastService 输出（demand 数据）                ║
║  Trace  : step_name="inventory_optimization"                     ║
║           output_summary=urgent_sku 数量 + 建议补货总量           ║
╚══════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from loguru import logger
from pydantic import BaseModel, Field

from backend.config import settings
from backend.schemas.artifact import ArtifactRef, ArtifactType


_DATA_ROOT = settings.MODELS_ROOT.parent / "data"
_INVENTORY_CSV = _DATA_ROOT / "generated" / "inventory.csv"

Z_95 = 1.65   # 95% 服务水平


class InventoryRequest(BaseModel):
    run_id:             Optional[str] = None
    store_id:           Optional[str] = None
    sku_codes:          Optional[List[str]] = None
    lead_time_days:     float = 7.0       # 平均补货提前期（天）
    ordering_cost:      float = 50.0      # 单次订货成本（元）
    holding_cost_ratio: float = 0.25      # 年持有成本率（占商品成本比例）
    unit_cost:          float = 100.0     # 商品单位成本（元，全局默认）
    forecast_daily_demand: Optional[float] = None  # 来自 ForecastService 的日均需求


class SKURecommendation(BaseModel):
    sku_code:        str
    store_id:        Optional[str]
    current_stock:   int
    avg_daily_demand: float
    safety_stock:    int
    reorder_point:   int
    eoq:             int
    urgent:          bool
    shortage_days:   Optional[float] = None   # 预计几天后缺货


class InventoryResult(BaseModel):
    run_id:           Optional[str]
    data_ready:       bool
    degraded:         bool = False

    total_skus:       int = 0
    urgent_count:     int = 0
    recommendations:  List[SKURecommendation] = Field(default_factory=list)
    total_reorder_qty: int = 0

    artifact:         Optional[ArtifactRef] = None
    error_message:    Optional[str] = None
    optimized_at:     datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class InventoryOptimizationService:

    def optimize(self, request: InventoryRequest) -> InventoryResult:
        try:
            df = self._load_inventory(request)
        except Exception as e:
            logger.warning(f"[InventoryService] 库存数据加载失败: {e}")
            return InventoryResult(
                run_id=request.run_id, data_ready=False,
                error_message=str(e),
            )

        recs: List[SKURecommendation] = []
        for _, row in df.iterrows():
            rec = self._calc_sku(row, request)
            recs.append(rec)

        urgent = [r for r in recs if r.urgent]
        result = InventoryResult(
            run_id=request.run_id,
            data_ready=True,
            total_skus=len(recs),
            urgent_count=len(urgent),
            recommendations=sorted(recs, key=lambda x: x.urgent, reverse=True)[:50],
            total_reorder_qty=sum(r.eoq for r in urgent),
            artifact=ArtifactRef(
                artifact_type=ArtifactType.INVENTORY,
                summary=(
                    f"库存优化: {len(recs)} 支 SKU, "
                    f"紧急补货 {len(urgent)} 支, "
                    f"建议补货总量 {sum(r.eoq for r in urgent):,}"
                ),
            ),
        )
        logger.info(
            f"[InventoryService] skus={len(recs)} urgent={len(urgent)} "
            f"total_reorder={result.total_reorder_qty}"
        )
        return result

    def _load_inventory(self, request: InventoryRequest) -> pd.DataFrame:
        if not _INVENTORY_CSV.exists():
            raise FileNotFoundError(f"inventory.csv 不存在: {_INVENTORY_CSV}")
        df = pd.read_csv(_INVENTORY_CSV)
        if request.store_id and "store_id" in df.columns:
            df = df[df["store_id"] == request.store_id]
        if request.sku_codes and "sku_code" in df.columns:
            df = df[df["sku_code"].isin(request.sku_codes)]
        return df

    def _calc_sku(self, row: pd.Series, request: InventoryRequest) -> SKURecommendation:
        sku    = str(row.get("sku_code", "unknown"))
        store  = str(row.get("store_id", "")) or None
        stock  = int(row.get("stock_qty", 0))

        # 日均需求：优先 forecast，其次库存快照推算
        if request.forecast_daily_demand:
            avg_demand = request.forecast_daily_demand
        elif "avg_daily_sales" in row:
            avg_demand = float(row["avg_daily_sales"])
        else:
            avg_demand = max(float(row.get("reorder_point", 20)) / max(request.lead_time_days, 1), 1.0)

        sigma_demand = avg_demand * 0.25   # 假设需求标准差 = 均值 25%
        safety = max(int(Z_95 * sigma_demand * np.sqrt(request.lead_time_days)), 1)
        rop    = int(avg_demand * request.lead_time_days + safety)

        # EOQ
        annual_demand = avg_demand * 365
        holding_cost  = request.unit_cost * request.holding_cost_ratio
        eoq = max(int(np.sqrt(2 * annual_demand * request.ordering_cost / holding_cost)), 1)

        urgent = stock <= rop
        shortage_days = round(float(stock / avg_demand), 1) if avg_demand > 0 else None

        return SKURecommendation(
            sku_code=sku, store_id=store,
            current_stock=stock,
            avg_daily_demand=round(avg_demand, 2),
            safety_stock=safety,
            reorder_point=rop,
            eoq=eoq,
            urgent=urgent,
            shortage_days=shortage_days,
        )


inventory_optimization_service = InventoryOptimizationService()
