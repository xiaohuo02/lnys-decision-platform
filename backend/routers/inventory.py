# -*- coding: utf-8 -*-
"""backend/routers/inventory.py — 库存优化 API（瘦路由）"""
from typing import Any, List
from fastapi import APIRouter, Depends, Query

from backend.dependencies.db import DbSession
from backend.dependencies.redis import RedisClient
from backend.dependencies.agents import get_optional_agent
from backend.schemas.base import ApiResponse
from backend.schemas.inventory_schemas import InventoryStatusResponse, InventoryAlertItem, InventoryTrendItem
from backend.services.inventory_service import InventoryService

router = APIRouter()


def _svc(
    db:    DbSession,
    redis: RedisClient,
    agent = get_optional_agent("inventory_agent"),
) -> InventoryService:
    return InventoryService(db, redis, agent)


@router.get("/status", summary="库存健康度汇总（healthy/warning/critical 数量）", response_model=ApiResponse[InventoryStatusResponse])
async def get_inventory_status(svc: InventoryService = Depends(_svc)):
    return await svc.get_status_summary()


@router.get("/alerts", summary="补货预警清单（按紧急程度排序）", response_model=ApiResponse[List[InventoryAlertItem]])
async def get_inventory_alerts(
    level: str = Query("all", description="筛选级别：critical | warning | all"),
    svc: InventoryService = Depends(_svc),
):
    return await svc.get_alerts(level)


@router.get("/abc-xyz", summary="26 SKU 的 ABC-XYZ 9象限分类矩阵", response_model=ApiResponse[Any])
async def get_abc_xyz(svc: InventoryService = Depends(_svc)):
    return await svc.get_abc_xyz()


@router.get("/trend", summary="库存健康度每日趋势（30天）", response_model=ApiResponse[List[InventoryTrendItem]])
async def get_inventory_trend(
    days: int = Query(30, ge=7, le=90),
    svc: InventoryService = Depends(_svc),
):
    return await svc.get_trend(days)
