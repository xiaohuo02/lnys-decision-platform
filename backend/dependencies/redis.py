# -*- coding: utf-8 -*-
"""backend/dependencies/redis.py — Redis 客户端依赖注入"""
from typing import Annotated
from fastapi import Depends, Request
import redis.asyncio as aioredis


async def _get_redis(request: Request) -> aioredis.Redis:
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        from backend.database import get_redis as _get
        return await _get()
    return redis


RedisClient = Annotated[aioredis.Redis, Depends(_get_redis)]
