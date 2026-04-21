# -*- coding: utf-8 -*-
"""§3.4 KB 反馈闭环 · 单元 + 路由 smoke 测试。

覆盖范围
--------
1. ``KBFeedbackService.submit``
   - 无 trace_id：直接 insert
   - 有 trace_id 且 24h 内已存在：走 update 分支
   - 有 trace_id 但库内不存在：仍走 insert
   - citations 序列化（list[dict] → JSON 字符串）
2. ``KBFeedbackService.list``
   - 过滤参数拼接（rating / kb_id / source / days）
   - citations 反序列化（JSON 字符串 → list[dict]）
3. ``KBFeedbackService.stats``
   - 分布、negative_rate、分库 / 分原因 / 分来源
4. router smoke
   - POST /api/kb/feedback 鉴权 + 落库
   - GET /admin/knowledge/v2/feedback / stats 鉴权
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest


# ════════════════════════════════════════════════════════════════════
# Mock 基础组件
# ════════════════════════════════════════════════════════════════════


class _Row:
    def __init__(self, mapping: Dict[str, Any]):
        self._mapping = mapping


class _StubResult:
    """SQLAlchemy CursorResult 的最小可用替身。"""

    def __init__(
        self,
        rows: Optional[List[_Row]] = None,
        scalar_value: Any = None,
        lastrowid: int = 0,
    ):
        self._rows = rows or []
        self._scalar = scalar_value
        self.lastrowid = lastrowid

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return self._scalar


class _ScriptedSession:
    """按 SQL 关键字脚本化返回结果。

    ``script`` 形如 ``[{"contains": "SELECT feedback_id", "result": _StubResult(...)}, ...]``
    每次 execute 找第一个匹配的 entry；没匹配则返回空 result。
    """

    def __init__(self, script: List[Dict[str, Any]]):
        self.script = list(script)
        self.calls: List[Dict[str, Any]] = []
        self.commits = 0
        self.rollbacks = 0

    def execute(self, sql, params=None):
        sql_str = str(sql)
        self.calls.append({"sql": sql_str, "params": params or {}})
        for entry in self.script:
            if entry["contains"] in sql_str:
                if entry.get("once"):
                    entry["used"] = True
                return entry["result"]
        return _StubResult()

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


# ════════════════════════════════════════════════════════════════════
# Service: submit
# ════════════════════════════════════════════════════════════════════


class TestFeedbackSubmit:
    def setup_method(self):
        from backend.knowledge.feedback_service import KBFeedbackService
        self.svc = KBFeedbackService.get_instance()

    def test_insert_when_no_trace_id(self):
        db = _ScriptedSession([
            {"contains": "INSERT INTO kb_feedback",
             "result": _StubResult(lastrowid=42)},
        ])
        out = self.svc.submit(
            db,
            user_id="u1",
            query="退款多久到账",
            rating=-1,
            rating_reason="inaccurate",
            free_text="给的答案是 7 天，实际 1-3",
            source="biz_kb",
        )
        assert out == {"feedback_id": 42, "action": "insert"}
        assert db.commits == 1
        # 没 trace_id 不应触发 SELECT 查询
        assert not any("SELECT feedback_id FROM kb_feedback" in c["sql"] for c in db.calls)

    def test_upsert_update_branch_when_trace_exists(self):
        db = _ScriptedSession([
            {"contains": "SELECT feedback_id FROM kb_feedback",
             "result": _StubResult(rows=[_Row({"feedback_id": 7})])},
            {"contains": "UPDATE kb_feedback",
             "result": _StubResult()},
        ])
        out = self.svc.submit(
            db,
            user_id="u1",
            query="退款多久到账",
            rating=1,
            trace_id="trace-abc",
            kb_id="kb-1",
            source="biz_kb",
        )
        assert out == {"feedback_id": 7, "action": "update"}
        assert db.commits == 1
        upd = next(c for c in db.calls if c["sql"].startswith("UPDATE kb_feedback"))
        assert upd["params"]["fid"] == 7
        assert upd["params"]["r"] == 1

    def test_upsert_insert_branch_when_trace_not_found(self):
        db = _ScriptedSession([
            {"contains": "SELECT feedback_id FROM kb_feedback",
             "result": _StubResult(rows=[])},
            {"contains": "INSERT INTO kb_feedback",
             "result": _StubResult(lastrowid=11)},
        ])
        out = self.svc.submit(
            db,
            user_id="u1",
            query="开通流程",
            rating=0,
            trace_id="trace-xyz",
        )
        assert out == {"feedback_id": 11, "action": "insert"}

    def test_citations_json_serialized(self):
        captured: Dict[str, Any] = {}

        def _exec(sql, params=None):
            captured["params"] = params
            return _StubResult(lastrowid=1)

        db = MagicMock()
        db.execute = MagicMock(side_effect=_exec)
        db.commit = MagicMock()
        self.svc.submit(
            db,
            user_id="u1",
            query="q",
            rating=-1,
            citations=[{"document_id": "d1", "chunk_id": "c1", "kb_id": "kb1",
                        "title": "退款政策", "score": 0.81}],
        )
        # citations 应被序列化成 JSON 字符串
        c_str = captured["params"]["c"]
        assert isinstance(c_str, str)
        parsed = json.loads(c_str)
        assert parsed[0]["document_id"] == "d1"


# ════════════════════════════════════════════════════════════════════
# Service: list
# ════════════════════════════════════════════════════════════════════


class TestFeedbackList:
    def setup_method(self):
        from backend.knowledge.feedback_service import KBFeedbackService
        self.svc = KBFeedbackService.get_instance()

    def test_list_with_filters_and_citations_decoded(self):
        db = _ScriptedSession([
            {"contains": "SELECT COUNT(*) FROM kb_feedback",
             "result": _StubResult(scalar_value=2)},
            {"contains": "SELECT feedback_id, trace_id, user_id",
             "result": _StubResult(rows=[
                 _Row({
                     "feedback_id": 10, "trace_id": "t1", "user_id": "u1",
                     "kb_id": "kb1", "query": "q1", "answer": "a1",
                     "citations": json.dumps([{"document_id": "d1"}]),
                     "rating": -1, "rating_reason": "inaccurate",
                     "free_text": None, "source": "biz_kb",
                     "created_at": None,
                 }),
                 _Row({
                     "feedback_id": 9, "trace_id": None, "user_id": "u2",
                     "kb_id": "kb1", "query": "q2", "answer": None,
                     "citations": None,
                     "rating": -1, "rating_reason": None,
                     "free_text": "差评", "source": "biz_kb",
                     "created_at": None,
                 }),
             ])},
        ])
        result = self.svc.list(
            db, rating=-1, kb_id="kb1", source="biz_kb",
            days=14, limit=20, offset=0,
        )
        assert result["total"] == 2
        assert result["limit"] == 20
        # 第一条 citations 已反序列化成 list[dict]
        assert result["items"][0]["citations"] == [{"document_id": "d1"}]
        # SELECT 列表 SQL 应包含三个过滤条件
        list_call = next(c for c in db.calls
                         if "SELECT feedback_id, trace_id, user_id" in c["sql"])
        assert "rating = :rating" in list_call["sql"]
        assert "kb_id = :kb_id" in list_call["sql"]
        assert "source = :src" in list_call["sql"]

    def test_list_pagination_clamping(self):
        db = _ScriptedSession([
            {"contains": "SELECT COUNT(*) FROM kb_feedback",
             "result": _StubResult(scalar_value=0)},
            {"contains": "SELECT feedback_id", "result": _StubResult(rows=[])},
        ])
        # 越界值要被夹紧到合法范围
        result = self.svc.list(db, days=9999, limit=99999, offset=-5)
        assert result["limit"] == 200      # max 200
        assert result["offset"] == 0       # min 0
        # days 上限 365
        params = db.calls[0]["params"]
        assert params["days"] == 365


# ════════════════════════════════════════════════════════════════════
# Service: stats
# ════════════════════════════════════════════════════════════════════


class TestFeedbackStats:
    def setup_method(self):
        from backend.knowledge.feedback_service import KBFeedbackService
        self.svc = KBFeedbackService.get_instance()

    def test_stats_aggregation(self):
        db = _ScriptedSession([
            # 总览
            {"contains": "AS positive",
             "result": _StubResult(rows=[_Row({
                 "total": 10, "positive": 4, "negative": 5, "neutral": 1,
             })])},
            # by_kb
            {"contains": "LEFT JOIN kb_libraries",
             "result": _StubResult(rows=[
                 _Row({"kb_id": "kb1", "kb_name": "FAQ",
                       "total": 6, "negative": 4}),
                 _Row({"kb_id": "kb2", "kb_name": "Policy",
                       "total": 4, "negative": 1}),
             ])},
            # by_reason
            {"contains": "WHERE rating=-1",
             "result": _StubResult(rows=[
                 _Row({"rating_reason": "inaccurate", "count": 3}),
                 _Row({"rating_reason": "irrelevant", "count": 2}),
             ])},
            # by_source
            {"contains": "GROUP BY source",
             "result": _StubResult(rows=[
                 _Row({"source": "biz_kb", "total": 8, "negative": 4}),
                 _Row({"source": "copilot_biz_rag", "total": 2, "negative": 1}),
             ])},
        ])
        s = self.svc.stats(db, days=7)
        assert s["window_days"] == 7
        assert s["total"] == 10
        assert s["positive"] == 4
        assert s["negative"] == 5
        assert s["negative_rate"] == 0.5
        # by_kb
        kb1 = next(x for x in s["by_kb"] if x["kb_id"] == "kb1")
        assert kb1["negative_rate"] == round(4 / 6, 4)
        # by_reason 仅 rating=-1
        reasons = {x["rating_reason"]: x["count"] for x in s["by_reason"]}
        assert reasons["inaccurate"] == 3
        # by_source
        srcs = {x["source"]: x for x in s["by_source"]}
        assert srcs["biz_kb"]["negative"] == 4

    def test_stats_zero_total_no_div_zero(self):
        db = _ScriptedSession([
            {"contains": "AS positive",
             "result": _StubResult(rows=[_Row({
                 "total": 0, "positive": 0, "negative": 0, "neutral": 0,
             })])},
        ])
        s = self.svc.stats(db, days=7)
        assert s["total"] == 0
        assert s["negative_rate"] == 0.0
        assert s["by_kb"] == []


# ════════════════════════════════════════════════════════════════════
# Router smoke：POST /api/kb/feedback + admin GET
# ════════════════════════════════════════════════════════════════════


@pytest.fixture
def feedback_client():
    """构造独立 TestClient，覆盖 get_current_user / get_db / KBFeedbackService。

    跟随 ``test_routers.py`` 风格：``TestClient(app, raise_server_exceptions=False)``
    不进入 ``with``，从而绕开 lifespan 对 Redis / 容器初始化的依赖。
    """
    from fastapi.testclient import TestClient
    from backend.main import create_app
    from backend.middleware.auth import CurrentUser, get_current_user
    from backend.database import get_db
    from backend.knowledge import feedback_service as fb_mod

    app = create_app()

    def _fake_user():
        return CurrentUser(username="tester", roles=["admin"])

    def _fake_db():
        yield object()

    fake_svc = MagicMock()
    fake_svc.submit.return_value = {"feedback_id": 100, "action": "insert"}
    fake_svc.list.return_value = {"total": 0, "items": [], "limit": 50, "offset": 0}
    fake_svc.stats.return_value = {
        "window_days": 7, "total": 0, "positive": 0, "negative": 0,
        "neutral": 0, "negative_rate": 0.0,
        "by_kb": [], "by_reason": [], "by_source": [],
    }
    original = fb_mod.KBFeedbackService.get_instance
    fb_mod.KBFeedbackService.get_instance = staticmethod(lambda: fake_svc)

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db
    client = TestClient(app, raise_server_exceptions=False)
    try:
        yield client, fake_svc
    finally:
        fb_mod.KBFeedbackService.get_instance = original


class TestFeedbackRouter:
    def test_post_feedback_success(self, feedback_client):
        client, svc = feedback_client
        r = client.post("/api/kb/feedback", json={
            "query": "退款多久到账",
            "rating": -1,
            "rating_reason": "inaccurate",
            "trace_id": "trace-1",
            "kb_id": "kb-1",
        })
        assert r.status_code == 200
        body = r.json()
        assert body["data"]["feedback_id"] == 100
        assert body["data"]["action"] == "insert"
        # 服务被调用一次，鉴权用的 username 透传到 user_id
        svc.submit.assert_called_once()
        kwargs = svc.submit.call_args.kwargs
        assert kwargs["user_id"] == "tester"
        assert kwargs["rating"] == -1
        assert kwargs["rating_reason"] == "inaccurate"

    def test_post_feedback_invalid_reason_falls_back_to_other(self, feedback_client):
        client, svc = feedback_client
        r = client.post("/api/kb/feedback", json={
            "query": "q", "rating": -1, "rating_reason": "weird-non-controlled",
        })
        assert r.status_code == 200
        kwargs = svc.submit.call_args.kwargs
        # 受控集合外的 reason 一律改成 "other"
        assert kwargs["rating_reason"] == "other"

    def test_post_feedback_invalid_source_falls_back(self, feedback_client):
        client, svc = feedback_client
        r = client.post("/api/kb/feedback", json={
            "query": "q", "rating": 1, "source": "hacker_made_up",
        })
        assert r.status_code == 200
        kwargs = svc.submit.call_args.kwargs
        assert kwargs["source"] == "biz_kb"

    def test_post_feedback_missing_query_400(self, feedback_client):
        client, _ = feedback_client
        r = client.post("/api/kb/feedback", json={"rating": 1})
        assert r.status_code == 422  # Pydantic missing field

    def test_admin_list_feedback_smoke(self, feedback_client):
        client, svc = feedback_client
        # admin token：依赖被 override 成 admin，因此直接通过
        r = client.get("/admin/knowledge/v2/feedback?rating=-1&days=7")
        assert r.status_code == 200
        svc.list.assert_called_once()
        assert svc.list.call_args.kwargs["rating"] == -1
        assert svc.list.call_args.kwargs["days"] == 7

    def test_admin_feedback_stats_smoke(self, feedback_client):
        client, svc = feedback_client
        r = client.get("/admin/knowledge/v2/feedback/stats?days=14")
        assert r.status_code == 200
        svc.stats.assert_called_once()
        assert svc.stats.call_args.kwargs["days"] == 14
