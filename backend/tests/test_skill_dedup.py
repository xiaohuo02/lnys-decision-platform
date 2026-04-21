# -*- coding: utf-8 -*-
"""backend/tests/test_skill_dedup.py — SkillCallDeduplicator 单元测试

覆盖：
- 连续重复调用触发缓存返回
- 不同参数不触发重复
- TTL 过期清理
- 容量上限 LRU 淘汰
- asyncio.Lock 串行化（并发调用不 race）
"""
from __future__ import annotations

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.copilot.engine import SkillCallDeduplicator  # noqa: E402


class TestDedupBasic:
    @pytest.mark.asyncio
    async def test_first_call_not_duplicate(self):
        dedup = SkillCallDeduplicator(max_repeat=3, cache_ttl=60)
        is_dup, cached = await dedup.check_and_cache("skill_a", {"x": 1})
        assert is_dup is False
        assert cached is None

    @pytest.mark.asyncio
    async def test_cache_result_roundtrip(self):
        """第 3 次调用命中缓存（需先 cache result）"""
        dedup = SkillCallDeduplicator(max_repeat=3, cache_ttl=60)
        args = {"sku": "A01"}
        # 1st call — 记录 + 缓存
        await dedup.check_and_cache("inventory", args, result={"qty": 100})
        # 2nd call — 只记录
        is_dup, _ = await dedup.check_and_cache("inventory", args)
        assert is_dup is False
        # 3rd call — 连续 3 次 + 缓存已存在 → 命中
        is_dup, cached = await dedup.check_and_cache("inventory", args)
        assert is_dup is True
        assert cached == {"qty": 100}

    @pytest.mark.asyncio
    async def test_different_args_not_duplicate(self):
        dedup = SkillCallDeduplicator(max_repeat=2, cache_ttl=60)
        await dedup.check_and_cache("skill_a", {"x": 1}, result="r1")
        await dedup.check_and_cache("skill_a", {"x": 2}, result="r2")
        # 虽然连续 2 次 skill_a，但 args 不同 → 不算重复
        is_dup, _ = await dedup.check_and_cache("skill_a", {"x": 2})
        # x=2 连续 2 次 → 命中（max_repeat=2）
        assert is_dup is True


class TestDedupTTL:
    @pytest.mark.asyncio
    async def test_expired_cache_dropped(self):
        """TTL 过期后缓存条目应被清理"""
        dedup = SkillCallDeduplicator(max_repeat=3, cache_ttl=0.2)
        await dedup.check_and_cache("skill_a", {"k": "v"}, result="old")
        await asyncio.sleep(0.3)
        # 过期后再调，不应返回旧缓存
        is_dup, _ = await dedup.check_and_cache("skill_a", {"k": "v"})
        assert is_dup is False
        assert len(dedup._cache) == 0


class TestDedupCapacity:
    @pytest.mark.asyncio
    async def test_cache_lru_eviction(self):
        """cache 容量上限触发 LRU 淘汰"""
        dedup = SkillCallDeduplicator(max_repeat=3, cache_ttl=60, max_cache_size=3)
        for i in range(5):
            await dedup.check_and_cache("skill_a", {"i": i}, result=f"r{i}")
        # 只应保留最近 3 项
        assert len(dedup._cache) == 3
        # 最早的 i=0 应已被淘汰
        hashes_in_cache = set(dedup._cache.keys())
        hash_0 = SkillCallDeduplicator._args_hash({"i": 0})
        assert hash_0 not in hashes_in_cache

    @pytest.mark.asyncio
    async def test_recent_capacity_capped(self):
        dedup = SkillCallDeduplicator(
            max_repeat=3, cache_ttl=60, max_recent_size=10,
        )
        for i in range(50):
            await dedup.check_and_cache("skill_a", {"i": i})
        assert len(dedup._recent) == 10


class TestDedupConcurrency:
    @pytest.mark.asyncio
    async def test_concurrent_access_no_race(self):
        """并发 200 次调用应全部完成且不抛异常"""
        dedup = SkillCallDeduplicator(max_repeat=3, cache_ttl=60)

        async def call(i: int):
            await dedup.check_and_cache("skill_x", {"i": i % 5}, result=f"r{i % 5}")

        await asyncio.gather(*[call(i) for i in range(200)])
        # 5 种不同 args → cache 应有 5 条
        assert len(dedup._cache) == 5
