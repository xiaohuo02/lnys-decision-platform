# -*- coding: utf-8 -*-
"""backend/services/dashboard_service.py — 业务总览 KPI 聚合"""
import pandas as pd
import redis.asyncio as aioredis
from sqlalchemy.orm import Session
from loguru import logger

from backend.config import settings
from backend.core.response import ok, degraded
from backend.core.exceptions import AppError
from backend.core.cache import redis_cached

_CUSTOMER = settings.MODELS_ROOT / "results" / "customer"
_FORECAST = settings.MODELS_ROOT / "results" / "forecast"


class DashboardService:
    def __init__(self, db: Session, redis: aioredis.Redis):
        self.db = db
        self.redis = redis

    @redis_cached("dashboard:kpis", ttl=300)
    async def get_kpis(self) -> dict:
        kpis = {
            "total_orders": None,
            "active_customers": None,
            "avg_order_value": None,
        }

        # ── 从 RFM CSV 聚合订单数 & 活跃客户 ──
        rfm_path = _CUSTOMER / "rfm_result.csv"
        if rfm_path.exists():
            try:
                df = pd.read_csv(rfm_path)
                freq_col = "Frequency" if "Frequency" in df.columns else "frequency"
                rec_col = "Recency" if "Recency" in df.columns else "recency"
                mon_col = "Monetary" if "Monetary" in df.columns else "monetary"

                if freq_col in df.columns:
                    kpis["total_orders"] = int(df[freq_col].sum())
                if rec_col in df.columns:
                    kpis["active_customers"] = int((df[rec_col] <= 30).sum())
                if mon_col in df.columns and freq_col in df.columns:
                    total_monetary = df[mon_col].sum()
                    total_freq = df[freq_col].sum()
                    if total_freq > 0:
                        kpis["avg_order_value"] = round(total_monetary / total_freq, 2)
            except Exception as e:
                logger.warning(f"[dashboard_svc] rfm csv error: {e}")

        # ── 从 Stacking CSV 补充今日预测销售 + 真实趋势 ──
        stacking_path = _FORECAST / "stacking_result.csv"
        if stacking_path.exists():
            try:
                df = pd.read_csv(stacking_path)
                if "actual" in df.columns:
                    kpis["today_sales"] = round(float(df["actual"].iloc[-1]), 2)
                    # 销售额环比趋势（今日 vs 昨日）
                    if len(df) >= 2:
                        today_val = float(df["actual"].iloc[-1])
                        yesterday_val = float(df["actual"].iloc[-2])
                        if yesterday_val > 0:
                            kpis["sales_trend_pct"] = round(
                                (today_val - yesterday_val) / yesterday_val * 100, 1
                            )
                if "ensemble" in df.columns:
                    kpis["today_forecast"] = round(float(df["ensemble"].iloc[-1]), 2)
            except Exception as e:
                logger.warning(f"[dashboard_svc] forecast csv error: {e}")

        has_data = any(v is not None for v in kpis.values())
        if has_data:
            return ok(kpis)

        if settings.ENABLE_MOCK_DATA:
            return degraded({
                "total_orders": 12680,
                "active_customers": 3420,
                "avg_order_value": 258.50,
                "today_sales": 285000,
                "today_forecast": 292000,
            }, "mock data")
        raise AppError(503, "KPI 数据暂未就绪")
