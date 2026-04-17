# -*- coding: utf-8 -*-
"""backend/copilot/skills/release_query_skill.py — Release 发布查询 Skill (R6-3)

从 OpsCopilotReadRepository.get_recent_releases / get_last_rollback 抽出。
查询 releases 表: 最近发布、最近回滚。
"""
from __future__ import annotations

from typing import AsyncGenerator

from loguru import logger

from backend.copilot.base_skill import BaseCopilotSkill, SkillContext
from backend.copilot.events import CopilotEvent, EventType


class ReleaseQuerySkill(BaseCopilotSkill):
    name = "release_query_skill"
    display_name = "Release 发布查询"
    description = (
        "查询 release 表: 最近发布的版本、最近一次 rollback。"
        "当用户询问 release/发布/回滚/上线相关问题时调用。"
    )
    required_roles = {
        # DB 真实角色
        "platform_admin", "ops_analyst", "ml_engineer", "auditor",
        # legacy 兼容
        "super_admin",
    }
    mode = {"ops"}
    summarization_hint = (
        "总结 release 查询时，高亮最近 rollback（如有）的原因和时间；"
        "对 release 列表按状态分类（active / rolled_back / pending）。"
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "query_type": {
                "type": "string",
                "enum": ["recent_releases", "last_rollback"],
                "description": "查询类型",
            },
            "limit": {
                "type": "integer",
                "description": "返回条数（query_type=recent_releases 时有效）",
                "default": 5,
            },
        },
    }

    async def execute(
        self, question: str, context: SkillContext
    ) -> AsyncGenerator[CopilotEvent, None]:
        query_type = context.tool_args.get("query_type", "recent_releases")
        limit = int(context.tool_args.get("limit", 5))

        try:
            from backend.database import _get_async_engine, _async_session_factory
            from sqlalchemy import text
            _get_async_engine()
            assert _async_session_factory is not None
            async with _async_session_factory() as db:
                data, title = await self._dispatch(db, text, query_type, limit)
        except Exception as e:
            logger.warning(f"[ReleaseQuerySkill] query failed: {e}")
            data = {"error": str(e), "hint": "数据库可能不可达或 releases 表缺失"}
            title = "Release 查询（降级）"

        yield CopilotEvent(
            type=EventType.ARTIFACT_START,
            artifact_type="generic_table",
            metadata={"title": title, "component": "GenericTableArtifact"},
        )
        yield CopilotEvent(type=EventType.ARTIFACT_DELTA, content=data)
        yield CopilotEvent(type=EventType.ARTIFACT_END)
        yield CopilotEvent(
            type=EventType.SUGGESTIONS,
            items=[
                {"type": "question", "label": "最近有哪些 release？"},
                {"type": "question", "label": "最近一次 rollback 是什么时候？"},
            ],
        )
        yield CopilotEvent(
            type=EventType.TOOL_RESULT,
            data=data if isinstance(data, dict) else {"results": data},
        )

    async def _dispatch(self, db, text_fn, query_type: str, limit: int):
        if query_type == "recent_releases":
            result = await db.execute(
                text_fn(
                    "SELECT release_id, name, version, status, released_by, created_at "
                    "FROM releases ORDER BY created_at DESC LIMIT :lim"
                ),
                {"lim": limit},
            )
            rows = result.fetchall()
            data = [
                {
                    "release_id": r[0],
                    "name": r[1],
                    "version": r[2],
                    "status": r[3],
                    "released_by": r[4],
                    "created_at": str(r[5]) if r[5] else None,
                }
                for r in rows
            ]
            return data, f"最近的 Release — {len(data)} 条"

        # last_rollback
        result = await db.execute(
            text_fn(
                "SELECT release_id, name, version, released_by, created_at "
                "FROM releases WHERE status='rolled_back' "
                "ORDER BY created_at DESC LIMIT 1"
            )
        )
        row = result.fetchone()
        if row is None:
            return {"note": "无 rollback 记录"}, "最近一次 Rollback（无）"
        data = {
            "release_id": row[0],
            "name": row[1],
            "version": row[2],
            "released_by": row[3],
            "created_at": str(row[4]) if row[4] else None,
        }
        return data, f"最近一次 Rollback — {data['name']}"


release_query_skill = ReleaseQuerySkill()
