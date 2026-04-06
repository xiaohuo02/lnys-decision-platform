# -*- coding: utf-8 -*-
"""backend/schemas/service_result.py — 统一 Service 调用协议的核心数据结构

本文件定义了 Agent/Workflow 调用 Service 时的：
- ServiceCallContext: 每次调用的运行时上下文
- ServiceMetrics:     性能与成本指标
- ServiceResult:      统一返回结构

所有 Service 的公开方法必须返回 ServiceResult。
Agent 层通过 ServiceProtocol 调用 Service 时会自动注入 context。
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, Optional
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── 性能与成本指标 ────────────────────────────────────────────────

class ServiceMetrics(BaseModel):
    """单次 Service 调用的性能指标"""
    latency_ms:   int   = 0
    tokens_used:  int   = 0       # 如涉及 LLM 调用
    cost_amount:  float = 0.0     # 单位：元
    model_used:   Optional[str] = None


# ── 调用上下文 ────────────────────────────────────────────────────

class ServiceCallContext(BaseModel):
    """ServiceProtocol 注入给每次调用的运行时上下文"""
    run_id:          str = Field(default_factory=lambda: str(uuid.uuid4()))
    step_id:         str = Field(default_factory=lambda: str(uuid.uuid4()))
    caller:          str = ""              # agent_name / node_name
    permission_mode: str = "auto"          # auto | check | hitl
    trace_enabled:   bool = True
    timestamp:       datetime = Field(default_factory=_utcnow)


# ── 统一返回结构 ──────────────────────────────────────────────────

class ServiceResult(BaseModel):
    """
    所有 Service 方法的统一返回结构。

    规则:
      1. success=True  时 data 必须非空，error 为 None
      2. success=False 时 error 必须非空
      3. summary 必须是有意义的中文自然语言摘要（供 InsightComposerAgent 使用）
      4. 如果使用了降级逻辑，fallback_used=True 且 summary 中说明
      5. artifact_ref 为该次调用产出的 artifact ID（如有）
      6. metrics 始终填写，至少有 latency_ms
    """
    success:       bool
    data:          Optional[Dict[str, Any]] = None
    artifact_ref:  Optional[str]  = None   # artifact_id (如产出了 artifact)
    summary:       Optional[str]  = None   # 中文自然语言摘要
    error:         Optional[str]  = None   # 错误信息
    fallback_used: bool           = False  # 是否使用了降级方案
    metrics:       ServiceMetrics = Field(default_factory=ServiceMetrics)

    model_config = ConfigDict(json_schema_extra={
        "examples": [
            {
                "success": True,
                "data": {"total_records": 15230, "quality_score": 87.5},
                "summary": "数据准备完成：共处理 15,230 条记录，数据质量评分 87.5/100。",
                "metrics": {"latency_ms": 3200, "tokens_used": 0, "cost_amount": 0.0},
            },
            {
                "success": False,
                "error": "模型文件缺失: customer_rfm_model.pkl",
                "metrics": {"latency_ms": 50},
            },
        ]
    })


# ── 工具函数：快速构造常见结果 ────────────────────────────────────

def service_ok(
    data: Dict[str, Any],
    summary: str,
    artifact_ref: Optional[str] = None,
    metrics: Optional[ServiceMetrics] = None,
) -> ServiceResult:
    """快捷创建成功结果"""
    return ServiceResult(
        success=True,
        data=data,
        summary=summary,
        artifact_ref=artifact_ref,
        metrics=metrics or ServiceMetrics(),
    )


def service_error(
    error: str,
    metrics: Optional[ServiceMetrics] = None,
) -> ServiceResult:
    """快捷创建失败结果"""
    return ServiceResult(
        success=False,
        error=error,
        metrics=metrics or ServiceMetrics(),
    )


def service_degraded(
    data: Dict[str, Any],
    summary: str,
    artifact_ref: Optional[str] = None,
    metrics: Optional[ServiceMetrics] = None,
) -> ServiceResult:
    """快捷创建降级结果"""
    return ServiceResult(
        success=True,
        data=data,
        summary=summary,
        artifact_ref=artifact_ref,
        fallback_used=True,
        metrics=metrics or ServiceMetrics(),
    )
