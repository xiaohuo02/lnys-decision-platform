# -*- coding: utf-8 -*-
"""backend/core/rate_limiter.py — 基于 Redis 的滑动窗口限流器

设计原则:
  - 使用 Redis sorted set 实现滑动窗口，精度到毫秒
  - 作为 FastAPI Depends 使用，而非全局中间件（按需保护关键接口）
  - Redis 不可用时降级放行（不因限流基础设施故障阻塞业务）
  - 支持按 IP / 用户 / 自定义 key 限流

用法:
    from backend.core.rate_limiter import RateLimiter

    login_limiter = RateLimiter(max_requests=5, window_seconds=60, prefix="login")

    @router.post("/auth/login")
    async def login(
        request: Request,
        _: None = Depends(login_limiter),
        ...
    ):
"""
from __future__ import annotations

import time
from typing import Optional

from fastapi import Depends, Request
from loguru import logger
from redis.asyncio import Redis

from backend.core.exceptions import RateLimitError
from backend.database import get_redis


class RateLimiter:
    """滑动窗口限流器（FastAPI 依赖项工厂）

    参数:
        max_requests:   窗口内允许的最大请求数
        window_seconds: 滑动窗口大小（秒）
        prefix:         Redis key 前缀，用于区分不同限流策略
        key_func:       自定义 key 提取函数，默认按客户端 IP
    """

    def __init__(
        self,
        max_requests: int = 10,
        window_seconds: int = 60,
        prefix: str = "rl",
        key_func: Optional[callable] = None,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.prefix = prefix
        self.key_func = key_func or self._default_key

    @staticmethod
    def _default_key(request: Request) -> str:
        """默认按客户端 IP 提取限流 key"""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def __call__(
        self,
        request: Request,
        redis: Optional[Redis] = Depends(get_redis),
    ) -> None:
        """FastAPI 依赖项入口"""
        if redis is None:
            # Redis 不可用时降级放行，不阻塞业务
            logger.warning(f"[rate_limiter:{self.prefix}] Redis unavailable, allowing request")
            return

        client_key = self.key_func(request) if self.key_func != self._default_key else self._default_key(request)
        redis_key = f"rate_limit:{self.prefix}:{client_key}"

        try:
            now_ms = int(time.time() * 1000)
            window_start_ms = now_ms - self.window_seconds * 1000

            pipe = redis.pipeline()
            # 1. 移除窗口外的过期记录
            pipe.zremrangebyscore(redis_key, 0, window_start_ms)
            # 2. 统计窗口内请求数
            pipe.zcard(redis_key)
            # 3. 添加当前请求时间戳
            pipe.zadd(redis_key, {str(now_ms): now_ms})
            # 4. 设置 key 过期时间（防止残留）
            pipe.expire(redis_key, self.window_seconds + 1)
            results = await pipe.execute()

            request_count = results[1]  # zcard 结果

            if request_count >= self.max_requests:
                retry_after = self.window_seconds
                logger.warning(
                    f"[rate_limiter:{self.prefix}] "
                    f"key={client_key} blocked ({request_count}/{self.max_requests})"
                )
                raise RateLimitError(
                    message=f"请求过于频繁，请 {retry_after} 秒后重试",
                    retry_after=retry_after,
                )

        except RateLimitError:
            raise
        except Exception as exc:
            # Redis 操作异常时降级放行
            logger.error(f"[rate_limiter:{self.prefix}] Redis error: {exc}, allowing request")


# ── 预定义常用限流策略 ────────────────────────────────────────────────

# 登录接口：每分钟最多 5 次尝试
login_limiter = RateLimiter(max_requests=5, window_seconds=60, prefix="login")

# 通用 API：每分钟最多 60 次
api_limiter = RateLimiter(max_requests=60, window_seconds=60, prefix="api")

# 敏感操作（密码修改等）：每小时最多 10 次
sensitive_limiter = RateLimiter(max_requests=10, window_seconds=3600, prefix="sensitive")
