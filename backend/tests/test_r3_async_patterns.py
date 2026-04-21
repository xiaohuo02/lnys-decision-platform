# -*- coding: utf-8 -*-
"""backend/tests/test_r3_async_patterns.py — R3 异步反模式修复回归测试

覆盖：
- R3-1: ProgressChannel.emit_threadsafe 从 worker 线程跨 loop 推送
- R3-2: _avector_faq_search / _vector_faq_search 在 async 上下文下行为
- R3-3: BaseCopilotSkill.to_function_schema per-instance 缓存
"""
from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ── R3-1: ProgressChannel.emit_threadsafe ───────────────────────

class TestProgressChannelThreadsafe:
    @pytest.mark.asyncio
    async def test_emit_threadsafe_from_worker_thread(self):
        """worker 线程调 emit_threadsafe 应把事件送回主 loop 订阅者"""
        from backend.core.progress_channel import ProgressChannel

        channel = ProgressChannel(run_id="run_ts")
        assert channel._loop is not None

        received = []

        async def collect():
            async for event in channel.subscribe():
                received.append(event)
                if len(received) >= 2:
                    await channel.close()
                    return

        collector = asyncio.create_task(collect())
        await asyncio.sleep(0.05)  # 等 subscribe 进入 queue.get

        # 在 worker 线程中 emit
        def worker():
            channel.emit_threadsafe("step_started", {"step": "a"})
            channel.emit_threadsafe("step_completed", {"step": "a"})

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, worker)

        # 等收集完成
        await asyncio.wait_for(collector, timeout=2.0)
        assert len(received) == 2
        assert received[0].event_type == "step_started"
        assert received[1].event_type == "step_completed"

    @pytest.mark.asyncio
    async def test_emit_threadsafe_after_close_is_noop(self):
        from backend.core.progress_channel import ProgressChannel
        channel = ProgressChannel(run_id="run_closed")
        await channel.close()
        # 不应抛异常
        channel.emit_threadsafe("step", {})

    def test_channel_created_without_loop_has_none_loop(self):
        """在无 running loop 的同步上下文中创建 channel，_loop 应为 None"""
        from backend.core.progress_channel import ProgressChannel
        channel = ProgressChannel(run_id="run_no_loop")
        assert channel._loop is None
        # emit_threadsafe 应静默跳过
        channel.emit_threadsafe("x", {})


# ── R3-2: _avector_faq_search / _vector_faq_search ────────────────

class TestVectorFaqSearch:
    @pytest.mark.asyncio
    async def test_avector_faq_search_awaits_kb(self):
        """async 版应直接 await kb.search"""
        from backend.agents import openclaw_agent

        mock_kb = AsyncMock()
        mock_kb.search.return_value = [
            {"doc_id": "f1", "title": "t", "content": "c", "similarity": 0.9},
        ]
        with patch(
            "backend.services.enterprise_kb_service.EnterpriseKBService.get_instance",
            return_value=mock_kb,
        ):
            results = await openclaw_agent._avector_faq_search("test", top_k=3)

        assert len(results) == 1
        mock_kb.search.assert_awaited_once_with("test", top_k=3)

    @pytest.mark.asyncio
    async def test_avector_faq_search_swallows_errors(self):
        """async 版底层异常 → 返回 []"""
        from backend.agents import openclaw_agent

        mock_kb = AsyncMock()
        mock_kb.search.side_effect = RuntimeError("kb down")
        with patch(
            "backend.services.enterprise_kb_service.EnterpriseKBService.get_instance",
            return_value=mock_kb,
        ):
            results = await openclaw_agent._avector_faq_search("test")
        assert results == []

    @pytest.mark.asyncio
    async def test_sync_vector_search_in_async_context_returns_empty(self):
        """sync 版在 async 上下文中应返回 [] 而不是 sandwich"""
        from backend.agents import openclaw_agent
        results = openclaw_agent._vector_faq_search("test")
        assert results == []


# ── R3-3: to_function_schema 缓存 ──────────────────────────────

class TestToolSchemaCache:
    def test_schema_cached_per_instance(self):
        from backend.copilot.registry import SkillRegistry
        registry = SkillRegistry.instance()
        if not registry._skills:
            registry.auto_discover()

        for name, skill in registry._skills.items():
            # 两次调用应返回同一对象（identity，不是 equality）
            s1 = skill.to_function_schema()
            s2 = skill.to_function_schema()
            assert s1 is s2, f"{name} schema 未被缓存"
            # 结构完整
            assert s1["type"] == "function"
            assert s1["function"]["name"] == name

    def test_different_instances_different_cache(self):
        """同一 class 的两个实例各自独立缓存"""
        from backend.copilot.skills.ocr_skill import OcrSkill
        a = OcrSkill()
        b = OcrSkill()
        sa = a.to_function_schema()
        sb = b.to_function_schema()
        # 内容相等
        assert sa == sb
        # 但缓存对象独立（避免一个实例修改影响另一个）
        assert sa is not sb
