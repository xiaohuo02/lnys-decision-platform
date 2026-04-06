# -*- coding: utf-8 -*-
"""backend/core/cache.py — Redis 缓存装饰器 + Singleflight

用法:
    class MyService:
        def __init__(self, ..., redis): self.redis = redis

        @redis_cached("dashboard:kpis", ttl=300)
        async def get_kpis(self) -> dict:
            return ok(expensive_data)

效果:
    1. Redis 命中 → 直接返回 cached(data)，不执行方法体
    2. Redis 未命中 → 执行方法体，提取 data，写入 Redis，返回原始响应
    3. Singleflight → 多个并发请求同一 key，只有第一个执行，其余等待复用结果
"""
import asyncio
import functools
import json
from typing import Optional

from loguru import logger

from backend.core.response import cached


def redis_cached(key_prefix: str, ttl: int = 300):
    """
    异步方法级 Redis 缓存装饰器。

    Parameters:
        key_prefix: Redis key 前缀（如 "dashboard:kpis"）
        ttl:        缓存过期秒数，默认 300s

    要求被装饰方法所在的 self 有 self.redis 属性（aioredis.Redis 实例）。
    方法返回值需要符合 ok() / degraded() 格式: {"code": ..., "data": ..., ...}
    """
    def decorator(func):
        # Singleflight: 同一 key 并发时只执行一次
        _inflight: dict[str, asyncio.Future] = {}

        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            # ── 1. 构建 cache key ──
            cache_key = _build_cache_key(key_prefix, args, kwargs)

            # ── 2. Redis 读取 ──
            redis = getattr(self, "redis", None)
            if redis is not None:
                try:
                    raw = await redis.get(cache_key)
                    if raw is not None:
                        return cached(json.loads(raw))
                except Exception as e:
                    logger.warning(f"[cache] redis GET {cache_key}: {e}")

            # ── 3. Singleflight: 如果同 key 正在计算，等待复用 ──
            if cache_key in _inflight:
                try:
                    return await asyncio.shield(_inflight[cache_key])
                except Exception:
                    pass  # 原始请求出错，本次重新执行

            # ── 4. 首个请求：创建 Future，执行并缓存 ──
            loop = asyncio.get_running_loop()
            fut: asyncio.Future = loop.create_future()
            _inflight[cache_key] = fut

            try:
                result = await func(self, *args, **kwargs)

                # 提取 data 并写入 Redis
                if redis is not None and isinstance(result, dict):
                    data = result.get("data")
                    if data is not None:
                        try:
                            await redis.setex(
                                cache_key, ttl,
                                json.dumps(data, ensure_ascii=False, default=str),
                            )
                        except Exception as e:
                            logger.warning(f"[cache] redis SETEX {cache_key}: {e}")

                # 通知等待者
                if not fut.done():
                    fut.set_result(result)
                return result

            except Exception as exc:
                if not fut.done():
                    fut.set_exception(exc)
                raise
            finally:
                _inflight.pop(cache_key, None)

        return wrapper
    return decorator


def _build_cache_key(prefix: str, args: tuple, kwargs: dict) -> str:
    """从前缀 + 方法参数生成稳定的 cache key。"""
    if not args and not kwargs:
        return prefix
    parts = [prefix]
    for a in args:
        parts.append(str(a))
    for k in sorted(kwargs):
        parts.append(f"{k}={kwargs[k]}")
    return ":".join(parts)
