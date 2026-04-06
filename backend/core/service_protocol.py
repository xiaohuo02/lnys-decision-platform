# -*- coding: utf-8 -*-
"""backend/core/service_protocol.py — 统一 Service 调用协议

设计来源: Claude Code 统一 Tool 调用协议 + 本项目 v4.0 架构方案

核心职责:
  1. 注册所有 Service 实例 (register)
  2. 提供统一调用入口 (call)
  3. 每次调用自动执行完整管道:
     input 校验 → Trace begin_step → 执行 → Trace end_step → SSE 推送

可选集成 (均可为 None，不影响核心流程):
  - TraceContext:     自动记录 step (来自 governance/trace_center/tracer.py)
  - ProgressChannel:  SSE 进度推送 (AG-04 实现后接入)
  - ErrorClassifier:  错误分类与智能重试 (core/error_handler.py)
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Callable, Coroutine, Dict, Optional, Protocol, runtime_checkable

from loguru import logger

from backend.schemas.service_result import (
    ServiceCallContext, ServiceMetrics, ServiceResult, service_error,
)
from backend.schemas.run_state import StepType
from backend.core.error_handler import (
    ErrorClassifier, ServiceCallError, execute_with_retry, error_classifier,
)


# ── Service 接口约定 ──────────────────────────────────────────────

@runtime_checkable
class ServiceLike(Protocol):
    """所有 Service 必须实现的最小接口"""
    async def run(self, input_data: Any) -> ServiceResult: ...


# ── ServiceRegistry: 注册与管理 ───────────────────────────────────

class ServiceRegistry:
    """Service 注册表，管理所有已注册的 Service 实例"""

    def __init__(self):
        self._services: Dict[str, Any] = {}

    def register(self, name: str, instance: Any) -> None:
        """注册一个 Service 实例"""
        self._services[name] = instance
        logger.info(f"[ServiceRegistry] 注册 service: {name} ({type(instance).__name__})")

    def get(self, name: str) -> Any:
        """获取已注册的 Service 实例"""
        svc = self._services.get(name)
        if svc is None:
            raise KeyError(f"Service '{name}' 未注册。已注册: {list(self._services.keys())}")
        return svc

    def has(self, name: str) -> bool:
        return name in self._services

    @property
    def names(self) -> list[str]:
        return list(self._services.keys())


# ── ServiceProtocol: 统一调用入口 ─────────────────────────────────

class ServiceProtocol:
    """
    统一 Service 调用协议。

    用法:
        protocol = ServiceProtocol()
        protocol.registry.register("customer_intelligence", CustomerIntelligenceService())

        result = await protocol.call(
            service_name="customer_intelligence",
            input_data={"feature_snapshot_id": "snap_001"},
            context=ServiceCallContext(run_id="run_001", caller="business_overview"),
        )

    可选注入:
        protocol.trace_context = trace_ctx   # TraceContext 实例
        protocol.progress_callback = cb      # SSE 推送回调
    """

    def __init__(
        self,
        classifier: Optional[ErrorClassifier] = None,
    ):
        self.registry = ServiceRegistry()
        self.classifier = classifier or error_classifier
        # 可选组件 (后续阶段接入)
        self.trace_context: Any = None            # TraceContext 实例
        self.progress_callback: Optional[
            Callable[[str, str, dict], Coroutine]
        ] = None  # async fn(event_type, step_name, data)

    async def call(
        self,
        service_name: str,
        input_data: Any = None,
        context: Optional[ServiceCallContext] = None,
        method: str = "run",
    ) -> ServiceResult:
        """
        统一调用入口。

        执行管道:
          1. 获取 Service 实例
          2. Trace: begin_step
          3. SSE: step_started
          4. 执行 service.method(input_data)，包裹在 execute_with_retry 中
          5. Trace: end_step
          6. SSE: step_completed / step_failed
          7. 返回 ServiceResult
        """
        ctx = context or ServiceCallContext(caller="unknown")
        t0 = time.monotonic()
        step_id = None

        # 1. 获取 Service
        try:
            svc = self.registry.get(service_name)
        except KeyError as e:
            return service_error(str(e), ServiceMetrics(latency_ms=0))

        # 2. Trace: begin_step
        if self.trace_context is not None:
            try:
                step_id = self.trace_context.begin_step(
                    step_type=StepType.SERVICE_CALL,
                    step_name=service_name,
                    agent_name=ctx.caller,
                    input_summary=_truncate(str(input_data), 200),
                )
                ctx.step_id = str(step_id)
            except Exception as e:
                logger.warning(f"[ServiceProtocol] trace begin_step failed: {e}")

        # 3. SSE: step_started
        await self._emit_progress("step_started", service_name, {
            "step_name": service_name,
            "agent_name": ctx.caller,
            "message": f"正在执行 {service_name}...",
        })

        # 4. 执行
        result: ServiceResult
        retry_count = 0
        try:
            async def _do_call() -> ServiceResult:
                fn = getattr(svc, method)
                if input_data is not None:
                    return await fn(input_data)
                else:
                    return await fn()

            result = await execute_with_retry(
                _do_call,
                classifier=self.classifier,
            )
            # 记录重试次数 (如果 execute_with_retry 内部有重试)

        except ServiceCallError:
            # 跳过该服务 → 返回降级结果
            latency_ms = int((time.monotonic() - t0) * 1000)
            result = ServiceResult(
                success=True,
                data=None,
                summary=f"[跳过] {service_name} 不可用，已跳过该模块",
                fallback_used=True,
                metrics=ServiceMetrics(latency_ms=latency_ms),
            )
        except Exception as e:
            # 所有重试用尽，返回失败
            latency_ms = int((time.monotonic() - t0) * 1000)
            result = service_error(
                f"{service_name} 执行失败: {type(e).__name__}: {str(e)[:200]}",
                ServiceMetrics(latency_ms=latency_ms),
            )

        # 确保 metrics.latency_ms 有值
        if result.metrics.latency_ms == 0:
            result.metrics.latency_ms = int((time.monotonic() - t0) * 1000)

        # 5. Trace: end_step
        if self.trace_context is not None and step_id is not None:
            try:
                from backend.schemas.run_state import TokenUsage
                self.trace_context.end_step(
                    step_id=step_id,
                    output_summary=_truncate(result.summary or result.error or "", 200),
                    token_usage=TokenUsage(total_tokens=result.metrics.tokens_used),
                    cost_amount=result.metrics.cost_amount,
                    artifact_ids=[result.artifact_ref] if result.artifact_ref else [],
                    error_message=result.error,
                    retry_count=retry_count,
                )
            except Exception as e:
                logger.warning(f"[ServiceProtocol] trace end_step failed: {e}")

        # 6. SSE: step_completed / step_failed
        if result.success:
            await self._emit_progress("step_completed", service_name, {
                "step_name": service_name,
                "message": result.summary or f"{service_name} 完成",
                "latency_ms": result.metrics.latency_ms,
                "fallback_used": result.fallback_used,
            })
        else:
            await self._emit_progress("step_failed", service_name, {
                "step_name": service_name,
                "error": result.error or "unknown",
                "latency_ms": result.metrics.latency_ms,
            })

        logger.info(
            f"[ServiceProtocol] {service_name} "
            f"{'OK' if result.success else 'FAIL'} "
            f"latency={result.metrics.latency_ms}ms "
            f"tokens={result.metrics.tokens_used} "
            f"cost={result.metrics.cost_amount:.4f} "
            f"fallback={result.fallback_used}"
        )

        return result

    # ── 内部方法 ──────────────────────────────────────────────────

    async def _emit_progress(self, event_type: str, step_name: str, data: dict) -> None:
        """推送进度事件 (如果 progress_callback 已设置)"""
        if self.progress_callback is not None:
            try:
                await self.progress_callback(event_type, step_name, data)
            except Exception as e:
                logger.warning(f"[ServiceProtocol] progress callback failed: {e}")


# ── 工具函数 ──────────────────────────────────────────────────────

def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


# ── 全局单例 ──────────────────────────────────────────────────────

service_protocol = ServiceProtocol()
