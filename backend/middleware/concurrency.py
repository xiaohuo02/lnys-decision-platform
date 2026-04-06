# -*- coding: utf-8 -*-
"""backend/middleware/concurrency.py — 全局并发上限中间件

设计:
  - 使用 asyncio.Semaphore 控制同时处理的请求数
  - 超出上限时返回 503 Service Unavailable
  - 轻量级内存计数，无外部依赖
  - SSE / WebSocket 长连接不占用信号量（通过路径白名单跳过）
"""
import asyncio

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from loguru import logger


class ConcurrencyLimitMiddleware(BaseHTTPMiddleware):
    """限制服务器同时处理的请求数量，防止过载"""

    def __init__(self, app, max_concurrent: int = 500, skip_prefixes: tuple = ()):
        super().__init__(app)
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max = max_concurrent
        self._skip_prefixes = skip_prefixes
        logger.info(f"[middleware:concurrency] max_concurrent={max_concurrent}")

    async def dispatch(self, request: Request, call_next):
        # 跳过长连接路径（SSE stream 等）
        path = request.url.path
        for prefix in self._skip_prefixes:
            if path.startswith(prefix):
                return await call_next(request)

        if self._semaphore.locked():
            logger.warning(
                f"[middleware:concurrency] rejected {request.method} {path} "
                f"(at capacity {self._max})"
            )
            return JSONResponse(
                status_code=503,
                content={
                    "code": 503,
                    "message": "服务器繁忙，请稍后重试",
                    "error": "CONCURRENCY_LIMIT",
                },
            )

        async with self._semaphore:
            return await call_next(request)
