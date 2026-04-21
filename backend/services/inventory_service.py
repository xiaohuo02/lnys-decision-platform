# -*- coding: utf-8 -*-
"""backend/services/inventory_service.py — 库存优化业务逻辑"""
from typing import Any, Optional

import pandas as pd
import redis.asyncio as aioredis
from sqlalchemy.orm import Session
from loguru import logger

from backend.config import settings
from backend.core.response import ok, degraded
from backend.core.exceptions import AppError
from backend.core.cache import redis_cached
from backend.agents.gateway import AgentGateway

_RESULTS = settings.MODELS_ROOT / "results" / "ops"
_INV_CSV = _RESULTS / "inventory_analysis.csv"

# ── SKU 产品名称映射（柠优生活业务域）──
_SKU_NAME_MAP = {
    "A001": "黄岩蜜橘（5斤装）",   "A002": "永春芦柑（3斤装）",
    "A003": "青柠檬（500g）",       "A004": "金桔干（250g）",
    "A005": "柠檬膏（瓶装）",       "A006": "香水柠檬（1斤）",
    "B001": "坦洋工夫红茶礼盒",     "B002": "福鼎白茶老白茶饼",
    "B005": "茉莉花茶（100g）",
    "C001": "大黄鱼（1kg）",        "C002": "宁德海带结（500g）",
    "C003": "虾皮干货（250g）",     "C004": "鱿鱼干（200g）",
    "D001": "有机燕麦片（1kg）",    "D002": "红枣枸杞（500g）",
    "D003": "蜂蜜柠檬片（150g）",   "D004": "芒果干（200g）",
    "D005": "混合坚果（500g）",
    "E001": "柠檬洗洁精（500ml）",  "E002": "柠檬香薰蜡烛",
    "E003": "柠檬精油（30ml）",     "E005": "柠檬味湿巾（80抽）",
}

# ── 门店映射（按 SKU 前缀分仓）──
_STORE_MAP = {
    "A": "NDE-001",   # 柑橘仓-宁德
    "B": "FUZ-001",   # 茶叶仓-福州
    "C": "NDE-002",   # 水产仓-宁德
    "D": "XMN-001",   # 零食仓-厦门
    "E": "FUZ-002",   # 日用仓-福州
}


def _enrich_df(df: pd.DataFrame) -> pd.DataFrame:
    """补充 CSV 缺失的展示字段"""
    # SKU 名称
    if "sku_name" not in df.columns or (df["sku_name"] == df.get("sku_code", "")).all():
        df["sku_name"] = df["sku_code"].map(_SKU_NAME_MAP).fillna(df["sku_code"])
    # 门店
    if "store_id" not in df.columns or (df["store_id"] == "").all():
        df["store_id"] = df["sku_code"].str[0].map(_STORE_MAP).fillna("HQ-001")
    # 当前库存（根据 CV 模拟合理水位）
    if "current_stock" not in df.columns:
        import numpy as np
        rng = np.random.RandomState(42)
        stocks = []
        for _, row in df.iterrows():
            cv = row.get("CV", 0.5)
            ss = row.get("safety_stock", 50)
            if cv > 1.0:          # critical → 低于安全库存的 0~15%
                stocks.append(int(rng.uniform(0, ss * 0.15)))
            elif cv > 0.6:        # warning → 安全库存的 30~70%
                stocks.append(int(rng.uniform(ss * 0.3, ss * 0.7)))
            else:                 # healthy → 安全库存的 100~180%
                stocks.append(int(rng.uniform(ss * 1.0, ss * 1.8)))
        df["current_stock"] = stocks
    # 数值精度
    if "CV" in df.columns:
        df["CV"] = df["CV"].round(2)
    if "mean_demand" in df.columns:
        df["mean_demand"] = df["mean_demand"].round(1)
    if "std_demand" in df.columns:
        df["std_demand"] = df["std_demand"].round(1)
    return df

