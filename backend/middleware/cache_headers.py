# -*- coding: utf-8 -*-
"""backend/middleware/cache_headers.py — HTTP Cache-Control 响应头中间件

为 GET 请求添加合适的缓存头，让浏览器/CDN 可以缓存短期数据，
减少重复请求打到后端。

策略:
- /api/* GET 200 → max-age=30, stale-while-revalidate=300
  （30s 内浏览器直接用缓存，300s 内可先展示旧数据同时后台刷新）
- /admin/* → no-store（管理后台不缓存）
- /api/health → no-cache
- 非 GET / 非 200 → 不设置
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class CacheHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # 只对 GET 200 响应设置缓存头
        if request.method != "GET" or response.status_code != 200:
            return response

        path = request.url.path

        # Admin 接口：禁止缓存
        if path.startswith("/admin"):
            response.headers["Cache-Control"] = "no-store"
            return response

        # Health 接口：不缓存
        if path in ("/api/health", "/api/v1/health"):
            response.headers["Cache-Control"] = "no-cache"
            return response

        # 业务 API：短期缓存 + stale-while-revalidate
        if path.startswith("/api"):
            response.headers["Cache-Control"] = (
                "public, max-age=30, stale-while-revalidate=300"
            )
            return response

        return response
