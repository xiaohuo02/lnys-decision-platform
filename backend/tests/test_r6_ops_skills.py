# -*- coding: utf-8 -*-
"""backend/tests/test_r6_ops_skills.py — R6-3 扩展 ops Skill 单元测试

覆盖三个从 ops_copilot_agent 抽出的 Skill:
  - prompt_query_skill (prompts 表)
  - release_query_skill (releases 表)
  - review_query_skill (review_cases 表)

策略与 test_r6_eval_query_skill.py 一致: mock async db 直调 _dispatch。
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.copilot.skills.prompt_query_skill import PromptQuerySkill  # noqa: E402
from backend.copilot.skills.release_query_skill import ReleaseQuerySkill  # noqa: E402
from backend.copilot.skills.review_query_skill import ReviewQuerySkill  # noqa: E402
from backend.copilot.events import EventType  # noqa: E402


# ── helpers ───────────────────────────────────────────────

class _FakeResult:
    def __init__(self, rows=None, single_row=None):
        self._rows = rows or []
        self._single = single_row

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._single


def _fake_db(results: list):
    """results: 按 execute 调用顺序的返回值列表。"""
    db = MagicMock()
    db.execute = AsyncMock(side_effect=results)
    return db


def _text(sql):
    return sql


# ── prompt_query_skill ────────────────────────────────────

class TestPromptQuerySkill:
    def test_metadata(self):
        s = PromptQuerySkill()
        assert s.name == "prompt_query_skill"
        assert s.mode == {"ops"}
        schema = s.to_function_schema()
        enum = schema["function"]["parameters"]["properties"]["query_type"]["enum"]
        assert set(enum) == {"recent_published", "version_count"}

    @pytest.mark.asyncio
    async def test_recent_published(self):
        ts = datetime(2026, 3, 1, 10, 0, 0)
        rows = [
            ("prompt_a", "agent_1", "v3", ts),
            ("prompt_b", "agent_2", "v1", ts),
        ]
        db = _fake_db([_FakeResult(rows=rows)])
        skill = PromptQuerySkill()
        data, title = await skill._dispatch(db, _text, "recent_published", limit=5)
        assert len(data) == 2
        assert data[0]["name"] == "prompt_a"
        assert data[0]["agent_name"] == "agent_1"
        assert data[0]["version"] == "v3"
        assert "2 条" in title

    @pytest.mark.asyncio
    async def test_version_count(self):
        rows = [("prompt_x", 5), ("prompt_y", 2)]
        db = _fake_db([_FakeResult(rows=rows)])
        skill = PromptQuerySkill()
        data, title = await skill._dispatch(db, _text, "version_count", limit=5)
        assert len(data) == 2
        assert data[0] == {"name": "prompt_x", "version_count": 5}
        assert "Top 2" in title


# ── release_query_skill ──────────────────────────────────

class TestReleaseQuerySkill:
    def test_metadata(self):
        s = ReleaseQuerySkill()
        assert s.name == "release_query_skill"
        schema = s.to_function_schema()
        enum = schema["function"]["parameters"]["properties"]["query_type"]["enum"]
        assert set(enum) == {"recent_releases", "last_rollback"}

    @pytest.mark.asyncio
    async def test_recent_releases(self):
        ts = datetime(2026, 3, 2, 11, 0, 0)
        rows = [("rel-1", "web-ui", "v2.1", "active", "admin", ts)]
        db = _fake_db([_FakeResult(rows=rows)])
        skill = ReleaseQuerySkill()
        data, title = await skill._dispatch(db, _text, "recent_releases", limit=5)
        assert len(data) == 1
        assert data[0]["status"] == "active"
        assert data[0]["released_by"] == "admin"
        assert "1 条" in title

    @pytest.mark.asyncio
    async def test_last_rollback_found(self):
        ts = datetime(2026, 3, 2, 15, 0, 0)
        row = ("rel-rb-01", "backend", "v3.0", "admin", ts)
        db = _fake_db([_FakeResult(single_row=row)])
        skill = ReleaseQuerySkill()
        data, title = await skill._dispatch(db, _text, "last_rollback", limit=1)
        assert data["release_id"] == "rel-rb-01"
        assert "backend" in title

    @pytest.mark.asyncio
    async def test_last_rollback_none(self):
        db = _fake_db([_FakeResult(single_row=None)])
        skill = ReleaseQuerySkill()
        data, title = await skill._dispatch(db, _text, "last_rollback", limit=1)
        assert "note" in data
        assert "无" in title


# ── review_query_skill ───────────────────────────────────

class TestReviewQuerySkill:
    def test_metadata(self):
        s = ReviewQuerySkill()
        assert s.name == "review_query_skill"

    @pytest.mark.asyncio
    async def test_dispatch_stats_and_recent(self):
        # 第 1 次 execute: stats (single_row)
        # 第 2 次 execute: recent (rows)
        stats_row = (20, 5, 3, 10, 2)
        ts = datetime(2026, 3, 3, 9, 0, 0)
        recent_rows = [
            ("case-A", "fraud", "high", "pending", "可疑交易审查", ts),
            ("case-B", "refund", "low", "in_review", "退款申请", ts),
        ]
        db = _fake_db([
            _FakeResult(single_row=stats_row),
            _FakeResult(rows=recent_rows),
        ])
        skill = ReviewQuerySkill()
        data, title = await skill._dispatch(db, _text, limit=5)

        assert data["stats"]["total"] == 20
        assert data["stats"]["pending"] == 5
        assert data["stats"]["in_review"] == 3
        assert data["stats"]["approved"] == 10
        assert data["stats"]["rejected"] == 2
        assert len(data["recent"]) == 2
        assert data["recent"][0]["priority"] == "high"
        assert "5 待审" in title

    @pytest.mark.asyncio
    async def test_dispatch_empty_stats(self):
        db = _fake_db([
            _FakeResult(single_row=(0, 0, 0, 0, 0)),
            _FakeResult(rows=[]),
        ])
        skill = ReviewQuerySkill()
        data, title = await skill._dispatch(db, _text, limit=5)
        assert data["stats"]["total"] == 0
        assert data["recent"] == []
        assert "0 待审" in title


# ── execute 降级事件序列 ───────────────────────────────

class TestExecuteFallback:
    @pytest.mark.asyncio
    async def test_prompt_skill_execute_fallback(self, monkeypatch):
        from backend.copilot.base_skill import SkillContext
        import backend.database as _db
        monkeypatch.setattr(_db, "_get_async_engine", lambda: (_ for _ in ()).throw(RuntimeError("no db")))

        skill = PromptQuerySkill()
        ctx = SkillContext(
            user_id="u1", user_role="super_admin",
            mode="ops", thread_id="t1",
            tool_args={"query_type": "recent_published"},
        )
        events = [e async for e in skill.execute("最近 prompt", ctx)]
        types = [e.type for e in events]
        assert EventType.ARTIFACT_START in types
        assert EventType.ARTIFACT_END in types
        assert EventType.TOOL_RESULT in types
        tool = [e for e in events if e.type == EventType.TOOL_RESULT][0]
        assert "error" in tool.data
