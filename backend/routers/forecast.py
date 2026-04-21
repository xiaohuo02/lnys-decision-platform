# -*- coding: utf-8 -*-
"""backend/routers/forecast.py — 销售预测 API（瘦路由）"""
from typing import Any
from fastapi import APIRouter, Depends

from backend.dependencies.db import DbSession
from backend.dependencies.redis import RedisClient
from backend.dependencies.agents import get_optional_agent
from backend.schemas.base import ApiResponse
from backend.schemas.forecast_schemas import ForecastPredictRequest, ForecastPredictResponse
from backend.services.forecast_service import ForecastService

router = APIRouter()


def _svc(
    db:    DbSession,
    redis: RedisClient,
    agent = get_optional_agent("forecast_agent"),
) -> ForecastService:
    return ForecastService(db, redis, agent)


@router.get("/summary", summary="最新预测汇总（模型对比 + 近7天）", response_model=ApiResponse[Any])
async def get_summary(svc: ForecastService = Depends(_svc)):
    return await svc.get_summary()


@router.post("/predict", summary="指定 SKU/门店预测（Redis 缓存 TTL=1800s）", response_model=ApiResponse[ForecastPredictResponse])
async def predict(
    body: ForecastPredictRequest,
    svc:  ForecastService = Depends(_svc),
):
    return await svc.predict(body)
