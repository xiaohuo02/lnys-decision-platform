# -*- coding: utf-8 -*-
"""backend/core/error_handler.py — 错误分类器与智能重试策略

设计来源: Claude Code 错误分类 + LangGraph 多层错误管理最佳实践

核心思路:
  1. 所有异常先经过 ErrorClassifier.classify() 分类
  2. 返回 ErrorAction 指导调用方如何处理
  3. execute_with_retry() 封装完整的重试/降级/中止逻辑

错误类型映射:
  RateLimitError (429)      → retry_with_backoff (读 Retry-After)
  ContextTooLongError       → compact_and_retry
  AuthenticationError (401) → abort
  ModelUnavailableError     → fallback_model
  TimeoutError              → retry (指数退避 2/4/8s + jitter)
  ServiceError              → skip_service (跳过该模块, 报告标注)
  Unknown                   → retry ×2 → abort
"""
from __future__ import annotations

import asyncio
import random
from enum import Enum
from typing import Any, Callable, Coroutine, Optional, TypeVar

from loguru import logger
from pydantic import BaseModel, ConfigDict


# ── 自定义异常层次 ────────────────────────────────────────────────

class LLMError(Exception):
    """LLM 调用相关错误基类"""
    pass


class RateLimitError(LLMError):
    """API 限流 (HTTP 429)"""
    def __init__(self, message: str = "Rate limit exceeded", retry_after: Optional[float] = None):
        super().__init__(message)
        self.retry_after = retry_after


class ContextTooLongError(LLMError):
    """输入 token 超出模型窗口"""
    def __init__(self, message: str = "Context too long", current_tokens: int = 0, max_tokens: int = 0):
        super().__init__(message)
        self.current_tokens = current_tokens
        self.max_tokens = max_tokens


class AuthenticationError(LLMError):
    """API Key 无效或过期 (HTTP 401/403)"""
    pass


class ModelUnavailableError(LLMError):
    """模型不可用 (HTTP 503 / 模型下线)"""
    def __init__(self, message: str = "Model unavailable", model_name: str = ""):
        super().__init__(message)
        self.model_name = model_name


class ServiceCallError(Exception):
    """业务 Service 调用错误（非 LLM 类）"""
    def __init__(self, service_name: str, message: str = "Service call failed"):
        super().__init__(message)
        self.service_name = service_name


# ── ErrorAction 决策结构 ──────────────────────────────────────────

class ErrorActionType(str, Enum):
    RETRY_WITH_BACKOFF = "retry_with_backoff"
    COMPACT_AND_RETRY  = "compact_and_retry"
    FALLBACK_MODEL     = "fallback_model"
    RETRY              = "retry"
    SKIP_SERVICE       = "skip_service"
    ABORT              = "abort"


class ErrorAction(BaseModel):
    """ErrorClassifier 的决策输出"""
    action:       ErrorActionType
    wait_seconds: float = 0.0
    max_retries:  int   = 0
    fallback:     Optional[str] = None   # 备用模型名
    reason:       str   = ""

    model_config = ConfigDict(use_enum_values=True)


# ── ErrorClassifier 分类器 ────────────────────────────────────────

class ErrorClassifier:
    """
    错误分类器：将异常映射为处理策略。

    用法:
        classifier = ErrorClassifier()
        action = classifier.classify(error)
        # action.action == "retry_with_backoff" / "abort" / ...
    """

    def __init__(self, fallback_model: str = "qwen3.5-plus-2026-02-15"):
        self.fallback_model = fallback_model

    def classify(self, error: Exception) -> ErrorAction:
        """将异常分类为 ErrorAction"""

        # 429 限流
        if isinstance(error, RateLimitError):
            wait = error.retry_after or 5.0
            return ErrorAction(
                action=ErrorActionType.RETRY_WITH_BACKOFF,
                wait_seconds=wait,
                max_retries=3,
                reason=f"API 限流，等待 {wait}s 后重试",
            )

        # 上下文过长
        if isinstance(error, ContextTooLongError):
            return ErrorAction(
                action=ErrorActionType.COMPACT_AND_RETRY,
                max_retries=1,
                reason=f"上下文过长 ({error.current_tokens}/{error.max_tokens})，压缩后重试",
            )

        # 认证失败 → 直接中止
        if isinstance(error, AuthenticationError):
            return ErrorAction(
                action=ErrorActionType.ABORT,
                reason="API Key 无效或过期，无法重试",
            )

        # 模型不可用 → 切换备用模型
        if isinstance(error, ModelUnavailableError):
            return ErrorAction(
                action=ErrorActionType.FALLBACK_MODEL,
                max_retries=1,
                fallback=self.fallback_model,
                reason=f"模型 {error.model_name} 不可用，切换到 {self.fallback_model}",
            )

        # 超时
        if isinstance(error, (asyncio.TimeoutError, TimeoutError)):
            return ErrorAction(
                action=ErrorActionType.RETRY,
                wait_seconds=2.0,
                max_retries=3,
                reason="请求超时，指数退避重试",
            )

        # 业务 Service 错误 → 跳过该模块
        if isinstance(error, ServiceCallError):
            return ErrorAction(
                action=ErrorActionType.SKIP_SERVICE,
                reason=f"Service '{error.service_name}' 调用失败，跳过该模块",
            )

        # OpenAI SDK 兼容错误检测 (httpx/openai 抛出的异常)
        error_str = str(error).lower()
        error_type = type(error).__name__

        if "rate" in error_str and "limit" in error_str:
            return ErrorAction(
                action=ErrorActionType.RETRY_WITH_BACKOFF,
                wait_seconds=5.0,
                max_retries=3,
                reason="检测到限流错误 (from error message)",
            )

        if "401" in error_str or "authentication" in error_type.lower():
            return ErrorAction(
                action=ErrorActionType.ABORT,
                reason="认证错误 (from error message)",
            )

        if "context" in error_str and ("long" in error_str or "length" in error_str):
            return ErrorAction(
                action=ErrorActionType.COMPACT_AND_RETRY,
                max_retries=1,
                reason="上下文过长 (from error message)",
            )

        # 未知错误 → 重试 2 次后中止
        return ErrorAction(
            action=ErrorActionType.RETRY,
            wait_seconds=1.0,
            max_retries=2,
            reason=f"未知错误 ({error_type}: {str(error)[:100]})，重试 2 次",
        )


