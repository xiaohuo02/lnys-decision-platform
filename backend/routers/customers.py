# -*- coding: utf-8 -*-
"""backend/routers/customers.py — 客户分析 API（瘦路由）

路由职责：参数校验 → 注入 CustomerService → 返回结果。
业务逻辑（CSV / mock / 缓存 / Agent 调用）全部在 CustomerService 中。
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query

from backend.dependencies.db import DbSession
from backend.dependencies.redis import RedisClient
from backend.dependencies.agents import get_optional_agent
from backend.schemas.base import ApiResponse, PaginatedData
from backend.schemas.customer_schemas import (
    ChurnPredictRequest, ChurnPredictResponse,
    RFMRecord, SegmentsResponse, CLVRecord,
    ChurnRiskListData,
)
from backend.services.customer_service import CustomerService

router = APIRouter()


def _svc(
    db:    DbSession,
    redis: RedisClient,
    agent = get_optional_agent("customer_agent"),
) -> CustomerService:
    return CustomerService(db, redis, agent)


@router.get("/rfm", summary="RFM 客户价值数据", response_model=ApiResponse[PaginatedData[RFMRecord]])
async def get_rfm(
    member_level: Optional[str] = Query(None, description="普通/银卡/金卡/钻石"),
    page:         int            = Query(1,   ge=1),
    page_size:    int            = Query(50,  le=200),
    svc: CustomerService = Depends(_svc),
):
    return await svc.get_rfm(member_level, page, page_size)


@router.get("/segments", summary="4 类客群统计", response_model=ApiResponse[SegmentsResponse])
async def get_segments(svc: CustomerService = Depends(_svc)):
    return await svc.get_segments()


@router.get("/clv", summary="CLV 排行榜", response_model=ApiResponse[List[CLVRecord]])
async def get_clv(
    top_n: int = Query(50, le=500),
    svc: CustomerService = Depends(_svc),
):
    return await svc.get_clv(top_n)


@router.get("/churn-risk", summary="高流失风险名单", response_model=ApiResponse[ChurnRiskListData])
async def get_churn_risk(
    threshold: float = Query(0.7, ge=0.0, le=1.0),
    top_n:     int   = Query(50,  le=500),
    svc: CustomerService = Depends(_svc),
):
    return await svc.get_churn_risk(threshold, top_n)


@router.post("/predict-churn", summary="实时流失预测（Redis 缓存 TTL=3600s）", response_model=ApiResponse[ChurnPredictResponse])
async def predict_churn(
    body: ChurnPredictRequest,
    svc:  CustomerService = Depends(_svc),
):
    return await svc.predict_churn(body)
