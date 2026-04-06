# -*- coding: utf-8 -*-
"""backend/core/telemetry.py — 统一遥测事件系统

设计来源: Aco/Forge 跨切面 3 (统一可观测性)
核心原则: 所有组件不直接写 trace，通过统一接口发射事件

事件类型:
    RUN_STARTED / RUN_COMPLETED / RUN_FAILED
    MODEL_REQUESTED / MODEL_COMPLETED / MODEL_FAILED
    TOOL_EXECUTED / SKILL_EXECUTED
    HOOK_FIRED
    COMPACT_TRIGGERED / COMPACT_COMPLETED
    ERROR_CLASSIFIED
    CONTEXT_EVALUATED
    WORKFLOW_NODE_STARTED / WORKFLOW_NODE_COMPLETED
    WORKFLOW_PARALLEL_STARTED / WORKFLOW_PARALLEL_COMPLETED

用法:
    from backend.core.telemetry import telemetry, TelemetryEventType

    telemetry.emit(TelemetryEventType.MODEL_REQUESTED, {
        "model": "qwen3.5-plus", "role": "routing", "tokens_in": 500,
    }, run_id="xxx", component="CopilotEngine")
"""
from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict, deque
from enum import Enum
from typing import Any, Callable, Deque, Dict, List, Optional

from loguru import logger
from pydantic import BaseModel, Field


class TelemetryEventType(str, Enum):
    """遥测事件类型枚举"""
    # Run lifecycle
    RUN_STARTED = "run_started"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    # Model calls
    MODEL_REQUESTED = "model_requested"
    MODEL_COMPLETED = "model_completed"
    MODEL_FAILED = "model_failed"
    # Tool / Skill
    TOOL_EXECUTED = "tool_executed"
    SKILL_EXECUTED = "skill_executed"
    # Hook
    HOOK_FIRED = "hook_fired"
    # Context management
    COMPACT_TRIGGERED = "compact_triggered"
    COMPACT_COMPLETED = "compact_completed"
    CONTEXT_EVALUATED = "context_evaluated"
    # Error
    ERROR_CLASSIFIED = "error_classified"
    # Workflow
    WORKFLOW_NODE_STARTED = "workflow_node_started"
    WORKFLOW_NODE_COMPLETED = "workflow_node_completed"
    WORKFLOW_PARALLEL_STARTED = "workflow_parallel_started"
    WORKFLOW_PARALLEL_COMPLETED = "workflow_parallel_completed"
    # Security
    SECURITY_CHECK_PASSED = "security_check_passed"
    SECURITY_CHECK_BLOCKED = "security_check_blocked"
    PII_DETECTED = "pii_detected"
    # Memory
    MEMORY_RECALLED = "memory_recalled"
    MEMORY_WRITTEN = "memory_written"
    # Prompt (R6-4)
    PROMPT_USED = "prompt_used"
    # Eval / Policy (R6-5)
    EVAL_VERDICT = "eval_verdict"
    POLICY_SUGGESTED = "policy_suggested"
    POLICY_APPLIED = "policy_applied"
    POLICY_ROLLED_BACK = "policy_rolled_back"


class TelemetryEvent(BaseModel):
    """单条遥测事件"""
    type: str
    timestamp: float = Field(default_factory=time.time)
    run_id: str = ""
    thread_id: str = ""
    component: str = ""
    data: Dict[str, Any] = Field(default_factory=dict)


class TelemetrySummary(BaseModel):
    """遥测聚合摘要（供前端展示）"""
    total_events: int = 0
    model_calls: int = 0
    model_tokens_in: int = 0
    model_tokens_out: int = 0
    model_latency_ms: int = 0
    skill_calls: int = 0
    compactions: int = 0
    errors: int = 0
    hook_fires: int = 0
    workflow_nodes: int = 0
    duration_ms: int = 0
    # per-model breakdown
    model_breakdown: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    # per-component breakdown
    component_breakdown: Dict[str, int] = Field(default_factory=dict)
    # security
    security_checks: int = 0
    security_blocks: int = 0
    pii_detections: int = 0
    security_hits: List[Dict[str, Any]] = Field(default_factory=list)
    # memory
    memory_recalls: int = 0
    memory_writes: int = 0
    memory_layers: Dict[str, int] = Field(default_factory=dict)


# 事件监听器类型
TelemetryListener = Callable[[TelemetryEvent], None]


