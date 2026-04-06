# -*- coding: utf-8 -*-
"""backend/schemas/sentiment_schemas.py — 舆情分析 Pydantic 模型"""
from pydantic import BaseModel, Field
from typing import Any, Dict, Optional, List


# ── 单条分析 ──────────────────────────────────────────────────
class SentimentAnalyzeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000,
                      examples=["这个茶叶质量真的很好，下次还会回购！"])


class ReasoningStep(BaseModel):
    step:   str
    detail: str


class CascadeTraceItem(BaseModel):
    tier:       int
    model:      str
    decision:   str
    label:      Optional[str]       = None
    confidence: Optional[float]     = None
    ms:         Optional[int]       = None
    vote_detail: Optional[Dict[str, int]] = None


class EntitySentiment(BaseModel):
    entity:    str
    aspect:    str
    opinion:   str
    sentiment: str = Field(..., pattern="^(正面|负面|中性)$")


class AgentSignal(BaseModel):
    target_agent: str
    signal_type:  str
    entity:       Optional[str] = None
    severity:     str = "medium"
    suggestion:   str = ""


class SentimentAnalyzeResponse(BaseModel):
    text:            str
    label:           str   = Field(..., examples=["正面"])
    confidence:      float = Field(..., ge=0.0, le=1.0)
    model_used:      str   = "bert-chinese"
    topics:          Optional[List[str]]              = None
    reflect_passed:  bool                             = True
    reasoning:       Optional[List[ReasoningStep]]    = None
    key_phrases:     Optional[List[str]]              = None
    aspects:         Optional[Dict[str, str]]         = None
    entity_sentiments: Optional[List[EntitySentiment]] = None
    intent_tags:     Optional[List[str]]              = None
    agent_signals:   Optional[List[AgentSignal]]      = None
    cascade_tier:    Optional[int]                    = None
    cascade_trace:   Optional[List[CascadeTraceItem]] = None
    needs_review:    Optional[bool]                   = None
    kb_id:           Optional[str]                    = None


# ── 舆情概览 ──────────────────────────────────────────────────
class TrendPoint(BaseModel):
    date:      str
    avg_score: float


class SentimentOverviewResponse(BaseModel):
    positive_pct: float
    negative_pct: float
    neutral_pct:  float
    avg_score_7d: float
    trend_30d:    List[TrendPoint]
    alert:        bool = False


# ── LDA 话题 ──────────────────────────────────────────────────
class TopicItem(BaseModel):
    id:       int
    label:    str
    keywords: List[str]


class TopicsResponse(BaseModel):
    k:         int
    coherence: float
    topics:    List[TopicItem]


# ── HITL 审核 ────────────────────────────────────────────────
class SentimentReviewItem(BaseModel):
    id:          str
    text:        str
    auto_label:  str
    confidence:  float
    model_used:  str
    created_at:  str
    status:      str = "pending"


class SentimentReviewAction(BaseModel):
    review_id:    str
    human_label:  str = Field(..., pattern="^(正面|负面|中性)$")


# ── 知识库查询 ────────────────────────────────────────
class KBSearchRequest(BaseModel):
    query:  str = Field(..., min_length=1, max_length=500)
    top_k:  int = Field(5, ge=1, le=50)
    label:  Optional[str] = Field(None, pattern="^(正面|负面|中性)$")


