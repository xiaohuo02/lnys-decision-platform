# -*- coding: utf-8 -*-
"""记忆管理 Skill — Agent 自主维护记忆（借鉴 Claude Code）

所有 DB 操作通过 AsyncSession + ORM 实现真异步。
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator, Iterable, List

from loguru import logger
from sqlalchemy import func, select, update

from backend.copilot.base_skill import BaseCopilotSkill, SkillContext
from backend.copilot.events import CopilotEvent, EventType
from backend.models.copilot import CopilotMemory


# 后台任务引用集合：避免 asyncio.create_task 返回的 Task 被 GC 时提前取消
# 参考: https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task
_BACKGROUND_TASKS: "set[asyncio.Task]" = set()


def _spawn_background(coro) -> None:
    """fire-and-forget 启动后台协程，保留引用避免 GC 取消"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # 无 loop 时静默跳过（测试场景）
    task = loop.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


class MemorySkill(BaseCopilotSkill):
    name = "memory_skill"
    display_name = "记忆管理"
    description = (
        '保存、检索、更新用户偏好和业务上下文记忆。当用户说"记住这个"、"我的偏好是"、"以后记得"等时调用write。'
        "当Agent需要回忆用户之前的偏好或决策时调用read/search。"
    )
    required_roles = {
        # DB 真实角色：memory 是 AI 工程面能力，仅平台管理员和算法工程师可用
        "platform_admin", "ml_engineer",
        # legacy 兼容
        "super_admin", "business_admin", "ops_analyst", "biz_operator",
    }
    mode = {"ops", "biz"}
    parameters_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["read", "write", "update", "search"],
                "description": "操作类型",
            },
            "domain": {
                "type": "string",
                "enum": ["user_preferences", "business_context", "decisions", "patterns"],
                "description": "记忆域",
            },
            "title": {"type": "string", "description": "记忆标题"},
            "content": {"type": "string", "description": "记忆内容"},
            "query": {"type": "string", "description": "搜索查询（action=search 时用）"},
            "memory_id": {"type": "integer", "description": "记忆ID（action=update 时用）"},
        },
        "required": ["action"],
    }

    async def execute(self, question: str, context: SkillContext) -> AsyncGenerator[CopilotEvent, None]:
        action = context.tool_args.get("action", "read")

        if action == "read":
            memories = await self._read_memories(context)
            yield CopilotEvent(
                type=EventType.TOOL_RESULT,
                data={"memories": memories, "count": len(memories)},
            )
            if memories:
                yield CopilotEvent(
                    type=EventType.MEMORY_UPDATED,
                    content=f"已加载 {len(memories)} 条记忆",
                )

        elif action == "write":
            success = await self._write_memory(context)
            yield CopilotEvent(
                type=EventType.TOOL_RESULT,
                data={"status": "saved" if success else "failed"},
            )
            if success:
                yield CopilotEvent(
                    type=EventType.MEMORY_UPDATED,
                    content=f"已保存记忆: {context.tool_args.get('title', '')}",
                )

        elif action == "update":
            success = await self._update_memory(context)
            yield CopilotEvent(
                type=EventType.TOOL_RESULT,
                data={"status": "updated" if success else "failed"},
            )

        elif action == "search":
            results = await self._search_memories(context)
            yield CopilotEvent(
                type=EventType.TOOL_RESULT,
                data={"results": results, "count": len(results)},
            )

    async def _read_memories(self, context: SkillContext) -> list:
        """读取指定域的记忆。返回前异步 bump access_count（fire-and-forget）"""
        try:
            from backend.database import _get_async_engine, _async_session_factory
            _get_async_engine()
            assert _async_session_factory is not None
            async with _async_session_factory() as session:
                domain = context.tool_args.get("domain")
                stmt = (
                    select(
                        CopilotMemory.id, CopilotMemory.domain,
                        CopilotMemory.title, CopilotMemory.content,
                        CopilotMemory.importance,
                    )
                    .where(
                        CopilotMemory.user_id == context.user_id,
                        CopilotMemory.is_active == True,
                    )
                )
                if domain:
                    stmt = stmt.where(CopilotMemory.domain == domain)
                stmt = stmt.order_by(
                    CopilotMemory.importance.desc(), CopilotMemory.updated_at.desc()
                ).limit(20)
                result = await session.execute(stmt)
                items = [
                    {"id": r.id, "domain": r.domain, "title": r.title,
                     "content": r.content, "importance": r.importance}
                    for r in result.all()
                ]
            # 后台更新 access_count + last_accessed_at（不阻塞主返回）
            ids = [m["id"] for m in items]
            if ids:
                _spawn_background(self._bump_access(ids))
            return items
        except Exception as e:
            logger.debug(f"[MemorySkill] read 失败: {e}")
            return []

    @staticmethod
    async def _bump_access(memory_ids: List[int]) -> None:
        """批量给命中的记忆 access_count += 1 + 更新 last_accessed_at。

        独立 session，非关键路径，失败静默降级。
        """
        if not memory_ids:
            return
        try:
            from backend.database import _get_async_engine, _async_session_factory
            _get_async_engine()
            assert _async_session_factory is not None
            async with _async_session_factory() as session:
                await session.execute(
                    update(CopilotMemory)
                    .where(CopilotMemory.id.in_(memory_ids))
                    .values(
                        access_count=CopilotMemory.access_count + 1,
                        last_accessed_at=func.now(),
                    )
                )
                await session.commit()
        except Exception as e:
            logger.debug(f"[MemorySkill] _bump_access failed (non-fatal): {e}")

    async def _write_memory(self, context: SkillContext) -> bool:
        try:
            from backend.database import _get_async_engine, _async_session_factory
            _get_async_engine()
            assert _async_session_factory is not None
            async with _async_session_factory() as session:
                mem = CopilotMemory(
                    user_id=context.user_id,
                    domain=context.tool_args.get("domain", "user_preferences"),
                    title=context.tool_args.get("title", ""),
                    content=context.tool_args.get("content", ""),
                    importance=0.5,
                )
                session.add(mem)
                await session.commit()
                await session.refresh(mem)  # 取回自增 ID
                mem_snapshot = {
                    "id": mem.id, "user_id": mem.user_id, "domain": mem.domain,
                    "title": mem.title, "content": mem.content, "importance": mem.importance,
                }
            # 后台写 chroma embedding（R5-3）
            _spawn_background(self._upsert_memory_embedding(mem_snapshot))
            return True
        except Exception as e:
            logger.warning(f"[MemorySkill] write 失败: {e}")
            return False

    async def _update_memory(self, context: SkillContext) -> bool:
        try:
            from backend.database import _get_async_engine, _async_session_factory
            _get_async_engine()
            assert _async_session_factory is not None
            memory_id = context.tool_args.get("memory_id")
            new_title = context.tool_args.get("title", "")
            new_content = context.tool_args.get("content", "")
            async with _async_session_factory() as session:
                await session.execute(
                    update(CopilotMemory)
                    .where(
                        CopilotMemory.id == memory_id,
                        CopilotMemory.user_id == context.user_id,
                    )
                    .values(content=new_content, title=new_title)
                )
                await session.commit()
                # 读回完整行用于 embedding 更新
                res = await session.execute(
                    select(
                        CopilotMemory.id, CopilotMemory.user_id, CopilotMemory.domain,
                        CopilotMemory.title, CopilotMemory.content, CopilotMemory.importance,
                    ).where(
                        CopilotMemory.id == memory_id,
                        CopilotMemory.user_id == context.user_id,
                    )
                )
                row = res.first()
            if row:
                snapshot = {
                    "id": row.id, "user_id": row.user_id, "domain": row.domain,
                    "title": row.title, "content": row.content, "importance": row.importance,
                }
                _spawn_background(self._upsert_memory_embedding(snapshot))
            return True
        except Exception as e:
            logger.warning(f"[MemorySkill] update 失败: {e}")
            return False

    # ── 向量落库辅助（R5-3）──────────────────────────────────────

    @staticmethod
    async def _embed_async(text: str) -> list:
        """同步 embedding 模型推理放线程池执行，不阻塞 event loop"""
        from fastapi.concurrency import run_in_threadpool
        from backend.core.embedding import EmbeddingService
        emb = EmbeddingService.get_instance()
        return await run_in_threadpool(emb.embed_query, text)

    @staticmethod
    def _get_memory_collection():
        """获取记忆 embedding collection（同步调用，仅在 threadpool 内用）"""
        from backend.core.vector_store import VectorStoreManager
        return VectorStoreManager.get_instance().get_collection("copilot_memory_embeddings")

    @staticmethod
    async def _upsert_memory_embedding(snapshot: dict) -> None:
        """Fire-and-forget: 向 chroma 写入/更新一条记忆 embedding"""
        try:
            from fastapi.concurrency import run_in_threadpool
            content = (snapshot.get("content") or "")[:512]
            if not content:
                return
            vec = await MemorySkill._embed_async(content)

            def _write() -> None:
                col = MemorySkill._get_memory_collection()
                col.upsert(
                    ids=[str(snapshot["id"])],
                    embeddings=[vec],
                    documents=[content],
                    metadatas=[{
                        "user_id": snapshot["user_id"],
                        "domain": snapshot.get("domain", ""),
                        "title": (snapshot.get("title") or "")[:200],
                        "importance": float(snapshot.get("importance") or 0.5),
                    }],
                )

            await run_in_threadpool(_write)
        except Exception as e:
            logger.debug(f"[MemorySkill] upsert embedding failed (non-fatal): {e}")

    @staticmethod
    async def _delete_memory_embedding(memory_id: int) -> None:
        """Fire-and-forget: 从 chroma 删除一条记忆 embedding"""
        try:
            from fastapi.concurrency import run_in_threadpool

            def _delete() -> None:
                col = MemorySkill._get_memory_collection()
                col.delete(ids=[str(memory_id)])

            await run_in_threadpool(_delete)
        except Exception as e:
            logger.debug(f"[MemorySkill] delete embedding failed (non-fatal): {e}")

    async def _search_memories(self, context: SkillContext) -> list:
        """语义搜索记忆（向量 kNN，按 user_id metadata 过滤）。

        流程:
          1. 用户查询 → 异步 embedding（run_in_threadpool）
          2. chroma.query 一次返回 top_k ids + distances
          3. SQL IN 查询 DB 拿完整行（过滤 is_active=True）
          4. 按 chroma 返回顺序 + similarity 组装
          5. fire-and-forget bump access_count
          6. chroma 不可用/查不到 → 降级 read_memories（按重要度 + 时间排序）
        """
        query = context.tool_args.get("query", "")
        if not query:
            return await self._read_memories(context)

        try:
            from fastapi.concurrency import run_in_threadpool
            from backend.database import _get_async_engine, _async_session_factory

            # 1. 查询 embedding
            query_vec = await self._embed_async(query)

            # 2. chroma kNN（按 user_id 过滤，同步操作放线程池）
            def _kquery() -> dict:
                col = self._get_memory_collection()
                return col.query(
                    query_embeddings=[query_vec],
                    n_results=10,
                    where={"user_id": context.user_id},
                    include=["metadatas", "distances"],
                )

            kres = await run_in_threadpool(_kquery)
            raw_ids = (kres.get("ids") or [[]])[0] if kres else []
            raw_dists = (kres.get("distances") or [[]])[0] if kres else []

            if not raw_ids:
                # 向量库无记录（可能是未落库历史数据），降级到按重要度读取
                return await self._read_memories(context)

            # 3. 批量 fetch DB 详情 + 过滤软删除
            try:
                ids_int = [int(i) for i in raw_ids]
            except ValueError:
                ids_int = []
            if not ids_int:
                return []

            _get_async_engine()
            assert _async_session_factory is not None
            async with _async_session_factory() as session:
                db_stmt = (
                    select(
                        CopilotMemory.id, CopilotMemory.domain,
                        CopilotMemory.title, CopilotMemory.content,
                        CopilotMemory.importance,
                    )
                    .where(
                        CopilotMemory.id.in_(ids_int),
                        CopilotMemory.user_id == context.user_id,
                        CopilotMemory.is_active == True,
                    )
                )
                rows = (await session.execute(db_stmt)).all()
            db_map = {r.id: r for r in rows}

            # 4. 按 chroma 顺序组装（保留 similarity）
            hits: list = []
            for idx, mid in enumerate(ids_int):
                row = db_map.get(mid)
                if row is None:
                    # chroma 有但 DB 已软删除 → 清理 chroma
                    _spawn_background(self._delete_memory_embedding(mid))
                    continue
                sim = 1.0 - float(raw_dists[idx]) if idx < len(raw_dists) else 0.0
                hits.append({
                    "id": row.id, "domain": row.domain, "title": row.title,
                    "content": row.content, "importance": row.importance,
                    "similarity": round(sim, 3),
                })

            # 5. 后台 bump access_count
            if hits:
                _spawn_background(self._bump_access([h["id"] for h in hits]))

            return hits
        except Exception as e:
            logger.warning(f"[MemorySkill] search 失败（降级到 read）: {e}")
            return await self._read_memories(context)


memory_skill = MemorySkill()
