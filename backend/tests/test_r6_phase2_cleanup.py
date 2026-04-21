# -*- coding: utf-8 -*-
"""backend/tests/test_r6_phase2_cleanup.py — R6 遗留项清理后的补充测试

覆盖:
  1. Engine._render_synthesize_prompt 的 hardcoded / prompt_store 两路径
  2. PolicyAdjuster.register_apply_handler + 真实 apply + TTL rollback handler
  3. policy_handlers.handle_model_default_name 改 ModelSelector 的效果
  4. PeriodicEvaluator.configure 注入 db_factory 后持久化尝试（mock db）
  5. PolicyAdjuster.configure 注入 db_factory 后持久化尝试（mock db）
"""
from __future__ import annotations

import os
import sys
import time
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.core.prompt_store import PromptStore, PromptTemplate, prompt_store as _global_ps  # noqa: E402
from backend.governance.eval_center.periodic_evaluator import (  # noqa: E402
    PeriodicEvaluator,
    EvalVerdict,
)
from backend.governance.policy_center.policy_adjuster import (  # noqa: E402
    PolicyAdjuster,
)
from backend.governance.policy_center.policy_handlers import (  # noqa: E402
    handle_model_default_name,
    register_default_handlers,
)


# ── 1. Engine synthesize prompt 两路径 ─────────────────────

class TestSynthesizePromptRouting:
    def test_hardcoded_path_when_flag_off(self, monkeypatch):
        """flag=off 时走 hardcoded，prompt 与 R6 之前一致。"""
        from backend.copilot.engine import CopilotEngine
        from backend.config import settings as real_settings

        monkeypatch.setattr(real_settings, "PROMPT_STORE_ENABLED", False)

        result = CopilotEngine._render_synthesize_prompt(
            context_system_prompt="CTX",
            skill_hint="总结库存",
            instruction_hint="简短直答",
            user_id="u1",
        )
        # 必须包含硬编码的固定段落
        assert "CTX" in result
        assert "你刚刚调用了分析工具获得了数据结果" in result
        assert "总结库存" in result
        assert "简短直答" in result
        assert "必须引用工具返回的关键数值" in result

    def test_prompt_store_path_when_flag_on(self, monkeypatch):
        """flag=on 且 prompt_store 已注册 key → 走 render，发 PROMPT_USED 遥测。"""
        from backend.copilot.engine import CopilotEngine
        from backend.config import settings as real_settings
        from backend.core.telemetry import telemetry, TelemetryEventType

        monkeypatch.setattr(real_settings, "PROMPT_STORE_ENABLED", True)
        telemetry.clear()

        # 注入一个独立的 store 让测试不依赖 lifespan 加载
        # 为了简洁,我们注册模板到 module 级 prompt_store
        _global_ps.register(PromptTemplate(
            key="agent.synthesize_base",
            version="test-v1",
            content="SYS={system_prompt}||SH={skill_hint_block}||INS={instruction_hint_block}",
            source="inline",
        ), set_as_default=True)

        result = CopilotEngine._render_synthesize_prompt(
            context_system_prompt="CTX",
            skill_hint="H1",
            instruction_hint="I1",
            user_id="u_phase2",
        )
        assert "SYS=CTX" in result
        assert "H1" in result
        assert "I1" in result
        # 发了 PROMPT_USED 事件
        events = telemetry.recent()
        types = [e["type"] for e in events]
        assert TelemetryEventType.PROMPT_USED.value in types

    def test_prompt_store_fallback_on_missing_key(self, monkeypatch):
        """flag=on 但 store 没有此 key → 平滑 fallback 到 hardcoded。"""
        from backend.copilot.engine import CopilotEngine
        from backend.config import settings as real_settings

        monkeypatch.setattr(real_settings, "PROMPT_STORE_ENABLED", True)

        # 用独立空 store 模拟"未注册"场景
        empty_ps = PromptStore()
        monkeypatch.setattr(
            "backend.core.prompt_store.prompt_store", empty_ps,
        )

        result = CopilotEngine._render_synthesize_prompt(
            context_system_prompt="CTX", skill_hint="", instruction_hint="",
        )
        # hardcoded 分支标志
        assert "你刚刚调用了分析工具获得了数据结果" in result


# ── 2. PolicyAdjuster apply handler 注册 ──────────────────

