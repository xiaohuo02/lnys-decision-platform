# -*- coding: utf-8 -*-
"""backend/tests/test_r6_eval_policy.py — R6-5 Eval + Policy 闭环单元测试

覆盖:
  1. PeriodicEvaluator:
     - 空 telemetry → 空 verdicts
     - skill_hit_rate: 正常 / 低于 warning / 低于 critical
     - tool_timeout_rate: 超时聚合
     - model_latency_p95: 按 model 分组 + p95 计算
     - pii_block_rate: block 与 pass 的比例
     - 样本量不足 → status="insufficient"
  2. PolicyAdjuster:
     - normal verdict → 无 change
     - warning verdict + 匹配 handler → 产出 suggested change (shadow)
     - enforce mode + whitelist → change.applied=True
     - 非 whitelist key → 退回 shadow
     - TTL 过期 → rolled_back=True
  3. 端到端: 手动 emit telemetry → evaluate → process → 新一轮事件发出
"""
from __future__ import annotations

import os
import sys
import time
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.core.telemetry import telemetry, TelemetryEventType  # noqa: E402
from backend.governance.eval_center.periodic_evaluator import (  # noqa: E402
    PeriodicEvaluator,
    EvalVerdict,
    DEFAULT_THRESHOLDS,
    MIN_SAMPLE_SIZE,
)
from backend.governance.policy_center.policy_adjuster import (  # noqa: E402
    PolicyAdjuster,
    PolicyChange,
    DEFAULT_TTL_SECONDS,
)


# ── Fixtures ─────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_telemetry():
    """每个测试前清空 telemetry ring buffer。"""
    telemetry.clear()
    yield
    telemetry.clear()


def _emit_events(events: list) -> None:
    """批量 emit 测试用 telemetry 事件。

    events: [(event_type, data, component), ...]
    """
    for evt_type, data, component in events:
        telemetry.emit(evt_type, data or {}, component=component or "test")


# ── 测试 1: PeriodicEvaluator 空数据 ─────────────────────

class TestEvaluatorEmpty:
    def test_empty_telemetry_yields_no_verdict(self):
        ev = PeriodicEvaluator()
        verdicts = ev.evaluate(window_seconds=300)
        assert verdicts == []

    def test_clear_wipes_buffer(self):
        ev = PeriodicEvaluator()
        _emit_events([(TelemetryEventType.RUN_STARTED, {}, "engine")] * 10)
        _emit_events([(TelemetryEventType.SKILL_EXECUTED, {}, "engine")] * 8)
        ev.evaluate(window_seconds=300)
        assert len(ev.verdicts) > 0
        ev.clear()
        assert ev.verdicts == []


# ── 测试 2: skill_hit_rate ──────────────────────────────

class TestSkillHitRate:
    def test_high_hit_rate_normal(self):
        ev = PeriodicEvaluator()
        _emit_events([(TelemetryEventType.RUN_STARTED, {}, "engine")] * 10)
        _emit_events([(TelemetryEventType.SKILL_EXECUTED, {"skill": "x"}, "engine")] * 9)
        verdicts = ev.evaluate(window_seconds=300)

        hit = [v for v in verdicts if v.metric == "skill_hit_rate_5m"]
        assert len(hit) == 1
        assert hit[0].value == 0.9
        assert hit[0].status == "normal"
        assert hit[0].recommendation == ""

    def test_low_hit_rate_triggers_critical(self):
        ev = PeriodicEvaluator()
        _emit_events([(TelemetryEventType.RUN_STARTED, {}, "engine")] * 10)
        # 只有 2 次 skill_executed → hit_rate=0.2 < critical 0.3
        _emit_events([(TelemetryEventType.SKILL_EXECUTED, {"skill": "x"}, "engine")] * 2)
        verdicts = ev.evaluate(window_seconds=300)

        hit = [v for v in verdicts if v.metric == "skill_hit_rate_5m"][0]
        assert hit.value == 0.2
        assert hit.status == "critical"
        assert hit.recommendation == "enhance_keyword_fallback"

    def test_insufficient_sample(self):
        """样本量 < MIN_SAMPLE_SIZE → insufficient, 不报警。"""
        ev = PeriodicEvaluator()
        _emit_events([(TelemetryEventType.RUN_STARTED, {}, "engine")] * 2)
        _emit_events([(TelemetryEventType.SKILL_EXECUTED, {}, "engine")] * 1)
        verdicts = ev.evaluate(window_seconds=300)

        hit = [v for v in verdicts if v.metric == "skill_hit_rate_5m"][0]
        assert hit.sample_size == 2
        assert hit.status == "insufficient"
        assert hit.recommendation == ""


