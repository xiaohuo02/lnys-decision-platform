# -*- coding: utf-8 -*-
"""backend/core/exceptions.py — 统一异常层次 + 全局 Handler

异常继承树:
  Exception
   └── AppError (base)
        ├── BusinessError          400
        ├── AuthenticationError    401
        ├── AuthorizationError     403
        ├── ResourceNotFoundError  404
        ├── ConflictError          409
        ├── RateLimitError         429
        ├── ServiceUnavailableError 503
        ├── DatabaseError          500
        ├── AgentNotReadyError     503
        └── CacheUnavailableError  503

全局 Handler 注册顺序（main.py）:
  1. AppError           → app_error_handler
  2. HTTPException      → http_exception_handler
  3. RequestValidationError → validation_error_handler
  4. Exception          → unhandled_exception_handler
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from loguru import logger

from backend.config import settings


# ── 异常类 ────────────────────────────────────────────────────────────


class AppError(Exception):
    """可预期的业务错误基类，统一走 app_error_handler。

    向后兼容: AppError(404, "xxx不存在") 仍可正常工作。
    新写法:   raise ResourceNotFoundError("xxx不存在")
    """

    def __init__(
        self,
        code: int = 500,
        message: str = "服务器内部错误",
        data: Any = None,
        *,
        error_code: str = "INTERNAL_ERROR",
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data
        self.error_code = error_code


class BusinessError(AppError):
    """业务规则校验失败 (400)"""

    def __init__(self, message: str, error_code: str = "BUSINESS_ERROR", data: Any = None):
        super().__init__(400, message, data, error_code=error_code)


class AuthenticationError(AppError):
    """认证失败 (401)"""

    def __init__(self, message: str = "认证失败", error_code: str = "AUTH_FAILED"):
        super().__init__(401, message, error_code=error_code)


class AuthorizationError(AppError):
    """权限不足 (403)"""

    def __init__(self, message: str = "权限不足", error_code: str = "FORBIDDEN"):
        super().__init__(403, message, error_code=error_code)


class ResourceNotFoundError(AppError):
    """资源不存在 (404)"""

    def __init__(self, message: str = "资源不存在", error_code: str = "RESOURCE_NOT_FOUND"):
        super().__init__(404, message, error_code=error_code)


class ConflictError(AppError):
    """资源冲突 / 幂等重复 (409)"""

    def __init__(self, message: str = "操作冲突", error_code: str = "CONFLICT"):
        super().__init__(409, message, error_code=error_code)


class RateLimitError(AppError):
    """限流 (429)"""

    def __init__(self, message: str = "请求过于频繁", retry_after: int = 60):
        super().__init__(429, message, error_code="RATE_LIMITED")
        self.retry_after = retry_after


class ServiceUnavailableError(AppError):
    """服务暂不可用 (503)"""

    def __init__(self, message: str = "服务暂不可用", error_code: str = "SERVICE_UNAVAILABLE"):
        super().__init__(503, message, error_code=error_code)


class AgentNotReadyError(ServiceUnavailableError):
    """Agent 尚未初始化（模型文件缺失或初始化失败）"""

    def __init__(self, agent_name: str, detail: str = ""):
        msg = f"Agent '{agent_name}' 暂未就绪" + (f": {detail}" if detail else "")
        super().__init__(msg, error_code="AGENT_NOT_READY")
        self.agent_name = agent_name


class CacheUnavailableError(ServiceUnavailableError):
    """Redis 缓存不可用（非致命，允许业务降级）"""

    def __init__(self, detail: str = ""):
        super().__init__(f"缓存服务不可用: {detail}", error_code="CACHE_UNAVAILABLE")


class DatabaseError(AppError):
    """数据库操作失败 (500)"""

    def __init__(self, message: str = "数据库操作失败"):
        super().__init__(500, message, error_code="DB_ERROR")


# ── 统一错误响应构造 ──────────────────────────────────────────────────


def _error_response(
    code: int,
    message: str,
    error_code: str = "INTERNAL_ERROR",
    data: Any = None,
    trace_id: Optional[str] = None,
    detail: Optional[str] = None,
    headers: Optional[dict] = None,
) -> JSONResponse:
    """构造统一格式的错误 JSONResponse，与 core/response.py 的 meta 结构对齐。"""
    body: dict[str, Any] = {
        "code": code,
        "data": data,
        "message": message,
        "meta": {
            "degraded": False,
            "source": "error",
            "trace_id": trace_id,
            "warnings": [],
            "error_code": error_code,
            # 仅开发环境暴露异常 detail
            "detail": detail if settings.DEV_BACKDOOR_ENABLED else None,
        },
    }
    return JSONResponse(status_code=code, content=body, headers=headers)


# ── 全局 Handler ─────────────────────────────────────────────────────


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """处理所有 AppError 及其子类"""
    trace_id = getattr(request.state, "trace_id", None)
    http_status = exc.code if 400 <= exc.code < 600 else 500

    if http_status >= 500:
        logger.error(f"[AppError] {http_status} {exc.error_code}: {exc.message} trace={trace_id}")
    else:
        logger.warning(f"[AppError] {http_status} {exc.error_code}: {exc.message} trace={trace_id}")

    headers = None
    if isinstance(exc, RateLimitError):
        headers = {"Retry-After": str(exc.retry_after)}

    return _error_response(
        http_status,
        exc.message,
        exc.error_code,
        data=exc.data,
        trace_id=trace_id,
        headers=headers,
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """统一处理 FastAPI HTTPException（含中间件抛出的 401/403/429 等）"""
    trace_id = getattr(request.state, "trace_id", None)

    _CODE_MAP = {
        400: "BAD_REQUEST",
        401: "AUTH_FAILED",
        403: "FORBIDDEN",
        404: "RESOURCE_NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        429: "RATE_LIMITED",
    }
    error_code = _CODE_MAP.get(exc.status_code, "HTTP_ERROR")
    message = exc.detail if isinstance(exc.detail, str) else "请求错误"

    logger.warning(f"[HTTPException] {exc.status_code} {error_code}: {message} trace={trace_id}")

    return _error_response(
        exc.status_code,
        message,
        error_code,
        trace_id=trace_id,
        headers=dict(exc.headers) if exc.headers else None,
    )


async def validation_error_handler(request: Request, exc) -> JSONResponse:
    """将 Pydantic / FastAPI 422 ValidationError 转换为统一格式。"""
    trace_id = getattr(request.state, "trace_id", None)

    errors = exc.errors() if hasattr(exc, "errors") else []
    # 拼接人可读摘要：取前 3 条错误，格式 "字段名: 错误描述"
    summaries = []
    for e in errors[:3]:
        loc = ".".join(str(l) for l in e.get("loc", []) if l != "body")
        summaries.append(f"{loc}: {e.get('msg', '校验失败')}")
    hint = "; ".join(summaries) if summaries else "请检查请求参数"
    if len(errors) > 3:
        hint += f" (共 {len(errors)} 项错误)"

    msg = f"参数校验失败: {hint}"
    logger.warning(f"[ValidationError] {msg} trace={trace_id}")

    return _error_response(422, msg, "VALIDATION_ERROR", data=errors, trace_id=trace_id)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """兜底：捕获所有未处理异常，防止泄露堆栈"""
    trace_id = getattr(request.state, "trace_id", None)
    logger.exception(f"[UnhandledException] {type(exc).__name__}: {exc} trace={trace_id}")

    return _error_response(
        500,
        "服务器内部错误，请稍后重试",
        "INTERNAL_ERROR",
        trace_id=trace_id,
        detail=f"{type(exc).__name__}: {exc}",
    )
