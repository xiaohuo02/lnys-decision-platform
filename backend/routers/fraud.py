# -*- coding: utf-8 -*-
"""backend/routers/fraud.py — 欺诈风控 API（瘦路由）"""
from typing import Any, List
from fastapi import APIRouter, Depends

from backend.dependencies.db import DbSession
from backend.dependencies.redis import RedisClient
from backend.dependencies.agents import get_optional_agent
from backend.schemas.base import ApiResponse
from backend.schemas.fraud_schemas import (
    FraudScoreRequest, FraudScoreResponse, FraudReviewRequest, FraudStats,
)
from backend.services.fraud_service import FraudService

router = APIRouter()


def _svc(
    db:    DbSession,
    redis: RedisClient,
    agent  = get_optional_agent("fraud_agent"),
) -> FraudService:
    return FraudService(db, redis, agent)


@router.get("/stats", summary="今日欺诈拦截统计", response_model=ApiResponse[FraudStats])
async def get_stats(svc: FraudService = Depends(_svc)):
    return await svc.get_stats()


@router.post("/score", summary="实时交易风险评分（规则引擎 + HITL）", response_model=ApiResponse[FraudScoreResponse])
async def score(
    body: FraudScoreRequest,
    svc:  FraudService = Depends(_svc),
):
    return await svc.score(body)


@router.post("/review/{thread_id}", summary="HITL 人工审核高风险交易", response_model=ApiResponse[Any])
async def review(
    thread_id: str,
    body:      FraudReviewRequest,
    svc:       FraudService = Depends(_svc),
):
    return await svc.review(thread_id, body)


@router.get("/pending-reviews", summary="查询待审核列表", response_model=ApiResponse[List[Any]])
async def pending_reviews(svc: FraudService = Depends(_svc)):
    return svc.list_pending()
