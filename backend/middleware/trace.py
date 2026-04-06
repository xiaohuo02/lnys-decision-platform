# -*- coding: utf-8 -*-
"""backend/middleware/trace.py — 请求追踪中间件

为每个请求注入 trace_id，供异常 handler 和日志使用。
优先使用客户端传入的 X-Trace-ID header，否则自动生成。
"""
from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class TraceMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        trace_id = request.headers.get("X-Trace-ID") or uuid.uuid4().hex[:8]
        request.state.trace_id = trace_id

        response = await call_next(request)
        response.headers["X-Trace-ID"] = trace_id
        return response
