# -*- coding: utf-8 -*-
"""backend/middleware/timeout.py — 请求超时中间件

设计:
  - 给每个请求设定最大执行时间（默认 30s）
  - 超时后返回 504 Gateway Timeout
  - SSE / 流式接口通过路径白名单跳过
  - 使用 asyncio.wait_for 实现，不影响其他请求
"""
import asyncio

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from loguru import logger


class RequestTimeoutMiddleware(BaseHTTPMiddleware):
    """为非流式请求设置 hard timeout"""

    def __init__(self, app, timeout_seconds: float = 30.0, skip_prefixes: tuple = ()):
        super().__init__(app)
        self._timeout = timeout_seconds
        self._skip_prefixes = skip_prefixes
        logger.info(f"[middleware:timeout] timeout={timeout_seconds}s")

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        for prefix in self._skip_prefixes:
            if path.startswith(prefix):
                return await call_next(request)

        try:
            return await asyncio.wait_for(
                call_next(request),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            logger.error(
                f"[middleware:timeout] {request.method} {path} "
                f"exceeded {self._timeout}s — returning 504"
            )
            return JSONResponse(
                status_code=504,
                content={
                    "code": 504,
                    "message": f"请求超时（>{self._timeout}s），请稍后重试",
                    "error": "REQUEST_TIMEOUT",
                },
            )
