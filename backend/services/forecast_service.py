# -*- coding: utf-8 -*-
"""backend/services/forecast_service.py — 销售预测业务逻辑"""
import json
from datetime import date, timedelta
from typing import Any, Optional

import pandas as pd
import redis.asyncio as aioredis
from sqlalchemy.orm import Session
from loguru import logger

from backend.config import settings
from backend.core.response import ok, cached, degraded
from backend.core.exceptions import AppError
from backend.agents.gateway import AgentGateway
from backend.repositories.analysis_results_repo import AnalysisResultsRepo
from backend.schemas.forecast_schemas import ForecastPredictRequest

_RESULTS = settings.MODELS_ROOT / "results" / "forecast"

_MODEL_COMPARISON = [
    {"model": "SARIMA",        "mape": 27.8, "mae": 773755},
    {"model": "Holt-Winters",  "mape": 26.5, "mae": 661845},
    {"model": "GRU",           "mape": 36.7, "mae": 1054283},
    {"model": "XGBoost",       "mape": 32.7, "mae": 1019916},
    {"model": "Stacking★",     "mape": 19.5, "mae": None},
]


class ForecastService:
    def __init__(self, db: Session, redis: aioredis.Redis, agent: Any = None):
        self.db    = db
        self.redis = redis
        self.agent = agent
        self._repo = AnalysisResultsRepo(db)

    # ── 缓存读写帮助方法 ────────────────────────────────────────

    async def _read_result(self, redis_key: str, db_module: str) -> Optional[dict]:
        """Redis 热缓存 → DB 持久化层 → None"""
        try:
            val = await self.redis.get(redis_key)
            if val:
                return json.loads(val)
        except Exception as e:
            logger.warning(f"[forecast_svc] redis get {redis_key}: {e}")
        result = self._repo.get_latest(db_module)
        if result is not None:
            try:
                await self.redis.setex(redis_key, 3600, json.dumps(result, ensure_ascii=False))
            except Exception:
                pass
        return result

    async def _set_result(self, redis_key: str, db_module: str, data: dict) -> None:
        """CSV 命中后回写 Redis + DB"""
        self._repo.save(db_module, data)
        try:
            await self.redis.setex(redis_key, 3600, json.dumps(data, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"[forecast_svc] redis setex {redis_key}: {e}")

    async def get_summary(self) -> dict:
        today = date.today()

        # 1. Redis → DB（带日期新鲜度检查）
        hit = await self._read_result("forecast:summary", "forecast_summary")
        if hit is not None:
            # 如果缓存的 generated_at 不是今天，视为过期，重新从 CSV 解析
            if hit.get("generated_at") == str(today):
                return ok(hit)
            logger.info("[forecast_svc] cached summary stale, re-parsing CSV")

        # 2. CSV
        path = _RESULTS / "stacking_result.csv"
        if path.exists():
            try:
                df = pd.read_csv(path)
                # 过滤 actual=0 的异常行（周休/数据缺失标记）
                if "actual" in df.columns:
                    df_clean = df[df["actual"] > 0]
                else:
                    df_clean = df
                # 取最后 7 条有效数据构造 forecast_7d
                tail7 = df_clean.tail(7)
                forecast_7d = []
                for idx, row in tail7.iterrows():
                    pred = float(row.get("ensemble", 0))
                    forecast_7d.append({
                        "date":      str(today - timedelta(days=len(tail7) - 1 - len(forecast_7d))),
                        "predicted": round(pred, 2),
                        "actual":    round(float(row.get("actual", 0)), 2),
                        "lower":     round(pred * 0.9, 2),
                        "upper":     round(pred * 1.1, 2),
                    })
                data = {
                    "generated_at":      str(today),
                    "model":             "Stacking(RidgeCV)",
                    "last_30d_actual":   round(float(df_clean["actual"].tail(30).sum()), 2)   if "actual"   in df_clean.columns else 0,
                    "last_30d_forecast": round(float(df_clean["ensemble"].tail(30).sum()), 2) if "ensemble" in df_clean.columns else 0,
                    "mape_stacking":     19.5,
                    "model_comparison":  _MODEL_COMPARISON,
                    "forecast_7d":       forecast_7d,
                }
                await self._set_result("forecast:summary", "forecast_summary", data)
                return ok(data)
            except Exception as e:
                logger.warning(f"[forecast_svc] summary csv error: {e}")

        # 3. Mock
        if settings.ENABLE_MOCK_DATA:
            return degraded({
                "generated_at":     str(today),
                "model":            "Stacking(RidgeCV)",
                "last_30d_actual":  78453840.0,
                "last_30d_forecast": 78453840.0,
                "mape_stacking":    19.5,
                "model_comparison": _MODEL_COMPARISON,
                "forecast_7d": [
                    {
                        "date":      str(today - timedelta(days=7 - i)),
                        "predicted": round(2800000 + i * 120000, 2),
                        "actual":    round(2600000 + i * 150000, 2),
                        "lower":     round(2520000 + i * 108000, 2),
                        "upper":     round(3080000 + i * 132000, 2),
                    }
                    for i in range(1, 8)
                ],
            }, "mock data")
        raise AppError(503, "预测汇总数据暂未就绪")

    async def predict(self, body: ForecastPredictRequest) -> dict:
        cache_key = f"forecast:{body.sku_code}:{body.store_id}:{body.days}"
        try:
            cached_val = await self.redis.get(cache_key)
            if cached_val:
                return cached(json.loads(cached_val))
        except Exception as e:
            logger.warning(f"[forecast_svc] redis get failed: {e}")

        result = await AgentGateway.call(
            self.agent,
            {"mode": "predict_single", "sku_code": body.sku_code,
             "store_id": body.store_id, "days": body.days},
            agent_name="forecast_agent",
        )

        if result is None:
            if not settings.ENABLE_MOCK_DATA:
                raise AppError(503, "预测服务暂不可用")
            today = date.today()
            result = {
                "sku_code":   body.sku_code,
                "store_id":   body.store_id,
                "model_used": "stacking",
                "forecast": [
                    {
                        "date":      str(today + timedelta(days=i)),
                        "predicted": round(58000 - i * 80, 2),
                        "lower":     round(52200 - i * 72, 2),
                        "upper":     round(63800 - i * 88, 2),
                    }
                    for i in range(1, body.days + 1)
                ],
            }
            return degraded(result, "mock data")

        try:
            await self.redis.setex(cache_key, 1800, json.dumps(result, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"[forecast_svc] redis setex failed: {e}")

        return ok(result)
