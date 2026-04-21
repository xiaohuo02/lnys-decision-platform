# -*- coding: utf-8 -*-
"""backend/routers/admin/telemetry.py — 遥测与系统治理 API

提供:
  GET  /admin/telemetry/summary       — 聚合摘要（含模型调用、token、错误）
  GET  /admin/telemetry/events        — 最近遥测事件
  GET  /admin/telemetry/counters      — 事件计数
  GET  /admin/telemetry/context       — 上下文治理诊断
  GET  /admin/telemetry/models        — 多模型路由信息
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

router = APIRouter(prefix="/telemetry", tags=["admin-telemetry"])


@router.get("/summary")
async def telemetry_summary(run_id: Optional[str] = Query(None)):
    """聚合摘要"""
    from backend.core.telemetry import telemetry
    s = telemetry.summary(run_id=run_id)
    return {"ok": True, "data": s.model_dump()}


@router.get("/events")
async def telemetry_events(
    limit: int = Query(50, ge=1, le=200),
    event_type: Optional[str] = Query(None),
):
    """最近遥测事件"""
    from backend.core.telemetry import telemetry
    events = telemetry.recent(limit=limit, event_type=event_type)
    return {"ok": True, "data": events, "total": len(events)}


@router.get("/counters")
async def telemetry_counters():
    """事件计数"""
    from backend.core.telemetry import telemetry
    return {"ok": True, "data": telemetry.counters()}


@router.get("/context")
async def context_diagnostics(
    current_tokens: int = Query(0, ge=0),
    thread_id: str = Query("_default"),
):
    """上下文治理诊断"""
    from backend.core.context_monitor import context_monitor
    diag = context_monitor.diagnostics(current_tokens, thread_id)
    return {"ok": True, "data": diag.to_dict()}


@router.get("/models")
async def model_routing_info():
    """多模型路由信息"""
    from backend.core.model_selector import model_selector
    return {"ok": True, "data": model_selector.get_model_info()}
