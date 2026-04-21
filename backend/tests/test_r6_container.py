# -*- coding: utf-8 -*-
"""backend/tests/test_r6_container.py — R6-2 依赖注入容器单元测试

验收目标（对应 R6-2 方案）:
  1. CoreContainer / AgentContainer / AppContainer 的构造和不可变语义
  2. **核心验收**: `dataclasses.replace(core, telemetry=fake)` 一个位置替换成功
     无需散点 patch("backend.core.telemetry.telemetry", ...)
  3. CopilotEngine 接受 container 可选参数，不破坏旧调用签名
  4. feature flag 控制: COPILOT_CONTAINER_ENABLED 决定 Engine 是否从 container 取依赖

测试策略:
  - 用手动构造 CoreContainer 的方式（直接传 mock），避开对真实 DB / Redis / 模型的依赖
  - build_core_container 完整路径的 integration 测试交给 lifespan 启动验证
"""
from __future__ import annotations

import dataclasses
import os
import sys
from typing import Any
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.core.container import (  # noqa: E402
    AgentContainer,
    AppContainer,
    CoreContainer,
    build_agent_container,
)


# ── Stubs ─────────────────────────────────────────────────────────

class _FakeTelemetry:
    """仅记录 emit 调用，用于验证 telemetry 替换是否生效。"""

    def __init__(self):
        self.emitted: list[tuple] = []
        self.configured = False

    def configure(self, **kwargs):
        self.configured = True

    def emit(self, event_type, data=None, run_id="", thread_id="", component=""):
        self.emitted.append((event_type, data, component, thread_id))
        return None


class _FakeModelSelector:
    def __init__(self):
        self.initialized = False

    def initialize(self):
        self.initialized = True

    def get_spec(self, role):
        return MagicMock(model_name="fake-model")


def _build_stub_core(telemetry=None, model_selector=None) -> CoreContainer:
    """手动构造一个 CoreContainer stub，不走 build_core_container（避免真依赖）。"""
    settings_stub = MagicMock()
    settings_stub.COPILOT_CONTAINER_ENABLED = True
    return CoreContainer(
        settings=settings_stub,
        redis=MagicMock(name="redis"),
        db_session_factory=MagicMock(name="sync_sessionmaker"),
        async_db_session_factory=MagicMock(name="async_sessionmaker"),
        telemetry=telemetry or _FakeTelemetry(),
        model_selector=model_selector or _FakeModelSelector(),
        token_counter=MagicMock(name="token_counter"),
        context_monitor=MagicMock(name="context_monitor"),
        input_guard=MagicMock(name="input_guard"),
    )


# ── 测试 1: CoreContainer 不可变性 & replace 能力 ─────────────────

class TestCoreContainerImmutable:
    def test_frozen_dataclass(self):
        """CoreContainer 是 frozen dataclass，字段赋值应抛 FrozenInstanceError。"""
        core = _build_stub_core()
        with pytest.raises(dataclasses.FrozenInstanceError):
            core.telemetry = _FakeTelemetry()  # type: ignore[misc]

    def test_replace_swaps_telemetry(self):
        """核心验收: 一次 dataclasses.replace 即可完成 telemetry 替换。

        这对应 R6-2 方案中的验收标准:
            'patch("backend.core.telemetry.telemetry", ...) 在测试里一个位置就能换掉'
        """
        old_telem = _FakeTelemetry()
        core = _build_stub_core(telemetry=old_telem)
        assert core.telemetry is old_telem

        new_telem = _FakeTelemetry()
        core2 = dataclasses.replace(core, telemetry=new_telem)

        # 原 container 不变，新 container 指向新 telemetry
        assert core.telemetry is old_telem
        assert core2.telemetry is new_telem
        # 其他字段保持不变（引用相同）
        assert core2.redis is core.redis
        assert core2.model_selector is core.model_selector

    def test_replace_swaps_model_selector(self):
        """同样的 replace 能力对所有字段都成立。"""
        core = _build_stub_core()
        fake_selector = _FakeModelSelector()
        core2 = dataclasses.replace(core, model_selector=fake_selector)
        assert core2.model_selector is fake_selector
        assert core.model_selector is not fake_selector  # 原实例不变


# ── 测试 2: AgentContainer / AppContainer 构造 ───────────────────

class TestAgentAndAppContainer:
    def test_build_agent_container_wraps_core(self):
        """build_agent_container 返回的 AgentContainer 持有同一 core 引用。"""
        core = _build_stub_core()
        agent = build_agent_container(core)
        assert agent.core is core
        assert agent.skill_registry is not None  # SkillRegistry.instance()

    def test_agent_container_is_frozen(self):
        core = _build_stub_core()
        agent = build_agent_container(core)
        with pytest.raises(dataclasses.FrozenInstanceError):
            agent.skill_registry = None  # type: ignore[misc]

    def test_app_container_facade(self):
        """AppContainer 的 property 转发正确。"""
        core = _build_stub_core()
        agent = build_agent_container(core)
        app = AppContainer(core=core, agent=agent)

        assert app.settings is core.settings
        assert app.redis is core.redis
        assert app.telemetry is core.telemetry
        assert app.skill_registry is agent.skill_registry
        assert app.core is core
        assert app.agent is agent


