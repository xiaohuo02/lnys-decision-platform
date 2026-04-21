# -*- coding: utf-8 -*-
"""backend/routers/dashboard.py — 业务总览 KPI API（瘦路由）"""
from typing import Any
from fastapi import APIRouter, Depends

from backend.dependencies.db import DbSession
from backend.dependencies.redis import RedisClient
from backend.schemas.base import ApiResponse
from backend.services.dashboard_service import DashboardService

router = APIRouter()


def _svc(db: DbSession, redis: RedisClient) -> DashboardService:
    return DashboardService(db, redis)


@router.get("/kpis", summary="业务总览 KPI（订单数、活跃客户等）", response_model=ApiResponse[Any])
async def get_kpis(svc: DashboardService = Depends(_svc)):
    return await svc.get_kpis()