# ── 测试 3: tool_timeout_rate ───────────────────────────

class TestToolTimeoutRate:
    def test_no_timeouts_normal(self):
        ev = PeriodicEvaluator()
        _emit_events([(TelemetryEventType.SKILL_EXECUTED, {"skill": "x"}, "engine")] * 10)
        verdicts = ev.evaluate(window_seconds=300)
        tto = [v for v in verdicts if v.metric == "tool_timeout_rate_5m"][0]
        assert tto.value == 0.0
        assert tto.status == "normal"

    def test_high_timeout_triggers_warning(self):
        ev = PeriodicEvaluator()
        # 10 个 skill_executed，其中 2 个超时 → 0.20 > critical 0.15
        _emit_events([(TelemetryEventType.SKILL_EXECUTED, {"skill": "x"}, "engine")] * 8)
        _emit_events([
            (TelemetryEventType.SKILL_EXECUTED, {"skill": "x", "error": "timeout"}, "engine")
        ] * 2)
        verdicts = ev.evaluate(window_seconds=300)
        tto = [v for v in verdicts if v.metric == "tool_timeout_rate_5m"][0]
        assert tto.value == 0.2
        assert tto.status == "critical"
        assert tto.recommendation == "extend_skill_timeout"


# ── 测试 4: model_latency_p95 ───────────────────────────

class TestModelLatencyP95:
    def test_per_model_grouping(self):
        ev = PeriodicEvaluator()
        # qwen-plus: 10 次，latency 递增 100/200/.../1000
        for i in range(10):
            telemetry.emit(
                TelemetryEventType.MODEL_COMPLETED,
                {"model": "qwen-plus", "latency_ms": (i + 1) * 100},
                component="engine",
            )
        # qwen-turbo: 10 次低延迟
        for _ in range(10):
            telemetry.emit(
                TelemetryEventType.MODEL_COMPLETED,
                {"model": "qwen-turbo", "latency_ms": 50},
                component="engine",
            )
        verdicts = ev.evaluate(window_seconds=300)
        latency_verdicts = [v for v in verdicts if v.metric == "model_latency_p95_5m"]
        subjects = {v.subject for v in latency_verdicts}
        assert "qwen-plus" in subjects
        assert "qwen-turbo" in subjects

    def test_critical_triggers_downgrade(self):
        ev = PeriodicEvaluator()
        # 生成 10 个 > 8000ms 的延迟（超过 critical）
        for _ in range(10):
            telemetry.emit(
                TelemetryEventType.MODEL_COMPLETED,
                {"model": "qwen-plus", "latency_ms": 9000},
                component="engine",
            )
        verdicts = ev.evaluate(window_seconds=300)
        v = [v for v in verdicts if v.metric == "model_latency_p95_5m"][0]
        assert v.subject == "qwen-plus"
        assert v.status == "critical"
        assert v.recommendation.startswith("model_downgrade:")


# ── 测试 5: pii_block_rate ──────────────────────────────

class TestPiiBlockRate:
    def test_high_block_triggers_relax(self):
        ev = PeriodicEvaluator()
        # 5 passed + 5 blocked → rate=0.5 > critical 0.50
        _emit_events([
            (TelemetryEventType.SECURITY_CHECK_PASSED, {}, "guard")
        ] * 5)
        _emit_events([
            (TelemetryEventType.SECURITY_CHECK_BLOCKED, {}, "guard")
        ] * 5)
        verdicts = ev.evaluate(window_seconds=300)
        pb = [v for v in verdicts if v.metric == "pii_block_rate_5m"][0]
        assert pb.value == 0.5
        assert pb.status == "critical"
        assert pb.recommendation == "relax_pii_rules"


# ── 测试 6: PolicyAdjuster shadow → enforce ─────────────

