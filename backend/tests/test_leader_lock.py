# -*- coding: utf-8 -*-
"""backend/tests/test_leader_lock.py — LeaderLock 单元测试

用 AsyncMock 模拟 Redis，验证：
- acquire 成功 / 被他人持有 / Redis 故障
- release 原子 compare-and-delete
- 续期成功 / 续期失败 → 放弃 leader
- 构造器参数校验
"""
from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.core.leader_lock import LeaderLock  # noqa: E402


# ── 构造器校验 ────────────────────────────────────────────────────

class TestLeaderLockInit:
    def test_invalid_ttl(self):
        with pytest.raises(ValueError):
            LeaderLock(redis=AsyncMock(), key="k", ttl_seconds=0)

    def test_renew_not_less_than_ttl(self):
        with pytest.raises(ValueError):
            LeaderLock(redis=AsyncMock(), key="k", ttl_seconds=30, renew_interval_seconds=30)
        with pytest.raises(ValueError):
            LeaderLock(redis=AsyncMock(), key="k", ttl_seconds=30, renew_interval_seconds=60)

    def test_default_renew_interval(self):
        lock = LeaderLock(redis=AsyncMock(), key="k", ttl_seconds=60)
        assert lock._renew_interval == 20  # ttl // 3


# ── acquire ───────────────────────────────────────────────────────

class TestAcquire:
    @pytest.mark.asyncio
    async def test_acquire_success(self):
        redis = AsyncMock()
        redis.set.return_value = True
        lock = LeaderLock(redis=redis, key="k", ttl_seconds=30)
        assert await lock.acquire() is True
        assert lock.is_leader is True
        # 确认 NX + EX 参数
        redis.set.assert_awaited_once()
        kwargs = redis.set.await_args.kwargs
        assert kwargs.get("nx") is True
        assert kwargs.get("ex") == 30

    @pytest.mark.asyncio
    async def test_acquire_held_by_other(self):
        redis = AsyncMock()
        redis.set.return_value = None  # redis-py 返回 None 表示 NX 失败
        lock = LeaderLock(redis=redis, key="k", ttl_seconds=30)
        assert await lock.acquire() is False
        assert lock.is_leader is False

    @pytest.mark.asyncio
    async def test_acquire_redis_error(self):
        """Redis 异常时 safe default: 非 leader"""
        redis = AsyncMock()
        redis.set.side_effect = ConnectionError("redis down")
        lock = LeaderLock(redis=redis, key="k", ttl_seconds=30)
        assert await lock.acquire() is False
        assert lock.is_leader is False

    @pytest.mark.asyncio
    async def test_acquire_redis_none(self):
        """Redis=None safe default: 非 leader"""
        lock = LeaderLock(redis=None, key="k", ttl_seconds=30)
        assert await lock.acquire() is False
        assert lock.is_leader is False


# ── release ───────────────────────────────────────────────────────

class TestRelease:
    @pytest.mark.asyncio
    async def test_release_when_leader(self):
        redis = AsyncMock()
        redis.set.return_value = True
        redis.eval.return_value = 1
        lock = LeaderLock(redis=redis, key="k", ttl_seconds=30)
        await lock.acquire()
        await lock.release()
        # 验证 eval 被调用（compare-and-delete）
        redis.eval.assert_awaited()
        args = redis.eval.await_args.args
        # args = (LUA_SCRIPT, 1, "k", instance_id)
        assert args[1] == 1
        assert args[2] == "k"
        assert args[3] == lock.instance_id
        assert lock.is_leader is False

    @pytest.mark.asyncio
    async def test_release_when_not_leader_is_noop(self):
        redis = AsyncMock()
        lock = LeaderLock(redis=redis, key="k", ttl_seconds=30)
        # 没有 acquire 就 release
        await lock.release()
        redis.eval.assert_not_called()

    @pytest.mark.asyncio
    async def test_release_idempotent(self):
        redis = AsyncMock()
        redis.set.return_value = True
        redis.eval.return_value = 1
        lock = LeaderLock(redis=redis, key="k", ttl_seconds=30)
        await lock.acquire()
        await lock.release()
        # 第二次 release 不应再调 eval
        redis.eval.reset_mock()
        await lock.release()
        redis.eval.assert_not_called()


# ── renewal ───────────────────────────────────────────────────────

class TestRenewal:
    @pytest.mark.asyncio
    async def test_renewal_loop_successfully_extends(self):
        """续期任务周期性调 eval 延长 TTL"""
        redis = AsyncMock()
        redis.set.return_value = True
        redis.eval.return_value = 1
        # 短 TTL/renew 以便测试快速结束
        lock = LeaderLock(redis=redis, key="k", ttl_seconds=3, renew_interval_seconds=1)
        await lock.acquire()
        await lock.start_renewal()
        # 等 2.5 秒，至少触发 2 次续期
        await asyncio.sleep(2.5)
        await lock.release()
        assert lock.is_leader is False
        # eval 调用次数 = renewal(>=2) + release(1)
        assert redis.eval.await_count >= 3

    @pytest.mark.asyncio
    async def test_renewal_gives_up_on_renewal_failure(self):
        """续期返回 0（key 丢失/被抢）立即放弃 leader 身份"""
        redis = AsyncMock()
        redis.set.return_value = True
        # 首次续期返回 0 → 放弃
        redis.eval.return_value = 0
        lock = LeaderLock(redis=redis, key="k", ttl_seconds=3, renew_interval_seconds=1)
        await lock.acquire()
        assert lock.is_leader is True
        await lock.start_renewal()
        # 等过续期周期
        await asyncio.sleep(1.5)
        # 续期失败后自动放弃
        assert lock.is_leader is False
        await lock.release()

    @pytest.mark.asyncio
    async def test_start_renewal_idempotent(self):
        redis = AsyncMock()
        redis.set.return_value = True
        redis.eval.return_value = 1
        lock = LeaderLock(redis=redis, key="k", ttl_seconds=3, renew_interval_seconds=1)
        await lock.acquire()
        await lock.start_renewal()
        first_task = lock._renew_task
        await lock.start_renewal()  # 第二次调不应重建 task
        assert lock._renew_task is first_task
        await lock.release()

    @pytest.mark.asyncio
    async def test_start_renewal_noop_when_not_leader(self):
        redis = AsyncMock()
        redis.set.return_value = None
        lock = LeaderLock(redis=redis, key="k", ttl_seconds=3, renew_interval_seconds=1)
        await lock.acquire()  # 失败
        await lock.start_renewal()
        assert lock._renew_task is None