class TestPolicyApplyHandler:
    def test_register_handler_validates_callable(self):
        adj = PolicyAdjuster(enforce_mode="enforce")
        with pytest.raises(ValueError):
            adj.register_apply_handler("model.default_name", "not_callable")

    def test_handler_called_on_enforce_apply(self):
        """注册 handler 后，enforce + whitelist 命中时 handler 被调用。"""
        adj = PolicyAdjuster(
            enforce_mode="enforce",
            enforce_whitelist=["model.default_name"],
        )
        calls = []
        adj.register_apply_handler(
            "model.default_name", lambda change: calls.append(change),
        )
        v = EvalVerdict(
            metric="model_latency_p95_5m", subject="qwen-plus",
            value=9000, threshold_warning=5000, threshold_critical=8000,
            status="critical", sample_size=10, window_seconds=300,
            timestamp=time.time(),
            recommendation="model_downgrade:qwen-plus",
        )
        changes = adj.process([v])
        assert len(changes) == 1
        assert changes[0].applied is True
        assert len(calls) == 1
        assert calls[0].policy_key == "model.default_name"

    def test_handler_exception_not_propagated(self):
        """handler 抛异常不影响 process 流程。"""
        adj = PolicyAdjuster(
            enforce_mode="enforce",
            enforce_whitelist=["model.default_name"],
        )
        adj.register_apply_handler(
            "model.default_name", lambda c: (_ for _ in ()).throw(RuntimeError("bang")),
        )
        v = EvalVerdict(
            metric="model_latency_p95_5m", subject="qwen-plus",
            value=9000, threshold_warning=5000, threshold_critical=8000,
            status="critical", sample_size=10, window_seconds=300,
            timestamp=time.time(),
            recommendation="model_downgrade:qwen-plus",
        )
        changes = adj.process([v])
        # handler 抛异常但 applied 仍被标 True（文档行为）
        assert changes[0].applied is True

    def test_rollback_invokes_reverse_handler(self):
        """TTL 过期触发 rollback handler，new_value/old_value 互换。"""
        adj = PolicyAdjuster(
            enforce_mode="enforce",
            enforce_whitelist=["model.default_name"],
        )
        calls = []
        adj.register_apply_handler(
            "model.default_name", lambda c: calls.append(c.new_value),
        )
        v = EvalVerdict(
            metric="model_latency_p95_5m", subject="qwen-plus",
            value=9000, threshold_warning=5000, threshold_critical=8000,
            status="critical", sample_size=10, window_seconds=300,
            timestamp=time.time(),
            recommendation="model_downgrade:qwen-plus",
        )
        changes = adj.process([v])
        c = changes[0]
        # 人为触发 TTL rollback
        c.expires_at = time.time() - 1
        adj.process([])
        assert c.rolled_back is True
        # handler 应被调用两次：apply 时 new_value，rollback 时 old_value
        assert len(calls) == 2

    def test_unregister_handler(self):
        adj = PolicyAdjuster(enforce_mode="enforce", enforce_whitelist=["model.default_name"])
        adj.register_apply_handler("model.default_name", lambda c: None)
        adj.unregister_apply_handler("model.default_name")
        assert "model.default_name" not in adj._apply_handlers


# ── 3. policy_handlers.handle_model_default_name ──────────

class TestModelDefaultNameHandler:
    def test_handler_swaps_model_selector_spec(self):
        """官方 handler 应改 ModelSelector PRIMARY 的 model_name 并清缓存。"""
        from backend.core.model_selector import model_selector, ModelRole
        # 确保 initialized
        model_selector.initialize()
        original = model_selector.get_spec(ModelRole.PRIMARY).model_name

        # 构造一个模拟 change
        from backend.governance.policy_center.policy_adjuster import PolicyChange
        c = PolicyChange(
            change_id="test-c1",
            suggested_at=time.time(),
            expires_at=time.time() + 3600,
            policy_key="model.default_name",
            new_value="qwen-ultra-fake",
            old_value=original,
        )
        handle_model_default_name(c)
        try:
            assert model_selector.get_spec(ModelRole.PRIMARY).model_name == "qwen-ultra-fake"
        finally:
            # 恢复原值避免污染后续测试
            c_restore = PolicyChange(
                change_id="test-c1r",
                suggested_at=time.time(),
                expires_at=time.time() + 3600,
                policy_key="model.default_name",
                new_value=original,
                old_value="qwen-ultra-fake",
            )
            handle_model_default_name(c_restore)

    def test_register_default_handlers_registers_model(self):
        adj = PolicyAdjuster()
        assert "model.default_name" not in adj._apply_handlers
        register_default_handlers(adj)
        assert "model.default_name" in adj._apply_handlers

    def test_handler_invalid_new_value_skip(self, caplog):
        """new_value 不是字符串 → 直接跳过，不抛异常。"""
        from backend.governance.policy_center.policy_adjuster import PolicyChange
        c = PolicyChange(
            change_id="test-bad",
            suggested_at=time.time(),
            expires_at=time.time() + 3600,
            policy_key="model.default_name",
            new_value=None,
            old_value="x",
        )
        # 应不抛异常
        handle_model_default_name(c)


# ── 4. Evaluator + Adjuster DB persist 尝试 ──────────────

class TestEvaluatorDbPersist:
    def test_configure_method_sets_factory(self):
        ev = PeriodicEvaluator()
        assert ev._db_factory is None
        fake_factory = MagicMock()
        ev.configure(db_session_factory=fake_factory)
        assert ev._db_factory is fake_factory

    def test_persist_swallows_db_exceptions(self):
        """_persist_to_db 异常不向上抛。"""
        ev = PeriodicEvaluator()
        ev.configure(db_session_factory=MagicMock(side_effect=Exception("down")))
        # 直接调内部方法
        v = EvalVerdict(
            metric="x", subject="y", value=0, threshold_warning=0,
            threshold_critical=0, status="normal",
            sample_size=10, window_seconds=300, timestamp=time.time(),
        )
        ev._persist_to_db([v])  # 不应抛


class TestAdjusterDbPersist:
    def test_configure_method_sets_factory(self):
        adj = PolicyAdjuster()
        assert adj._db_factory is None
        fake_factory = MagicMock()
        adj.configure(db_session_factory=fake_factory)
        assert adj._db_factory is fake_factory

    def test_persist_swallows_db_exceptions(self):
        adj = PolicyAdjuster()
        adj.configure(db_session_factory=MagicMock(side_effect=Exception("db down")))
        from backend.governance.policy_center.policy_adjuster import PolicyChange
        c = PolicyChange(
            change_id="p-1",
            suggested_at=time.time(),
            expires_at=time.time() + 60,
            policy_key="model.default_name",
            new_value="qwen-turbo",
        )
        adj._persist_changes([c])  # 不应抛
