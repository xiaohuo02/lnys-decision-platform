# -*- coding: utf-8 -*-
"""backend/tests/test_r6_eval_query_skill.py — R6-3 EvalQuerySkill 单元测试

示范 R6-3 做法:
  - 从 ops_copilot_agent 抽出的 Skill 必须保持行为一致
  - 用 agent_snapshot helper 固化输出结构（golden file 回归兜底）
  - 单元测试不依赖真实 MySQL（mock async session）

Tests:
  1. Skill 元数据正确
  2. _dispatch(query_type='recent') 转换 row → 结构化列表
  3. _dispatch(query_type='lowest_pass') pass_rate < 0.7 标高风险
  4. _dispatch(query_type='lowest_pass') 无数据时的降级
  5. _dispatch(query_type='summary') 统计聚合
  6. 全流程事件序列（execute）
  7. agent_snapshot: 对 _dispatch 输出结构做 golden file 固化
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.copilot.skills.eval_query_skill import EvalQuerySkill  # noqa: E402
from backend.copilot.events import EventType  # noqa: E402
from backend.tests.helpers.agent_snapshot import assert_matches_snapshot  # noqa: E402


# ── Helpers: Mock async DB ───────────────────────────────────

class _FakeResult:
    def __init__(self, rows=None, single_row=None):
        self._rows = rows or []
        self._single = single_row

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._single


def _make_fake_db(result_factory):
    """result_factory: callable(sql_text, params) -> _FakeResult"""
    db = MagicMock()
    db.execute = AsyncMock(side_effect=result_factory)
    return db


def _text_stub(sql_str):
    """伪 sqlalchemy.text — 测试中不执行 SQL，只要 identity 传递。"""
    return sql_str


# ── 测试 1: Skill 元数据 ───────────────────────────────────

class TestEvalQuerySkillMetadata:
    def test_basic_attrs(self):
        skill = EvalQuerySkill()
        assert skill.name == "eval_query_skill"
        assert skill.mode == {"ops"}
        assert "ops_analyst" in skill.required_roles
        assert "super_admin" in skill.required_roles
        assert skill.summarization_hint  # 非空

    def test_function_schema(self):
        schema = EvalQuerySkill().to_function_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "eval_query_skill"
        # enum 覆盖 3 种 query_type
        enum_values = schema["function"]["parameters"]["properties"]["query_type"]["enum"]
        assert set(enum_values) == {"recent", "lowest_pass", "summary"}

    def test_is_available_ops_only(self):
        skill = EvalQuerySkill()
        # ops 模式 + 合法角色
        assert skill.is_available("ops", "super_admin") is True
        assert skill.is_available("ops", "platform_admin") is True
        # ops 模式但角色不匹配
        assert skill.is_available("ops", "biz_viewer") is False
        # biz 模式 → 不可用
        assert skill.is_available("biz", "super_admin") is False


# ── 测试 2: _dispatch recent ────────────────────────────────

class TestDispatchRecent:
    @pytest.mark.asyncio
    async def test_recent_converts_rows(self):
        ts = datetime(2026, 1, 1, 12, 0, 0)
        fake_rows = [
            ("exp-001", "test_a", "completed", 0.85, ts),
            ("exp-002", "test_b", "running", None, ts),
        ]
        db = _make_fake_db(lambda *a, **kw: _FakeResult(rows=fake_rows))
        skill = EvalQuerySkill()
        data, title = await skill._dispatch(db, _text_stub, "recent", limit=5)

        assert title == "最近的评测实验 — 2 条"
        assert len(data) == 2
        assert data[0]["experiment_id"] == "exp-001"
        assert data[0]["pass_rate"] == 0.85
        assert data[1]["pass_rate"] is None  # running 时 pass_rate 可能为 None
        db.execute.assert_awaited_once()


# ── 测试 3: _dispatch lowest_pass ───────────────────────────

class TestDispatchLowestPass:
    @pytest.mark.asyncio
    async def test_lowest_pass_marks_high_risk_below_threshold(self):
        ts = datetime(2026, 1, 5, 10, 0, 0)
        fake_row = ("exp-xx", "acc_test", 0.55, ts)
        db = _make_fake_db(lambda *a, **kw: _FakeResult(single_row=fake_row))
        skill = EvalQuerySkill()
        data, title = await skill._dispatch(db, _text_stub, "lowest_pass", limit=1)

        assert "acc_test" in title
        assert data["pass_rate"] == 0.55
        assert data["risk_level"] == "high"  # < 0.7

    @pytest.mark.asyncio
    async def test_lowest_pass_normal_above_threshold(self):
        ts = datetime(2026, 1, 5, 10, 0, 0)
        fake_row = ("exp-zz", "stable_test", 0.88, ts)
        db = _make_fake_db(lambda *a, **kw: _FakeResult(single_row=fake_row))
        skill = EvalQuerySkill()
        data, _ = await skill._dispatch(db, _text_stub, "lowest_pass", limit=1)

        assert data["risk_level"] == "normal"

    @pytest.mark.asyncio
    async def test_lowest_pass_no_data(self):
        db = _make_fake_db(lambda *a, **kw: _FakeResult(single_row=None))
        skill = EvalQuerySkill()
        data, title = await skill._dispatch(db, _text_stub, "lowest_pass", limit=1)

        assert "无数据" in title
        assert "error" in data


# ── 测试 4: _dispatch summary ──────────────────────────────

class TestDispatchSummary:
    @pytest.mark.asyncio
    async def test_summary_computes_completion_rate(self):
        # (total, completed, avg_pass)
        fake_row = (12, 8, 0.76)
        db = _make_fake_db(lambda *a, **kw: _FakeResult(single_row=fake_row))
        skill = EvalQuerySkill()
        data, title = await skill._dispatch(db, _text_stub, "summary", limit=0)

        assert data["period"] == "30d"
        assert data["total"] == 12
        assert data["completed"] == 8
        assert abs(data["completion_rate"] - (8 / 12)) < 1e-9
        assert data["avg_pass_rate"] == 0.76
        assert "统计" in title

    @pytest.mark.asyncio
    async def test_summary_no_data_returns_zero(self):
        fake_row = (None, None, None)
        db = _make_fake_db(lambda *a, **kw: _FakeResult(single_row=fake_row))
        skill = EvalQuerySkill()
        data, _ = await skill._dispatch(db, _text_stub, "summary", limit=0)

        assert data["total"] == 0
        assert data["completed"] == 0
        assert data["completion_rate"] == 0.0
        assert data["avg_pass_rate"] is None


# ── 测试 5: 全流程 execute 事件序列 ───────────────────────

class TestEvalQuerySkillExecute:
    @pytest.mark.asyncio
    async def test_execute_emits_expected_events_on_error(self, monkeypatch):
        """DB 初始化失败 → 走降级分支，仍产出 artifact + tool_result 事件。"""
        from backend.copilot.base_skill import SkillContext

        skill = EvalQuerySkill()
        # 让 database 初始化抛异常 → 进入 except 降级
        import backend.database as _db
        monkeypatch.setattr(_db, "_get_async_engine", lambda: (_ for _ in ()).throw(RuntimeError("no db")))

        ctx = SkillContext(
            user_id="u1", user_role="super_admin",
            mode="ops", thread_id="t1",
            tool_args={"query_type": "summary"},
        )
        events = [e async for e in skill.execute("查一下评测", ctx)]
        types = [e.type for e in events]

        assert EventType.ARTIFACT_START in types
        assert EventType.ARTIFACT_DELTA in types
        assert EventType.ARTIFACT_END in types
        assert EventType.SUGGESTIONS in types
        assert EventType.TOOL_RESULT in types
        # 降级分支 data 含 error 字段
        tool_result_events = [e for e in events if e.type == EventType.TOOL_RESULT]
        assert "error" in tool_result_events[0].data


# ── 测试 6: agent_snapshot 固化输出 ───────────────────────

class TestEvalQuerySkillSnapshots:
    """用 snapshot helper 固化 _dispatch 输出结构，作为 R6-3 回归兜底。"""

    @pytest.mark.asyncio
    async def test_snapshot_recent_output_shape(self):
        ts = datetime(2026, 2, 10, 9, 0, 0)
        fake_rows = [
            ("exp-A", "inventory_v1", "completed", 0.92, ts),
            ("exp-B", "forecast_v2", "failed", 0.0, ts),
        ]
        db = _make_fake_db(lambda *a, **kw: _FakeResult(rows=fake_rows))
        skill = EvalQuerySkill()
        data, title = await skill._dispatch(db, _text_stub, "recent", limit=5)

        assert_matches_snapshot(
            actual={"title": title, "data": data},
            snapshot_name="eval_query_skill_recent",
        )

    @pytest.mark.asyncio
    async def test_snapshot_lowest_pass_high_risk(self):
        ts = datetime(2026, 2, 10, 9, 0, 0)
        fake_row = ("exp-risk", "critical_eval", 0.45, ts)
        db = _make_fake_db(lambda *a, **kw: _FakeResult(single_row=fake_row))
        skill = EvalQuerySkill()
        data, title = await skill._dispatch(db, _text_stub, "lowest_pass", limit=1)

        assert_matches_snapshot(
            actual={"title": title, "data": data},
            snapshot_name="eval_query_skill_lowest_pass_high_risk",
        )

    @pytest.mark.asyncio
    async def test_snapshot_summary(self):
        fake_row = (20, 15, 0.82)
        db = _make_fake_db(lambda *a, **kw: _FakeResult(single_row=fake_row))
        skill = EvalQuerySkill()
        data, title = await skill._dispatch(db, _text_stub, "summary", limit=0)

        assert_matches_snapshot(
            actual={"title": title, "data": data},
            snapshot_name="eval_query_skill_summary",
        )
