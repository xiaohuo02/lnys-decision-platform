# -*- coding: utf-8 -*-
"""backend/schemas/artifact.py — Artifact 引用与元数据 schema"""
from __future__ import annotations
import uuid
from enum import Enum
from typing import Any, Dict, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ArtifactType(str, Enum):
    CUSTOMER_INSIGHT  = "customer_insight"
    FORECAST          = "forecast"
    FRAUD_SCORE       = "fraud_score"
    SENTIMENT         = "sentiment"
    INVENTORY         = "inventory"
    ASSOCIATION       = "association"
    REPORT            = "report"
    DATA_QUALITY      = "data_quality"
    EXECUTIVE_SUMMARY = "executive_summary"
    REVIEW_SUMMARY    = "review_summary"
    RAW_DATA          = "raw_data"


class ArtifactRef(BaseModel):
    """轻量引用，用于在 Agent/workflow 间传递，不含正文"""
    artifact_id:   uuid.UUID = Field(default_factory=uuid.uuid4)
    artifact_type: ArtifactType
    run_id:        Optional[uuid.UUID] = None
    summary:       str = ""
    content_type:  str = "application/json"

    model_config = ConfigDict(use_enum_values=True)


class ArtifactMeta(BaseModel):
    """完整 artifact 元数据（对应 DB artifacts 表）"""
    artifact_id:   uuid.UUID = Field(default_factory=uuid.uuid4)
    artifact_type: ArtifactType
    artifact_uri:  str                              # 文件路径或存储 key
    content_type:  str = "application/json"
    summary:       str = ""
    metadata:      Dict[str, Any] = Field(default_factory=dict)
    run_id:        Optional[uuid.UUID] = None
    step_id:       Optional[uuid.UUID] = None
    created_at:    datetime = Field(default_factory=_utcnow)

    model_config = ConfigDict(use_enum_values=True)


# ── mock artifact 工厂（供早期开发与测试使用）─────────────────────

def make_mock_customer_artifact(run_id: Optional[uuid.UUID] = None) -> ArtifactRef:
    return ArtifactRef(
        artifact_type=ArtifactType.CUSTOMER_INSIGHT,
        run_id=run_id,
        summary="高流失客户 Top10，RFM 分布集中在低频高价值群",
    )


def make_mock_forecast_artifact(run_id: Optional[uuid.UUID] = None) -> ArtifactRef:
    return ArtifactRef(
        artifact_type=ArtifactType.FORECAST,
        run_id=run_id,
        summary="未来 30 天销售预测，Stacking 模型，环比下降 3.2%",
    )


def make_mock_sentiment_artifact(run_id: Optional[uuid.UUID] = None) -> ArtifactRef:
    return ArtifactRef(
        artifact_type=ArtifactType.SENTIMENT,
        run_id=run_id,
        summary="近 7 天负面评价占比 12.3%，主题：物流延误、品质投诉",
    )


def make_mock_fraud_artifact(run_id: Optional[uuid.UUID] = None) -> ArtifactRef:
    return ArtifactRef(
        artifact_type=ArtifactType.FRAUD_SCORE,
        run_id=run_id,
        summary="高风险交易 3 笔，待人工审核；中风险 17 笔，已自动标记",
    )