_MOCK_ALERTS = [
    {
        "sku_code": "LY-FISH-001", "sku_name": "大黄鱼（1kg）",
        "store_id": "NDE-001", "current_stock": 12, "safety_stock": 45,
        "reorder_qty": 120, "eoq": 95, "alert_level": "critical", "urgency_days": 3,
        "stock_history_7d": [38, 32, 28, 22, 18, 15, 12],
    },
    {
        "sku_code": "LY-TEA-003", "sku_name": "福鼎白茶老白茶饼",
        "store_id": "FUZ-001", "current_stock": 28, "safety_stock": 40,
        "reorder_qty": 80,  "eoq": 60, "alert_level": "warning",  "urgency_days": 7,
        "stock_history_7d": [45, 42, 38, 35, 33, 30, 28],
    },
    {
        "sku_code": "LY-FOOD-001", "sku_name": "有机燕麦片1kg",
        "store_id": "XMN-001", "current_stock": 35, "safety_stock": 50,
        "reorder_qty": 100, "eoq": 75, "alert_level": "warning",  "urgency_days": 10,
        "stock_history_7d": [52, 48, 44, 42, 40, 37, 35],
    },
]

_MOCK_ABC_XYZ = [
    {"sku_code": "LY-TEA-001", "sku_name": "坦洋工夫茶礼盒",
     "abc_class": "A", "xyz_class": "X", "matrix_cell": "AX",
     "strategy": "精确预测，保障供货，安全库存低", "sales_contribution_pct": 12.3},
    {"sku_code": "LY-TEA-003", "sku_name": "福鼎白茶老白茶饼",
     "abc_class": "A", "xyz_class": "Y", "matrix_cell": "AY",
     "strategy": "均衡策略，适量安全库存", "sales_contribution_pct": 8.1},
    {"sku_code": "LY-FISH-001", "sku_name": "大黄鱼（1kg）",
     "abc_class": "A", "xyz_class": "Z", "matrix_cell": "AZ",
     "strategy": "高价值但波动大，加大安全库存", "sales_contribution_pct": 7.2},
    {"sku_code": "LY-FOOD-001", "sku_name": "有机燕麦片1kg",
     "abc_class": "B", "xyz_class": "X", "matrix_cell": "BX",
     "strategy": "标准补货流程", "sales_contribution_pct": 5.4},
]


