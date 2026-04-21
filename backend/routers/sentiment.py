# -*- coding: utf-8 -*-
"""backend/routers/sentiment.py — 舆情分析 API（瘦路由）"""
from typing import Any
from fastapi import APIRouter, Depends

from backend.dependencies.db import DbSession
from backend.dependencies.redis import RedisClient
from backend.dependencies.agents import get_optional_agent
from backend.schemas.base import ApiResponse
from backend.core.response import ok
from backend.schemas.sentiment_schemas import (
    SentimentAnalyzeRequest, SentimentAnalyzeResponse,
    SentimentOverviewResponse, SentimentReviewAction,
    KBSearchRequest,
)
from backend.services.sentiment_service import SentimentService

router = APIRouter()


def _svc(
    db:    DbSession,
    redis: RedisClient,
    agent = get_optional_agent("sentiment_agent"),
) -> SentimentService:
    return SentimentService(db, redis, agent)


@router.get("/overview", summary="正/负/中性占比 + 近30天情感趋势", response_model=ApiResponse[SentimentOverviewResponse])
async def get_sentiment_overview(svc: SentimentService = Depends(_svc)):
    return await svc.get_overview()


@router.get("/topics", summary="LDA K=3 话题 + 关键词", response_model=ApiResponse[Any])
async def get_topics(svc: SentimentService = Depends(_svc)):
    return await svc.get_topics()


@router.post("/analyze", summary="Cascade 实时情感推理（BERT→LLM CoT→Self-Consistency→HITL）", response_model=ApiResponse[SentimentAnalyzeResponse])
async def analyze_sentiment(
    body: SentimentAnalyzeRequest,
    svc:  SentimentService = Depends(_svc),
):
    return await svc.analyze(body)


@router.get("/reviews", summary="HITL 待审核队列")
async def get_review_queue(svc: SentimentService = Depends(_svc)):
    return await svc.get_review_queue()


@router.post("/reviews/resolve", summary="HITL 人工裁决")
async def resolve_review(
    body: SentimentReviewAction,
    svc:  SentimentService = Depends(_svc),
):
    return await svc.resolve_review(body.review_id, body.human_label)


# ── 知识库端点 ─────────────────────────────────────────────

@router.get("/kb/stats", summary="舆情知识库统计")
async def get_kb_stats():
    from backend.services.sentiment_kb_service import SentimentKBService
    svc = SentimentKBService.get_instance()
    return ok(await svc.get_stats())


@router.post("/kb/search", summary="语义检索相似评论")
async def search_similar(body: KBSearchRequest):
    from backend.services.sentiment_kb_service import SentimentKBService
    svc = SentimentKBService.get_instance()
    results = await svc.search_similar(body.query, body.top_k, body.label)
    return ok(results)


@router.get("/kb/entity/{entity}", summary="按实体检索情报")
async def search_entity(entity: str, days: int = 7, top_k: int = 20):
    from backend.services.sentiment_kb_service import SentimentKBService
    svc = SentimentKBService.get_instance()
    results = await svc.search_by_entity(entity, days, top_k)
    return ok(results)
