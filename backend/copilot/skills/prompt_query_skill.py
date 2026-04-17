# -*- coding: utf-8 -*-
"""backend/copilot/skills/prompt_query_skill.py — Prompt 版本查询 Skill (R6-3)

从 OpsCopilotReadRepository.get_recent_published_prompts / get_prompt_versions 抽出。
查询 prompts 表：最近发布的 prompt / 各 prompt 的版本数量统计。
"""
from __future__ import annotations

from typing import AsyncGenerator

from loguru import logger

from backend.copilot.base_skill import BaseCopilotSkill, SkillContext
from backend.copilot.events import CopilotEvent, EventType


class PromptQuerySkill(BaseCopilotSkill):
    name = "prompt_query_skill"
    display_name = "Prompt 版本查询"
    description = (
        "查询 prompt 表: 最近发布的 prompt、各 prompt 的版本数量。"
        "当用户询问 prompt/提示词/版本发布/草稿相关问题时调用。"
    )
    required_roles = {
        # DB 真实角色
        "platform_admin", "ops_analyst", "ml_engineer", "auditor",
        # legacy 兼容
        "super_admin",
    }
    mode = {"ops"}
    summarization_hint = (
        "总结 prompt 查询时，优先展示版本号、最近更新时间、活跃/草稿状态；"
        "按 agent_name 聚合时说明哪些 agent 的 prompt 最近有变动。"
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "query_type": {
                "type": "string",
                "enum": ["recent_published", "version_count"],
                "description": "查询类型: recent_published=最近发布, version_count=版本数量统计",
            },
            "limit": {
                "type": "integer",
                "description": "返回条数",
                "default": 5,
            },
        },
    }

    async def execute(
        self, question: str, context: SkillContext
    ) -> AsyncGenerator[CopilotEvent, None]:
        query_type = context.tool_args.get("query_type", "recent_published")
        limit = int(context.tool_args.get("limit", 5))

        try:
            from backend.database import _get_async_engine, _async_session_factory
            from sqlalchemy import text
            _get_async_engine()
            assert _async_session_factory is not None
            async with _async_session_factory() as db:
                data, title = await self._dispatch(db, text, query_type, limit)
        except Exception as e:
            logger.warning(f"[PromptQuerySkill] query failed: {e}")
            data = {"error": str(e), "hint": "数据库可能不可达或 prompts 表缺失"}
            title = "Prompt 查询（降级）"

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
                {"type": "question", "label": "最近发布了哪些 prompt？"},
                {"type": "question", "label": "哪些 prompt 版本最多？"},
            ],
        )
        yield CopilotEvent(
            type=EventType.TOOL_RESULT,
            data=data if isinstance(data, dict) else {"results": data},
        )

    async def _dispatch(self, db, text_fn, query_type: str, limit: int):
        """SQL 路由，便于测试通过 mock db 直接调。"""
        if query_type == "recent_published":
            result = await db.execute(
                text_fn(
                    "SELECT name, agent_name, version, updated_at "
                    "FROM prompts WHERE status='active' "
                    "ORDER BY updated_at DESC LIMIT :lim"
                ),
                {"lim": limit},
            )
            rows = result.fetchall()
            data = [
                {
                    "name": r[0],
                    "agent_name": r[1],
                    "version": r[2],
                    "updated_at": str(r[3]) if r[3] else None,
                }
                for r in rows
            ]
            return data, f"最近发布的 Prompt — {len(data)} 条"

        # version_count
        result = await db.execute(
            text_fn(
                "SELECT name, COUNT(*) AS version_count "
                "FROM prompts GROUP BY name "
                "ORDER BY version_count DESC LIMIT :lim"
            ),
            {"lim": limit},
        )
        rows = result.fetchall()
        data = [
            {"name": r[0], "version_count": int(r[1]) if r[1] is not None else 0}
            for r in rows
        ]
        return data, f"Prompt 版本数量统计 — Top {len(data)}"


prompt_query_skill = PromptQuerySkill()