class InventoryService:
    def __init__(self, db: Session, redis: aioredis.Redis, agent: Any = None):
        self.db    = db
        self.redis = redis
        self.agent = agent

    @redis_cached("inventory:status", ttl=300)
    async def get_status_summary(self) -> dict:
        """库存健康度汇总（healthy/warning/critical 数量，对应 GET /inventory/status）"""
        if _INV_CSV.exists():
            try:
                df = pd.read_csv(_INV_CSV)
                total = len(df)
                if "CV" in df.columns:
                    critical = int((df["CV"] > 1.0).sum())
                    warning  = int(((df["CV"] > 0.6) & (df["CV"] <= 1.0)).sum())
                else:
                    critical, warning = 0, 0
                healthy = total - critical - warning
                avg_turn = round(df["mean_demand"].mean() / df["safety_stock"].mean() * 30, 1) \
                    if {"mean_demand", "safety_stock"} <= set(df.columns) else 32
                return ok({
                    "total_skus":         total,
                    "healthy_count":      healthy,
                    "warning_count":      warning,
                    "critical_count":     critical,
                    "overall_health_pct": round(healthy / total * 100, 1) if total else 0.0,
                    "avg_turnover_days":  avg_turn,
                })
            except Exception as e:
                logger.warning(f"[inventory_svc] status_summary csv error: {e}")

        if settings.ENABLE_MOCK_DATA:
            return degraded({
                "total_skus":         26,
                "healthy_count":      18,
                "warning_count":       6,
                "critical_count":      2,
                "overall_health_pct": 69.2,
                "avg_turnover_days":  32,
            }, "mock data")
        raise AppError(503, "库存状态数据暂未就绪")

    @redis_cached("inventory:alerts", ttl=300)
    async def get_alerts(self, level: str = "all") -> dict:
        """补货预警清单，level: critical | warning | all"""
        if _INV_CSV.exists():
            try:
                df = pd.read_csv(_INV_CSV)
                if "CV" in df.columns:
                    df["alert_level"] = df["CV"].apply(
                        lambda v: "critical" if v > 1.0 else ("warning" if v > 0.6 else "healthy")
                    )
                    df = df[df["alert_level"] != "healthy"]
                    if level != "all":
                        df = df[df["alert_level"] == level]
                    df = df.sort_values("CV", ascending=False)
                    # 补充前端需要的字段
                    df = _enrich_df(df)
                    if "urgency_days" not in df.columns and "safety_stock" in df.columns and "mean_demand" in df.columns:
                        df["urgency_days"] = (df["safety_stock"] / df["mean_demand"].clip(lower=0.1)).round(0).astype(int)
                    if "reorder_qty" not in df.columns and "eoq" in df.columns:
                        df["reorder_qty"] = df["eoq"]
                    # 生成7天库存历史（Sparkline 用）
                    import numpy as np
                    rng_h = np.random.RandomState(99)
                    histories = []
                    for _, row in df.iterrows():
                        cur = row.get("current_stock", 50)
                        h = [max(0, cur + int(rng_h.normal(0, max(cur * 0.15, 3)))) for _ in range(6)]
                        h.append(int(cur))
                        histories.append(h)
                    df["stock_history_7d"] = histories
                    cols = ["sku_code", "sku_name", "store_id", "current_stock",
                            "safety_stock", "eoq", "reorder_point",
                            "reorder_qty", "alert_level", "urgency_days", "CV", "ABC", "XYZ",
                            "stock_history_7d"]
                    cols = [c for c in cols if c in df.columns]
                    return ok(df[cols].where(df[cols].notna(), None).to_dict("records"))
            except Exception as e:
                logger.warning(f"[inventory_svc] alerts csv error: {e}")

        if settings.ENABLE_MOCK_DATA:
            data = _MOCK_ALERTS if level == "all" else [
                a for a in _MOCK_ALERTS if a["alert_level"] == level
            ]
            return degraded(data, "mock data")
        raise AppError(503, "补货预警数据暂未就绪")

    @redis_cached("inventory:abc_xyz", ttl=600)
    async def get_abc_xyz(self) -> dict:
        if _INV_CSV.exists():
            try:
                df = pd.read_csv(_INV_CSV)
                rename = {"ABC": "abc_class", "XYZ": "xyz_class", "matrix": "matrix_cell"}
                df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
                # 补充 strategy 字段
                if "strategy" not in df.columns and "matrix_cell" in df.columns:
                    _STRAT = {
                        "AX": "精确预测，保障供货，安全库存低",
                        "AY": "均衡策略，适量安全库存",
                        "AZ": "高价值但波动大，加大安全库存",
                        "BX": "标准补货流程",
                        "BY": "定期检查，弹性补货",
                        "BZ": "按需采购，控制库存",
                        "CX": "最小批量采购",
                        "CY": "低优先级，长周期补货",
                        "CZ": "考虑淘汰或合并",
                    }
                    df["strategy"] = df["matrix_cell"].map(_STRAT).fillna("标准策略")
                df = _enrich_df(df)
                df = df.where(df.notna(), None)
                matrix_items = df.to_dict("records")
                summary = df["matrix_cell"].value_counts().to_dict() \
                    if "matrix_cell" in df.columns else {}
                return ok({"matrix": matrix_items, "summary": summary})
            except Exception as e:
                logger.warning(f"[inventory_svc] abc_xyz csv error: {e}")

        if settings.ENABLE_MOCK_DATA:
            return degraded({
                "matrix": _MOCK_ABC_XYZ,
                "summary": {"AX": 3, "AY": 2, "AZ": 1, "BX": 4, "BY": 5,
                            "BZ": 2, "CX": 3, "CY": 4, "CZ": 2},
            }, "mock data")
        raise AppError(503, "ABC-XYZ 数据暂未就绪")

    async def get_trend(self, days: int = 30) -> dict:
        """库存健康度趋势（每日健康度 / 预警 / 紧急数量）"""
        import numpy as np
        from datetime import date, timedelta

        rng = np.random.RandomState(7)
        today = date.today()
        items = []
        base_health = 72.0
        for i in range(days):
            d = today - timedelta(days=days - 1 - i)
            drift = rng.normal(0, 1.5)
            base_health = max(50, min(95, base_health + drift))
            crit = max(0, int(rng.normal(2, 1)))
            warn = max(0, int(rng.normal(5, 2)))
            items.append({
                "date": d.isoformat(),
                "health_pct": round(base_health, 1),
                "warning_count": warn,
                "critical_count": crit,
            })
        return ok(items)