# ── 带重试的执行器 ────────────────────────────────────────────────

T = TypeVar("T")


async def execute_with_retry(
    func: Callable[..., Coroutine[Any, Any, T]],
    *args: Any,
    classifier: Optional[ErrorClassifier] = None,
    compact_callback: Optional[Callable[..., Coroutine]] = None,
    fallback_model_callback: Optional[Callable[[str], Coroutine]] = None,
    **kwargs: Any,
) -> T:
    """
    带智能重试的异步执行器。

    参数:
        func:                   要执行的异步函数
        classifier:             错误分类器 (默认创建)
        compact_callback:       上下文压缩回调 (ContextTooLongError 时调用)
        fallback_model_callback: 切换模型回调 (ModelUnavailableError 时调用)

    返回:
        func 的返回值

    抛出:
        原始异常 (当所有重试用尽或分类为 abort 时)
    """
    _classifier = classifier or ErrorClassifier()
    attempt = 0

    while True:
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            action = _classifier.classify(e)
            attempt += 1

            logger.warning(
                f"[ErrorHandler] attempt={attempt} action={action.action} "
                f"reason={action.reason} error={type(e).__name__}: {str(e)[:200]}"
            )

            # ABORT → 直接抛出
            if action.action == ErrorActionType.ABORT:
                logger.error(f"[ErrorHandler] ABORT: {action.reason}")
                raise

            # SKIP_SERVICE → 抛出 ServiceCallError (调用方捕获后跳过)
            if action.action == ErrorActionType.SKIP_SERVICE:
                logger.warning(f"[ErrorHandler] SKIP: {action.reason}")
                raise

            # 超过最大重试次数 → 中止
            if attempt > action.max_retries:
                logger.error(
                    f"[ErrorHandler] 重试用尽 (attempt={attempt} > max={action.max_retries})"
                )
                raise

            # COMPACT_AND_RETRY → 调用压缩回调
            if action.action == ErrorActionType.COMPACT_AND_RETRY:
                if compact_callback:
                    logger.info("[ErrorHandler] 执行上下文压缩...")
                    await compact_callback()
                else:
                    logger.warning("[ErrorHandler] 无压缩回调，直接重试")

            # FALLBACK_MODEL → 调用切换模型回调
            if action.action == ErrorActionType.FALLBACK_MODEL:
                if fallback_model_callback and action.fallback:
                    logger.info(f"[ErrorHandler] 切换到备用模型: {action.fallback}")
                    await fallback_model_callback(action.fallback)
                else:
                    logger.warning("[ErrorHandler] 无模型切换回调，直接重试")

            # 等待 (指数退避 + jitter)
            if action.wait_seconds > 0:
                jitter = random.uniform(0, action.wait_seconds * 0.2)
                backoff = action.wait_seconds * (2 ** (attempt - 1))
                wait = min(backoff + jitter, 60.0)  # 最大等待 60s
                logger.info(f"[ErrorHandler] 等待 {wait:.1f}s (backoff={backoff:.1f} jitter={jitter:.1f})")
                await asyncio.sleep(wait)


# ── 默认单例 ──────────────────────────────────────────────────────

error_classifier = ErrorClassifier()