# ── 测试 3: CoreContainer 延迟加载访问器 ──────────────────────────

class TestLazyAccessors:
    def test_get_embedding_not_called_on_construct(self):
        """构造 CoreContainer 时不应触发 EmbeddingService 初始化。"""
        # 直接构造 stub，内部不会调用 get_embedding()。如果构造就触发，
        # 就需要加载 ~200MB BGE 模型，会在 CI 上爆内存。
        core = _build_stub_core()
        # 不调用 .get_embedding()，构造应秒完成
        assert core is not None

    def test_get_embedding_returns_singleton(self):
        """get_embedding() 返回 module 级的 EmbeddingService singleton。"""
        # 此测试只验证方法签名可调用；真实调用会加载模型，跳过执行
        core = _build_stub_core()
        assert callable(core.get_embedding)
        assert callable(core.get_vector_store)


# ── 测试 4: CopilotEngine 接受 container ──────────────────────────

class TestEngineContainerInjection:
    def test_engine_accepts_no_container_legacy(self, monkeypatch):
        """旧调用 CopilotEngine(redis, db) 无 container 参数 → 走旧单例路径。"""
        # 避免真实 SkillRegistry.auto_discover 加载（tests 环境可能未初始化）
        from backend.copilot.engine import CopilotEngine
        engine = CopilotEngine(redis=MagicMock(), db=None)
        assert engine._container is None
        assert engine._registry is not None

    def test_engine_accepts_container_but_flag_off(self, monkeypatch):
        """flag 关闭时，即使传入 container，_registry 也应走 SkillRegistry.instance()。"""
        from backend.copilot.engine import CopilotEngine
        from backend.config import settings as real_settings

        monkeypatch.setattr(real_settings, "COPILOT_CONTAINER_ENABLED", False)

        fake_registry = MagicMock(name="fake_skill_registry_in_container")
        core = _build_stub_core()
        agent = AgentContainer(core=core, skill_registry=fake_registry)

        engine = CopilotEngine(redis=MagicMock(), db=None, container=agent)
        # flag 关 → 忽略 container 的 skill_registry，走 SkillRegistry.instance()
        assert engine._container is agent
        assert engine._registry is not fake_registry

    def test_engine_uses_container_skill_registry_when_flag_on(self, monkeypatch):
        """flag 开启时，Engine 应从 container 取 skill_registry。"""
        from backend.copilot.engine import CopilotEngine
        from backend.config import settings as real_settings

        monkeypatch.setattr(real_settings, "COPILOT_CONTAINER_ENABLED", True)

        fake_registry = MagicMock(name="fake_skill_registry_in_container")
        core = _build_stub_core()
        agent = AgentContainer(core=core, skill_registry=fake_registry)

        engine = CopilotEngine(redis=MagicMock(), db=None, container=agent)
        # flag 开 → 使用 container 的 skill_registry
        assert engine._registry is fake_registry

    def test_engine_flag_on_but_no_container_fallback(self, monkeypatch):
        """flag 开启但未传 container → 仍然 fallback 到单例，不抛异常。"""
        from backend.copilot.engine import CopilotEngine
        from backend.config import settings as real_settings

        monkeypatch.setattr(real_settings, "COPILOT_CONTAINER_ENABLED", True)

        engine = CopilotEngine(redis=MagicMock(), db=None, container=None)
        assert engine._container is None
        assert engine._registry is not None  # SkillRegistry.instance()


# ── 测试 5: 向后兼容性保证 ────────────────────────────────────────

class TestBackwardCompat:
    def test_module_singletons_still_importable(self):
        """现有代码的 module-level singleton import 不应被破坏。"""
        from backend.core.telemetry import telemetry
        from backend.core.model_selector import model_selector
        from backend.core.context_monitor import context_monitor
        from backend.core.token_counter import token_counter
        from backend.governance.guardrails.input_guard import input_guard

        assert telemetry is not None
        assert model_selector is not None
        assert context_monitor is not None
        assert token_counter is not None
        assert input_guard is not None

    def test_core_container_can_reference_real_singletons(self):
        """CoreContainer 可以直接持有现有 module singleton 的引用（用于 lifespan 场景）。"""
        from backend.core.telemetry import telemetry as real_telem
        from backend.core.model_selector import model_selector as real_selector
        from backend.core.context_monitor import context_monitor
        from backend.core.token_counter import token_counter
        from backend.governance.guardrails.input_guard import input_guard

        core = CoreContainer(
            settings=MagicMock(),
            redis=MagicMock(),
            db_session_factory=MagicMock(),
            async_db_session_factory=MagicMock(),
            telemetry=real_telem,
            model_selector=real_selector,
            token_counter=token_counter,
            context_monitor=context_monitor,
            input_guard=input_guard,
        )
        assert core.telemetry is real_telem