class Telemetry:
    """统一遥测系统。

    职责:
    - 发射事件
    - 内存 ring buffer 保留最近 N 条（单 worker，快速）
    - 可选 Redis Stream 归档（多 worker 共享，XADD fire-and-forget）
    - 聚合计算 summary
    - 支持外部 listener (写 DB / 推 SSE)

    跨 worker 查询:
        telemetry.configure(redis=redis_client)  # lifespan 初始化
        events = await telemetry.arecent_from_redis(limit=100)
    """

    MAX_EVENTS = 2000           # 内存中保留最近 N 条
    DEFAULT_STREAM_MAXLEN = 10000  # Redis stream 近似最大长度

    def __init__(self):
        self._events: Deque[TelemetryEvent] = deque(maxlen=self.MAX_EVENTS)
        self._listeners: List[TelemetryListener] = []
        self._counters: Dict[str, int] = defaultdict(int)
        # Redis stream 可选（多 worker 共享）
        self._redis: Any = None
        self._stream_key: str = "lnys:telemetry"
        self._stream_maxlen: int = self.DEFAULT_STREAM_MAXLEN
        # 后台 task 引用集合（避免 GC 取消 fire-and-forget XADD）
        self._bg_tasks: "set[asyncio.Task]" = set()

    def configure(
        self,
        redis: Any = None,
        stream_key: Optional[str] = None,
        stream_maxlen: Optional[int] = None,
    ) -> None:
        """配置 Redis 归档通道。应在 lifespan 启动时调一次。

        Args:
            redis:         redis.asyncio.Redis 客户端；None 则关闭 Redis 归档
            stream_key:    Redis Stream 的 key，默认 lnys:telemetry
            stream_maxlen: 流近似最大长度（XTRIM MAXLEN ~ N），默认 10000
        """
        self._redis = redis
        if stream_key:
            self._stream_key = stream_key
        if stream_maxlen is not None:
            self._stream_maxlen = stream_maxlen
        logger.info(
            f"[Telemetry] Redis stream archiving "
            f"{'enabled' if redis else 'disabled'} "
            f"key={self._stream_key} maxlen={self._stream_maxlen}"
        )

    def emit(
        self,
        event_type: TelemetryEventType,
        data: Optional[Dict[str, Any]] = None,
        run_id: str = "",
        thread_id: str = "",
        component: str = "",
    ) -> TelemetryEvent:
        """发射一条遥测事件。

        - 写入本 worker 的内存 ring buffer（同步，热路径）
        - 触发 listener
        - 若已 configure(redis=...)，同时 fire-and-forget 写 Redis Stream
        """
        event = TelemetryEvent(
            type=event_type.value,
            run_id=run_id,
            thread_id=thread_id,
            component=component,
            data=data or {},
        )
        self._events.append(event)
        self._counters[event_type.value] += 1

        # 通知 listeners
        for listener in self._listeners:
            try:
                listener(event)
            except Exception as e:
                logger.debug(f"[Telemetry] listener error: {e}")

        # Redis 归档：fire-and-forget（仅在有 running loop 时）
        self._try_write_redis(event)

        return event

    def _try_write_redis(self, event: TelemetryEvent) -> None:
        """best-effort 把事件 XADD 到 Redis Stream，不阻塞 emit"""
        if self._redis is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # 同步调用场景，跳过 Redis 归档

        async def _xadd() -> None:
            try:
                await self._redis.xadd(
                    self._stream_key,
                    {"data": event.model_dump_json()},
                    maxlen=self._stream_maxlen,
                    approximate=True,
                )
            except Exception as e:
                logger.debug(f"[Telemetry] xadd failed: {e}")

        task = loop.create_task(_xadd())
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    async def arecent_from_redis(
        self,
        limit: int = 100,
        event_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """从 Redis Stream 读取最近事件（跨 worker）。

        Args:
            limit:      最多返回条数
            event_type: 按 type 过滤（Python 侧过滤，精确）

        Returns:
            list of event dict；Redis 未配置或读取失败时返回 []
        """
        if self._redis is None:
            return []
        try:
            # XREVRANGE 从新到旧
            rows = await self._redis.xrevrange(
                self._stream_key, max="+", min="-", count=limit * 3 if event_type else limit,
            )
        except Exception as e:
            logger.debug(f"[Telemetry] xrevrange failed: {e}")
            return []

        out: List[Dict[str, Any]] = []
        for _stream_id, fields in rows or []:
            try:
                payload = fields.get("data") if isinstance(fields, dict) else None
                if not payload:
                    continue
                evt = json.loads(payload)
                if event_type and evt.get("type") != event_type:
                    continue
                out.append(evt)
                if len(out) >= limit:
                    break
            except Exception:
                continue
        # 恢复旧→新顺序以匹配 recent() 约定
        out.reverse()
        return out

    def add_listener(self, listener: TelemetryListener) -> None:
        """注册事件监听器。"""
        self._listeners.append(listener)

    def remove_listener(self, listener: TelemetryListener) -> None:
        """移除事件监听器。"""
        self._listeners = [l for l in self._listeners if l is not listener]

    def recent(self, limit: int = 50, event_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取最近事件（供 API 返回）。"""
        events = list(self._events)
        if event_type:
            events = [e for e in events if e.type == event_type]
        return [e.model_dump() for e in events[-limit:]]

    def summary(self, run_id: Optional[str] = None) -> TelemetrySummary:
        """聚合计算摘要。"""
        events = list(self._events)
        if run_id:
            events = [e for e in events if e.run_id == run_id]

        if not events:
            return TelemetrySummary()

        s = TelemetrySummary(total_events=len(events))
        model_breakdown: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"calls": 0, "tokens_in": 0, "tokens_out": 0, "latency_ms": 0}
        )
        component_breakdown: Dict[str, int] = defaultdict(int)
        first_ts = events[0].timestamp
        last_ts = events[-1].timestamp

        for e in events:
            if e.component:
                component_breakdown[e.component] += 1

            if e.type == TelemetryEventType.MODEL_COMPLETED.value:
                s.model_calls += 1
                t_in = e.data.get("tokens_in", 0)
                t_out = e.data.get("tokens_out", 0)
                lat = e.data.get("latency_ms", 0)
                s.model_tokens_in += t_in
                s.model_tokens_out += t_out
                s.model_latency_ms += lat
                model_name = e.data.get("model", "unknown")
                model_breakdown[model_name]["calls"] += 1
                model_breakdown[model_name]["tokens_in"] += t_in
                model_breakdown[model_name]["tokens_out"] += t_out
                model_breakdown[model_name]["latency_ms"] += lat

            elif e.type == TelemetryEventType.SKILL_EXECUTED.value:
                s.skill_calls += 1
            elif e.type == TelemetryEventType.COMPACT_COMPLETED.value:
                s.compactions += 1
            elif e.type in (TelemetryEventType.RUN_FAILED.value, TelemetryEventType.MODEL_FAILED.value, TelemetryEventType.ERROR_CLASSIFIED.value):
                s.errors += 1
            elif e.type == TelemetryEventType.HOOK_FIRED.value:
                s.hook_fires += 1
            elif e.type == TelemetryEventType.WORKFLOW_NODE_COMPLETED.value:
                s.workflow_nodes += 1
            elif e.type == TelemetryEventType.SECURITY_CHECK_PASSED.value:
                s.security_checks += 1
            elif e.type == TelemetryEventType.SECURITY_CHECK_BLOCKED.value:
                s.security_checks += 1
                s.security_blocks += 1
            elif e.type == TelemetryEventType.PII_DETECTED.value:
                s.pii_detections += 1
                hit_info = {k: e.data.get(k) for k in ("rule", "direction", "count") if e.data.get(k)}
                if hit_info:
                    s.security_hits.append(hit_info)
            elif e.type == TelemetryEventType.MEMORY_RECALLED.value:
                s.memory_recalls += 1
                layer = e.data.get("layer", "unknown")
                s.memory_layers[layer] = s.memory_layers.get(layer, 0) + e.data.get("count", 1)
            elif e.type == TelemetryEventType.MEMORY_WRITTEN.value:
                s.memory_writes += 1

        s.duration_ms = int((last_ts - first_ts) * 1000) if last_ts > first_ts else 0
        s.model_breakdown = dict(model_breakdown)
        s.component_breakdown = dict(component_breakdown)
        return s

    def counters(self) -> Dict[str, int]:
        """返回所有事件类型的累计计数。"""
        return dict(self._counters)

    def clear(self) -> None:
        """清空所有事件（测试用）。"""
        self._events.clear()
        self._counters.clear()


# ── 默认单例 ──────────────────────────────────────────────────────
telemetry = Telemetry()
