# -*- coding: utf-8 -*-
"""backend/tests/test_r5_performance.py — R5 性能/资源优化回归测试

覆盖：
- R5-1: CopilotMemory ORM 扩展字段（access_count / last_accessed_at / 索引）
- R5-2: MemorySkill._bump_access 批量更新访问计数
- R5-3: MemorySkill 向量管线（embedding upsert + kNN 搜索）
- R5-4: ContextManager._load_thread_history Redis 批量 rpush 回填
- R5-5: Telemetry Redis Stream 归档（XADD fire-and-forget + arecent_from_redis）
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ── R5-1: ORM schema 字段 ───────────────────────────────────────

class TestMemoryOrmSchema:
    def test_access_count_column_exists(self):
        from backend.models.copilot import CopilotMemory
        cols = {c.name for c in CopilotMemory.__table__.columns}
        assert "access_count" in cols
        assert "last_accessed_at" in cols

    def test_access_count_not_null_default_zero(self):
        from backend.models.copilot import CopilotMemory
        col = CopilotMemory.__table__.columns["access_count"]
        assert col.nullable is False
        # server_default="0"
        assert col.server_default is not None
        assert str(col.server_default.arg) == "0"

    def test_last_accessed_at_nullable(self):
        from backend.models.copilot import CopilotMemory
        col = CopilotMemory.__table__.columns["last_accessed_at"]
        assert col.nullable is True

    def test_new_indexes_registered(self):
        from backend.models.copilot import CopilotMemory
        idx_names = {idx.name for idx in CopilotMemory.__table__.indexes}
        assert "idx_memory_access" in idx_names
        assert "idx_memory_last_accessed" in idx_names


# ── 通用 DB session mock ─────────────────────────────────────────

class _DBMocks:
    """一次性构造 _async_session_factory + AsyncSession 的 mock 组合"""

    def __init__(self):
        self.session = AsyncMock()
        self.session.execute = AsyncMock()
        self.session.commit = AsyncMock()
        self.session.add = MagicMock()
        self.session.refresh = AsyncMock()
        self.session.rollback = AsyncMock()

        @asynccontextmanager
        async def _factory():
            yield self.session

        self.factory = _factory

    def patch(self):
        return [
            patch("backend.database._get_async_engine", return_value=MagicMock()),
            patch("backend.database._async_session_factory", self.factory),
        ]

    def __enter__(self):
        self._ctx = self.patch()
        for p in self._ctx:
            p.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        for p in self._ctx:
            p.stop()


# ── R5-2: _bump_access 批量更新 ─────────────────────────────────

class TestBumpAccess:
    @pytest.mark.asyncio
    async def test_bump_access_empty_ids_noop(self):
        from backend.copilot.skills.memory_skill import MemorySkill
        # 空 ID 列表应直接 early-return，不触发 DB 调用
        with _DBMocks() as dbm:
            await MemorySkill._bump_access([])
            dbm.session.execute.assert_not_awaited()
            dbm.session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_bump_access_single_batch_update(self):
        """多个 id 应汇总为一次 UPDATE ... WHERE id IN (...)"""
        from backend.copilot.skills.memory_skill import MemorySkill
        from backend.models.copilot import CopilotMemory

        with _DBMocks() as dbm:
            await MemorySkill._bump_access([10, 20, 30])
            # 仅一次 execute（批量 update）+ 一次 commit
            assert dbm.session.execute.await_count == 1
            assert dbm.session.commit.await_count == 1
            # 校验 Update 语句目标是 CopilotMemory
            call = dbm.session.execute.await_args
            stmt = call.args[0]
            # 反射检查 SQL 是 UPDATE copilot_memory
            assert CopilotMemory.__table__.name in str(stmt).lower()
            assert "update" in str(stmt).lower()

    @pytest.mark.asyncio
    async def test_bump_access_swallows_exception(self):
        """DB 异常不应向上传播（非关键路径）"""
        from backend.copilot.skills.memory_skill import MemorySkill

        with _DBMocks() as dbm:
            dbm.session.execute.side_effect = RuntimeError("db down")
            # 不应抛异常
            await MemorySkill._bump_access([1])


# ── R5-3: 向量管线 ──────────────────────────────────────────────

class TestMemoryVectorPipeline:
    @pytest.mark.asyncio
    async def test_embed_async_calls_embedding_service(self):
        """_embed_async 应在 threadpool 中调用 EmbeddingService.embed_query"""
        from backend.copilot.skills.memory_skill import MemorySkill
        fake_vec = [0.1, 0.2, 0.3]
        fake_service = MagicMock()
        fake_service.embed_query = MagicMock(return_value=fake_vec)
        with patch(
            "backend.core.embedding.EmbeddingService.get_instance",
            return_value=fake_service,
        ):
            vec = await MemorySkill._embed_async("hello")
        assert vec == fake_vec
        fake_service.embed_query.assert_called_once_with("hello")

    @pytest.mark.asyncio
    async def test_upsert_embedding_writes_to_collection(self):
        """_upsert_memory_embedding 应把 embedding + metadata 写入 chroma"""
        from backend.copilot.skills.memory_skill import MemorySkill

        fake_col = MagicMock()
        fake_col.upsert = MagicMock()
        fake_vsm = MagicMock()
        fake_vsm.get_collection = MagicMock(return_value=fake_col)

        fake_service = MagicMock()
        fake_service.embed_query = MagicMock(return_value=[0.5, 0.6])

        with (
            patch("backend.core.vector_store.VectorStoreManager.get_instance", return_value=fake_vsm),
            patch("backend.core.embedding.EmbeddingService.get_instance", return_value=fake_service),
        ):
            await MemorySkill._upsert_memory_embedding({
                "id": 42,
                "user_id": "u1",
                "domain": "user_preferences",
                "title": "t",
                "content": "用户偏好 X",
                "importance": 0.6,
            })

        fake_vsm.get_collection.assert_called_once_with("copilot_memory_embeddings")
        fake_col.upsert.assert_called_once()
        kwargs = fake_col.upsert.call_args.kwargs
        assert kwargs["ids"] == ["42"]
        assert kwargs["embeddings"] == [[0.5, 0.6]]
        assert kwargs["documents"] == ["用户偏好 X"]
        meta = kwargs["metadatas"][0]
        assert meta["user_id"] == "u1"
        assert meta["domain"] == "user_preferences"
        assert meta["importance"] == pytest.approx(0.6)

    @pytest.mark.asyncio
    async def test_upsert_empty_content_skipped(self):
        """空内容不写 embedding（防止无意义 upsert）"""
        from backend.copilot.skills.memory_skill import MemorySkill
        fake_vsm = MagicMock()
        with patch(
            "backend.core.vector_store.VectorStoreManager.get_instance",
            return_value=fake_vsm,
        ):
            await MemorySkill._upsert_memory_embedding({
                "id": 1, "user_id": "u", "domain": "d",
                "title": "t", "content": "", "importance": 0.5,
            })
        fake_vsm.get_collection.assert_not_called()

    @pytest.mark.asyncio
    async def test_upsert_errors_silently(self):
        """chroma 写入异常不应向上抛（非关键路径）"""
        from backend.copilot.skills.memory_skill import MemorySkill
        fake_col = MagicMock()
        fake_col.upsert.side_effect = RuntimeError("chroma down")
        fake_vsm = MagicMock()
        fake_vsm.get_collection.return_value = fake_col
        fake_service = MagicMock()
        fake_service.embed_query = MagicMock(return_value=[0.1])
        with (
            patch("backend.core.vector_store.VectorStoreManager.get_instance", return_value=fake_vsm),
            patch("backend.core.embedding.EmbeddingService.get_instance", return_value=fake_service),
        ):
            # 不应抛异常
            await MemorySkill._upsert_memory_embedding({
                "id": 1, "user_id": "u", "domain": "d",
                "title": "t", "content": "x", "importance": 0.5,
            })

    @pytest.mark.asyncio
    async def test_search_memories_vector_knn_with_user_filter(self):
        """_search_memories 应调用 chroma.query(where={user_id})，
        不再现场做 O(N) embedding"""
        from backend.copilot.skills.memory_skill import MemorySkill
        from backend.copilot.base_skill import SkillContext

        # chroma 返回 2 个 id
        fake_col = MagicMock()
        fake_col.query = MagicMock(return_value={
            "ids": [["10", "20"]],
            "distances": [[0.1, 0.3]],
            "metadatas": [[{}, {}]],
        })
        fake_vsm = MagicMock()
        fake_vsm.get_collection.return_value = fake_col

        fake_service = MagicMock()
        fake_service.embed_query = MagicMock(return_value=[0.1, 0.2])

        # DB 回 2 行
        row10 = SimpleNamespace(id=10, domain="d", title="t10", content="c10", importance=0.8)
        row20 = SimpleNamespace(id=20, domain="d", title="t20", content="c20", importance=0.5)
        db_result = MagicMock()
        db_result.all.return_value = [row10, row20]

        with (
            _DBMocks() as dbm,
            patch("backend.core.vector_store.VectorStoreManager.get_instance", return_value=fake_vsm),
            patch("backend.core.embedding.EmbeddingService.get_instance", return_value=fake_service),
        ):
            dbm.session.execute.return_value = db_result
            ctx = SkillContext(
                user_id="u1", user_role="biz_operator", mode="biz",
                thread_id="t", tool_args={"query": "how"},
            )
            skill = MemorySkill()
            hits = await skill._search_memories(ctx)

        # chroma.query 必须按 user_id 过滤
        call = fake_col.query.call_args
        assert call.kwargs["n_results"] == 10
        assert call.kwargs["where"] == {"user_id": "u1"}
        # 结果按 chroma 顺序 + 计算 similarity = 1 - distance
        assert [h["id"] for h in hits] == [10, 20]
        assert hits[0]["similarity"] == pytest.approx(0.9, abs=1e-6)
        assert hits[1]["similarity"] == pytest.approx(0.7, abs=1e-6)

    @pytest.mark.asyncio
    async def test_search_memories_empty_query_falls_back_to_read(self):
        """空 query 降级到 _read_memories"""
        from backend.copilot.skills.memory_skill import MemorySkill
        from backend.copilot.base_skill import SkillContext

        skill = MemorySkill()
        skill._read_memories = AsyncMock(return_value=[{"id": 1}])
        ctx = SkillContext(
            user_id="u1", user_role="biz_operator", mode="biz",
            thread_id="t", tool_args={"query": ""},
        )
        result = await skill._search_memories(ctx)
        assert result == [{"id": 1}]
        skill._read_memories.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_search_memories_empty_chroma_hit_falls_back(self):
        """chroma 无结果（历史数据未落库）降级到 read"""
        from backend.copilot.skills.memory_skill import MemorySkill
        from backend.copilot.base_skill import SkillContext

        fake_col = MagicMock()
        fake_col.query = MagicMock(return_value={"ids": [[]], "distances": [[]]})
        fake_vsm = MagicMock()
        fake_vsm.get_collection.return_value = fake_col

        fake_service = MagicMock()
        fake_service.embed_query = MagicMock(return_value=[0.1])

        with (
            patch("backend.core.vector_store.VectorStoreManager.get_instance", return_value=fake_vsm),
            patch("backend.core.embedding.EmbeddingService.get_instance", return_value=fake_service),
        ):
            skill = MemorySkill()
            skill._read_memories = AsyncMock(return_value=[{"id": 99}])
            ctx = SkillContext(
                user_id="u1", user_role="biz_operator", mode="biz",
                thread_id="t", tool_args={"query": "hello"},
            )
            result = await skill._search_memories(ctx)
        assert result == [{"id": 99}]

    @pytest.mark.asyncio
    async def test_search_memories_soft_deleted_filtered_and_cleans_chroma(self):
        """chroma 命中但 DB 已软删 → 不返回 + 后台清理 chroma"""
        from backend.copilot.skills import memory_skill as ms
        from backend.copilot.base_skill import SkillContext

        fake_col = MagicMock()
        fake_col.query = MagicMock(return_value={
            "ids": [["10", "99"]], "distances": [[0.2, 0.3]],
        })
        fake_col.delete = MagicMock()
        fake_vsm = MagicMock()
        fake_vsm.get_collection.return_value = fake_col
        fake_service = MagicMock()
        fake_service.embed_query = MagicMock(return_value=[0.1])

        # DB 仅返回 10（99 已软删）
        row10 = SimpleNamespace(id=10, domain="d", title="t", content="c", importance=0.5)
        db_result = MagicMock()
        db_result.all.return_value = [row10]

        # 把所有 patch 放在同一作用域内，并在作用域内 flush 后台任务，
        # 避免 background task 在 patch 退出后才执行导致取真实依赖。
        with (
            _DBMocks() as dbm,
            patch("backend.core.vector_store.VectorStoreManager.get_instance", return_value=fake_vsm),
            patch("backend.core.embedding.EmbeddingService.get_instance", return_value=fake_service),
        ):
            dbm.session.execute.return_value = db_result
            skill = ms.MemorySkill()
            ctx = SkillContext(
                user_id="u1", user_role="biz_operator", mode="biz",
                thread_id="t", tool_args={"query": "hello"},
            )
            hits = await skill._search_memories(ctx)

            assert [h["id"] for h in hits] == [10]

            # flush：显式 await 所有 fire-and-forget 的后台 task
            pending = [t for t in ms._BACKGROUND_TASKS if not t.done()]
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

            # 查验 chroma.delete 对 id=99 被调用
            deleted_ids = [c.kwargs.get("ids") for c in fake_col.delete.call_args_list]
            assert ["99"] in deleted_ids or any("99" in d for d in deleted_ids)


# ── R5-3: VectorStore 注册表 ───────────────────────────────────

class TestVectorStoreRegistry:
    def test_copilot_memory_collection_registered(self):
        from backend.core.vector_store import COLLECTION_REGISTRY
        assert "copilot_memory_embeddings" in COLLECTION_REGISTRY
        entry = COLLECTION_REGISTRY["copilot_memory_embeddings"]
        assert entry["owner"] == "copilot"

    def test_get_collection_auto_registers_unknown_dynamic_kb(self):
        """SQL seed 路径下 KB 没经 create_library，get_collection 应自动注册到 registry。"""
        from backend.core.vector_store import VectorStoreManager, COLLECTION_REGISTRY

        col_name = "kb_unit_test_auto_reg_dummy"
        assert col_name not in COLLECTION_REGISTRY

        fake_client = MagicMock()
        fake_chroma_col = MagicMock()
        fake_client.get_or_create_collection.return_value = fake_chroma_col

        store = VectorStoreManager.__new__(VectorStoreManager)
        store._client = fake_client

        result = store.get_collection(col_name)

        assert result is fake_chroma_col
        assert col_name in COLLECTION_REGISTRY
        assert COLLECTION_REGISTRY[col_name]["owner"] == "knowledge"
        assert "auto-registered" in COLLECTION_REGISTRY[col_name]["description"]
        fake_client.get_or_create_collection.assert_called_once_with(
            name=col_name,
            metadata={"hnsw:space": "cosine"},
        )

        COLLECTION_REGISTRY.pop(col_name, None)


# ── R5-4: ContextManager 批量 rpush ─────────────────────────────

class TestContextLoadHistoryBatchRPush:
    @pytest.mark.asyncio
    async def test_redis_hit_no_db_no_rpush(self):
        """Redis 有数据直接返回，不触碰 DB / rpush"""
        from backend.copilot.context import ContextManager

        redis = AsyncMock()
        redis.lrange.return_value = [
            json.dumps({"role": "user", "content": "q1"}),
            json.dumps({"role": "assistant", "content": "a1"}),
        ]
        db = AsyncMock()
        cm = ContextManager(redis=redis, db=db)
        history = await cm._load_thread_history("t123", max_turns=5)
        assert len(history) == 2
        db.execute.assert_not_awaited()
        redis.rpush.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_redis_miss_db_fallback_single_rpush(self):
        """Redis miss + DB 命中 → MySQL 回填为单次 rpush 批量推送"""
        from backend.copilot.context import ContextManager

        redis = AsyncMock()
        redis.lrange.return_value = []
        redis.rpush = AsyncMock(return_value=3)
        redis.expire = AsyncMock(return_value=True)

        # DB 返回 3 条消息（倒序），context 会 reverse 到 user→assistant→user
        rows = [
            SimpleNamespace(role="user", content="q3"),
            SimpleNamespace(role="assistant", content="a2"),
            SimpleNamespace(role="user", content="q1"),
        ]
        db_result = MagicMock()
        db_result.all.return_value = rows
        db = AsyncMock()
        db.execute.return_value = db_result

        cm = ContextManager(redis=redis, db=db)
        history = await cm._load_thread_history("t-batch", max_turns=5)

        # 3 条按 reverse 顺序回来（q1 在最前）
        assert [h["content"] for h in history] == ["q1", "a2", "q3"]

        # rpush 仅调一次，args = key + N payloads
        assert redis.rpush.await_count == 1
        call = redis.rpush.await_args
        assert call.args[0] == "copilot:thread:t-batch"
        payloads = call.args[1:]
        assert len(payloads) == 3
        # payload 每条都是合法 JSON
        decoded = [json.loads(p) for p in payloads]
        assert decoded[0]["content"] == "q1"
        assert decoded[-1]["content"] == "q3"

        # expire 也应设置
        redis.expire.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_redis_miss_db_empty_no_rpush(self):
        """Redis miss + DB 空 → 不调 rpush"""
        from backend.copilot.context import ContextManager

        redis = AsyncMock()
        redis.lrange.return_value = []
        redis.rpush = AsyncMock()
        db_result = MagicMock()
        db_result.all.return_value = []
        db = AsyncMock()
        db.execute.return_value = db_result

        cm = ContextManager(redis=redis, db=db)
        history = await cm._load_thread_history("t-empty", max_turns=5)
        assert history == []
        redis.rpush.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rpush_failure_not_propagate(self):
        """Redis rpush 异常属于 best-effort，不应影响 history 返回"""
        from backend.copilot.context import ContextManager

        redis = AsyncMock()
        redis.lrange.return_value = []
        redis.rpush.side_effect = ConnectionError("redis down")
        redis.expire = AsyncMock()

        rows = [SimpleNamespace(role="user", content="q")]
        db_result = MagicMock()
        db_result.all.return_value = rows
        db = AsyncMock()
        db.execute.return_value = db_result

        cm = ContextManager(redis=redis, db=db)
        history = await cm._load_thread_history("t-boom", max_turns=5)
        # 仍应返回 DB 结果
        assert [h["content"] for h in history] == ["q"]


# ── R5-5: Telemetry Redis Stream 归档 ───────────────────────────

class TestTelemetryRedisStream:
    def test_configure_sets_redis_and_key(self):
        from backend.core.telemetry import Telemetry
        tm = Telemetry()
        fake_redis = AsyncMock()
        tm.configure(redis=fake_redis, stream_key="test:stream", stream_maxlen=500)
        assert tm._redis is fake_redis
        assert tm._stream_key == "test:stream"
        assert tm._stream_maxlen == 500

    def test_configure_with_none_disables(self):
        from backend.core.telemetry import Telemetry
        tm = Telemetry()
        tm.configure(redis=None)
        assert tm._redis is None

    @pytest.mark.asyncio
    async def test_emit_fires_xadd_on_configured_redis(self):
        """emit 应 fire-and-forget 调 redis.xadd"""
        from backend.core.telemetry import Telemetry, TelemetryEventType
        fake_redis = AsyncMock()
        fake_redis.xadd = AsyncMock(return_value="1-0")
        tm = Telemetry()
        tm.configure(redis=fake_redis, stream_key="lnys:telemetry", stream_maxlen=100)

        tm.emit(
            TelemetryEventType.MODEL_REQUESTED,
            {"model": "qwen"}, run_id="r1", component="Test",
        )
        # 等后台 task 跑完
        await asyncio.sleep(0.05)
        fake_redis.xadd.assert_awaited()
        call = fake_redis.xadd.await_args
        assert call.args[0] == "lnys:telemetry"
        payload = call.args[1]["data"]
        parsed = json.loads(payload)
        assert parsed["type"] == TelemetryEventType.MODEL_REQUESTED.value
        assert parsed["run_id"] == "r1"
        assert call.kwargs.get("maxlen") == 100
        assert call.kwargs.get("approximate") is True

    @pytest.mark.asyncio
    async def test_emit_without_redis_noop_xadd(self):
        """未 configure redis 时 emit 不应尝试 xadd"""
        from backend.core.telemetry import Telemetry, TelemetryEventType
        tm = Telemetry()
        # 未 configure → 没有 _redis
        tm.emit(TelemetryEventType.MODEL_REQUESTED, {"k": "v"})
        await asyncio.sleep(0.01)
        # 事件仍进入内存 deque
        assert len(tm._events) == 1

    @pytest.mark.asyncio
    async def test_xadd_failure_not_propagate(self):
        """xadd 异常不应阻塞 emit 主路径"""
        from backend.core.telemetry import Telemetry, TelemetryEventType
        fake_redis = AsyncMock()
        fake_redis.xadd.side_effect = ConnectionError("redis down")
        tm = Telemetry()
        tm.configure(redis=fake_redis)

        # emit 本身应成功返回
        tm.emit(TelemetryEventType.MODEL_REQUESTED, {})
        await asyncio.sleep(0.05)
        # 内存仍记录
        assert len(tm._events) == 1

    @pytest.mark.asyncio
    async def test_arecent_from_redis_decodes_events(self):
        """arecent_from_redis 应把 Redis Stream 返回的 payload 反序列化为 event dict"""
        from backend.core.telemetry import Telemetry, TelemetryEventType

        # Redis stream 返回格式：list of (stream_id, {"data": json_str})
        ev1 = {"type": "model_requested", "run_id": "r1", "timestamp": 1.0, "data": {}}
        ev2 = {"type": "run_completed", "run_id": "r2", "timestamp": 2.0, "data": {}}
        fake_rows = [
            ("1-0", {"data": json.dumps(ev2)}),
            ("2-0", {"data": json.dumps(ev1)}),
        ]
        fake_redis = AsyncMock()
        fake_redis.xrevrange = AsyncMock(return_value=fake_rows)
        tm = Telemetry()
        tm.configure(redis=fake_redis, stream_key="k")

        out = await tm.arecent_from_redis(limit=10)
        # arecent_from_redis 恢复旧→新顺序
        assert [e["run_id"] for e in out] == ["r1", "r2"]

    @pytest.mark.asyncio
    async def test_arecent_from_redis_filters_by_type(self):
        """event_type 过滤"""
        from backend.core.telemetry import Telemetry

        e_ok = {"type": "run_completed", "run_id": "r1", "timestamp": 1.0, "data": {}}
        e_bad = {"type": "model_requested", "run_id": "r2", "timestamp": 2.0, "data": {}}
        fake_rows = [
            ("1-0", {"data": json.dumps(e_bad)}),
            ("2-0", {"data": json.dumps(e_ok)}),
            ("3-0", {"data": json.dumps(e_bad)}),
        ]
        fake_redis = AsyncMock()
        fake_redis.xrevrange = AsyncMock(return_value=fake_rows)
        tm = Telemetry()
        tm.configure(redis=fake_redis)

        out = await tm.arecent_from_redis(limit=5, event_type="run_completed")
        assert [e["run_id"] for e in out] == ["r1"]

    @pytest.mark.asyncio
    async def test_arecent_from_redis_empty_when_not_configured(self):
        from backend.core.telemetry import Telemetry
        tm = Telemetry()
        out = await tm.arecent_from_redis()
        assert out == []

    @pytest.mark.asyncio
    async def test_arecent_from_redis_xrevrange_failure(self):
        from backend.core.telemetry import Telemetry
        fake_redis = AsyncMock()
        fake_redis.xrevrange.side_effect = ConnectionError("down")
        tm = Telemetry()
        tm.configure(redis=fake_redis)
        out = await tm.arecent_from_redis()
        assert out == []
