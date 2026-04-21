# -*- coding: utf-8 -*-
"""backend/routers/association.py — 关联分析 API（瘦路由）"""
from typing import Any, List
from fastapi import APIRouter, Depends, Query

from backend.dependencies.db import DbSession
from backend.dependencies.redis import RedisClient
from backend.dependencies.agents import get_optional_agent
from backend.schemas.base import ApiResponse
from backend.services.association_service import AssociationService

router = APIRouter()


def _svc(
    db:    DbSession,
    redis: RedisClient,
    agent = get_optional_agent("association_agent"),
) -> AssociationService:
    return AssociationService(db, redis, agent)


@router.get("/rules", summary="Top N 关联规则（按 lift 降序，支持 min_lift 筛选）", response_model=ApiResponse[List[Any]])
async def get_rules(
    top_n:    int   = Query(20,  le=100),
    min_lift: float = Query(1.5, ge=0.0),
    svc: AssociationService = Depends(_svc),
):
    return await svc.get_rules(top_n, min_lift)


@router.get("/graph", summary="关联网络图谱数据（节点+边）", response_model=ApiResponse[Any])
async def get_graph(
    min_lift:  float = Query(1.5, ge=0.0),
    max_nodes: int   = Query(100, le=500),
    svc: AssociationService = Depends(_svc),
):
    return await svc.get_graph(min_lift, max_nodes)


@router.get("/sku/{sku_code}/rules", summary="指定 SKU 参与的所有关联规则", response_model=ApiResponse[List[Any]])
async def get_sku_rules(
    sku_code: str,
    top_n:    int = Query(20, le=50),
    svc: AssociationService = Depends(_svc),
):
    return await svc.get_sku_rules(sku_code, top_n)


@router.get("/recommend/{sku_code}", summary="给定 SKU 返回关联推荐商品（购物篮推荐）", response_model=ApiResponse[List[Any]])
async def recommend(
    sku_code: str,
    top_n:    int = Query(5, le=20),
    svc: AssociationService = Depends(_svc),
):
    return await svc.recommend(sku_code, top_n)
