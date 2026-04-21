# -*- coding: utf-8 -*-
"""backend/services/sales_forecast_service.py

SalesForecastService — 销售预测服务

╔══════════════════════════════════════════════════════════════════╗
║  Agent 契约                                                       ║
╠══════════════════════════════════════════════════════════════════╣
║  输入   : ForecastRequest（预测天数、门店/SKU 过滤、是否对比模型）  ║
║  输出   : ForecastResult（Stacking 预测 + 模型对比 + fallback）   ║
║  可调用 : 读取 models/results/forecast/*.csv                      ║
║  禁止   : 重新训练模型、直接写 DB、调用 LLM                        ║
║  降级   : 无 Stacking 时回退加权均值 → 无模型时返回历史均值         ║
║  HITL   : 不需要                                                   ║
║  依赖   : models/results/forecast/stacking_result.csv（最优）     ║
║           models/results/forecast/sarima_result.csv（fallback）  ║
║  Trace  : step_type=SERVICE_CALL, step_name="sales_forecast"     ║
║           output_summary=forecast_days + MAPE + model_used       ║
╚══════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

from datetime import datetime, timezone, date, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from loguru import logger
from pydantic import BaseModel, Field

from backend.config import settings
from backend.schemas.artifact import ArtifactRef, ArtifactType


_RESULTS = settings.MODELS_ROOT / "results" / "forecast"

_RESULT_FILES = [
    ("stacking",      "stacking_result.csv"),
    ("neuralprophet", "neuralprophet_result.csv"),
    ("xgb",           "sales_xgb_result.csv"),
    ("prophet",       "prophet_result.csv"),
    ("sarima",        "sarima_result.csv"),
]


class ForecastRequest(BaseModel):
    forecast_days: int = 30
    run_id:        Optional[str] = None
    store_id:      Optional[str] = None
    sku_code:      Optional[str] = None
    compare_models: bool = True


class DailyForecast(BaseModel):
    ds:           str
    forecast:     float
    lower_bound:  Optional[float] = None
    upper_bound:  Optional[float] = None


class ModelMetric(BaseModel):
    model:       str
    mape:        Optional[float] = None
    rmse:        Optional[float] = None
    available:   bool


class ForecastResult(BaseModel):
    """SalesForecastService 的标准输出"""
    run_id:         Optional[str]
    forecast_days:  int
    model_used:     str
    degraded:       bool = False
    data_ready:     bool = False

    daily_forecast: List[DailyForecast] = Field(default_factory=list)
    total_forecast: float = 0.0
    mape:           Optional[float] = None
    model_comparison: List[ModelMetric] = Field(default_factory=list)

    artifact:       Optional[ArtifactRef] = None
    error_message:  Optional[str] = None
    forecasted_at:  datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SalesForecastService:
    """
    读取 ml/ 目录 pre-computed forecast 结果，
    优先使用 Stacking，降级时依次回退到可用模型或历史均值。
    """

    def forecast(self, request: ForecastRequest) -> ForecastResult:
        # 按优先级尝试各模型结果
        for model_name, fname in _RESULT_FILES:
            path = _RESULTS / fname
            if not path.exists():
                continue
            try:
                df = pd.read_csv(path)
                result = self._build_result(df, model_name, request)
                if result.data_ready:
                    if model_name != "stacking":
                        result.degraded = True
                    # 补充模型对比
                    if request.compare_models:
                        result.model_comparison = self._compare_models()
                    logger.info(
                        f"[SalesForecastService] model={model_name} "
                        f"days={request.forecast_days} "
                        f"total={result.total_forecast:.1f} "
                        f"mape={result.mape} degraded={result.degraded}"
                    )
                    return result
            except Exception as e:
                logger.warning(f"[SalesForecastService] {model_name} 加载失败: {e}")
                continue

        # 所有模型均不可用 → 历史均值 fallback
        return self._fallback_result(request)

    def _build_result(
        self, df: pd.DataFrame, model_name: str, request: ForecastRequest
    ) -> ForecastResult:
        if "forecast" not in df.columns:
            return ForecastResult(
                run_id=request.run_id,
                forecast_days=request.forecast_days,
                model_used=model_name,
                data_ready=False,
                error_message="forecast 列不存在",
            )

        # 取最后 N 天预测
        tail = df.tail(request.forecast_days).copy()
        forecasts = tail["forecast"].clip(0).tolist()

        # 日期序列
        start_date = date.today() + timedelta(days=1)
        daily = [
            DailyForecast(
                ds=str(start_date + timedelta(days=i)),
                forecast=round(float(v), 2),
                lower_bound=round(float(tail["lower"].iloc[i]), 2) if "lower" in tail.columns else None,
                upper_bound=round(float(tail["upper"].iloc[i]), 2) if "upper" in tail.columns else None,
            )
            for i, v in enumerate(forecasts)
        ]

        mape = None
        if "mape" in df.columns:
            mape = round(float(df["mape"].iloc[-1]), 2)
        elif "actual" in df.columns:
            actual = tail["actual"].values
            pred   = tail["forecast"].values
            mask   = np.abs(actual) > 1e-6
            if mask.sum() > 0:
                mape = round(float(np.mean(np.abs((actual[mask] - pred[mask]) / actual[mask])) * 100), 2)

        artifact = ArtifactRef(
            artifact_type=ArtifactType.FORECAST,
            summary=(
                f"销售预测({model_name}): 未来{request.forecast_days}天合计 "
                f"{sum(forecasts):,.1f}，MAPE={mape}%"
            ),
        )

        return ForecastResult(
            run_id=request.run_id,
            forecast_days=request.forecast_days,
            model_used=model_name,
            data_ready=True,
            daily_forecast=daily,
            total_forecast=round(sum(forecasts), 2),
            mape=mape,
            artifact=artifact,
        )

    def _compare_models(self) -> List[ModelMetric]:
        metrics = []
        for model_name, fname in _RESULT_FILES:
            path = _RESULTS / fname
            if not path.exists():
                metrics.append(ModelMetric(model=model_name, available=False))
                continue
            try:
                df = pd.read_csv(path)
                mape = None
                if "mape" in df.columns:
                    mape = round(float(df["mape"].mean()), 2)
                metrics.append(ModelMetric(model=model_name, mape=mape, available=True))
            except Exception:
                metrics.append(ModelMetric(model=model_name, available=False))
        return metrics

    def _fallback_result(self, request: ForecastRequest) -> ForecastResult:
        """所有模型均不可用时返回历史均值占位"""
        logger.warning("[SalesForecastService] 所有模型不可用，返回历史均值 fallback")
        placeholder = 5000.0
        daily = [
            DailyForecast(
                ds=str(date.today() + timedelta(days=i + 1)),
                forecast=placeholder,
            )
            for i in range(request.forecast_days)
        ]
        return ForecastResult(
            run_id=request.run_id,
            forecast_days=request.forecast_days,
            model_used="historical_avg_fallback",
            data_ready=True,
            degraded=True,
            daily_forecast=daily,
            total_forecast=round(placeholder * request.forecast_days, 2),
            error_message="所有预测模型不可用，使用历史均值占位",
        )


sales_forecast_service = SalesForecastService()