class TestPolicyAdjusterShadow:
    def _make_verdict(self, metric: str, recommendation: str, value: float = 0.9) -> EvalVerdict:
        return EvalVerdict(
            metric=metric, subject="qwen-plus",
            value=value,
            threshold_warning=0.5, threshold_critical=0.3,
            status="critical",
            sample_size=10,
            window_seconds=300,
            timestamp=time.time(),
            recommendation=recommendation,
        )

    def test_normal_verdict_produces_no_change(self):
        adj = PolicyAdjuster()
        normal = EvalVerdict(
            metric="x", subject="y", value=0.99,
            threshold_warning=0.5, threshold_critical=0.3,
            status="normal", sample_size=10,
            window_seconds=300, timestamp=time.time(),
            recommendation="",
        )
        changes = adj.process([normal])
        assert changes == []

    def test_critical_verdict_in_shadow_not_applied(self):
        adj = PolicyAdjuster(enforce_mode="shadow")
        adj.clear()
        v = self._make_verdict(
            "model_latency_p95_5m",
            "model_downgrade:qwen-plus",
            value=9000,
        )
        changes = adj.process([v])
        assert len(changes) == 1
        c = changes[0]
        assert c.policy_key == "model.default_name"
        assert c.mode == "shadow"
        assert c.applied is False
        assert c.new_value  # 非空
        assert c.expires_at > c.suggested_at

    def test_enforce_mode_with_whitelist_applies(self):
        adj = PolicyAdjuster(
            enforce_mode="enforce",
            enforce_whitelist=["model.default_name"],
        )
        adj.clear()
        v = self._make_verdict(
            "model_latency_p95_5m",
            "model_downgrade:qwen-plus",
            value=9000,
        )
        changes = adj.process([v])
        assert len(changes) == 1
        c = changes[0]
        assert c.mode == "enforce"
        assert c.applied is True
        assert c.applied_at is not None

    def test_enforce_mode_key_not_in_whitelist_fallback_to_shadow(self):
        """enforce mode 但目标 key 不在 whitelist → 退回 shadow。"""
        adj = PolicyAdjuster(
            enforce_mode="enforce",
            enforce_whitelist=["input_guard.pii_threshold"],  # 仅允许 PII 放宽
        )
        adj.clear()
        v = self._make_verdict(
            "model_latency_p95_5m",
            "model_downgrade:qwen-plus",
            value=9000,
        )
        changes = adj.process([v])
        assert len(changes) == 1
        assert changes[0].mode == "shadow"
        assert changes[0].applied is False

    def test_unknown_recommendation_ignored(self):
        adj = PolicyAdjuster()
        v = self._make_verdict("x", "unknown_rec_key", value=1)
        changes = adj.process([v])
        assert changes == []


# ── 测试 7: TTL 回滚 ───────────────────────────────────

class TestPolicyAdjusterTTL:
    def test_rollback_after_ttl_expires(self):
        adj = PolicyAdjuster(
            enforce_mode="enforce",
            enforce_whitelist=["model.default_name"],
        )
        adj.clear()
        v = EvalVerdict(
            metric="model_latency_p95_5m", subject="qwen-plus",
            value=9000,
            threshold_warning=5000, threshold_critical=8000,
            status="critical", sample_size=10,
            window_seconds=300, timestamp=time.time(),
            recommendation="model_downgrade:qwen-plus",
        )
        changes = adj.process([v])
        c = changes[0]
        assert c.applied is True
        assert c.rolled_back is False

        # 人为把 expires_at 往前挪
        c.expires_at = time.time() - 1

        # 再走一次 process（即便没新 verdict, rollback 逻辑也会跑）
        adj.process([])
        assert c.rolled_back is True
        assert c.rolled_back_at is not None

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError):
            PolicyAdjuster(enforce_mode="invalid")

    def test_set_mode_runtime(self):
        adj = PolicyAdjuster()
        assert adj.mode == "shadow"
        adj.set_mode("enforce")
        assert adj.mode == "enforce"
        with pytest.raises(ValueError):
            adj.set_mode("bad")


# ── 测试 8: 端到端 evaluate → process ───────────────────

class TestEndToEndLoop:
    def test_eval_feeds_policy_adjuster(self):
        """模拟: telemetry 事件 → evaluate 产出 verdict → PolicyAdjuster 消费。"""
        # 造一个 model_latency_p95 > critical 的场景
        for _ in range(10):
            telemetry.emit(
                TelemetryEventType.MODEL_COMPLETED,
                {"model": "qwen-plus", "latency_ms": 9500},
                component="engine",
            )

        ev = PeriodicEvaluator()
        verdicts = ev.evaluate(window_seconds=300)
        assert any(
            v.metric == "model_latency_p95_5m" and v.status == "critical"
            for v in verdicts
        )

        adj = PolicyAdjuster(
            enforce_mode="enforce",
            enforce_whitelist=["model.default_name"],
        )
        adj.clear()
        changes = adj.process(verdicts)
        # 至少一条 model.default_name 被 applied
        applied = [c for c in changes if c.policy_key == "model.default_name" and c.applied]
        assert len(applied) >= 1
