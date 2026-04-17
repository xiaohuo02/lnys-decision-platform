# -*- coding: utf-8 -*-
"""backend/copilot/skills/review_query_skill.py — 人工审核队列查询 Skill (R6-3)

从 OpsCopilotReadRepository.get_pending_reviews 抽出。
查询 review_cases 表: 审核总量 + 最近待审列表。
"""
from __future__ import annotations

from typing import AsyncGenerator

from loguru import logger

from backend.copilot.base_skill import BaseCopilotSkill, SkillContext
from backend.copilot.events import CopilotEvent, EventType


class ReviewQuerySkill(BaseCopilotSkill):
    name = "review_query_skill"
    display_name = "审核队列查询"
    description = (
        "查询人工审核队列 (review_cases): 各状态案件统计 + 最近待审列表。"
        "当用户询问审核/待审/review/HITL 相关问题时调用。"
    )
    required_roles = {
        # DB 真实角色
        "platform_admin", "ops_analyst", "ml_engineer",
        "risk_reviewer", "auditor",
        # legacy 兼容
        "super_admin",
    }
    mode = {"ops"}
    summarization_hint = (
        "先给 pending 案件数量；若有高优先级案件（priority=high）单独列出；"
        "若 in_review 持续时间超过 2 小时，标为需要跟进。"
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "最近待审案件返回条数",
                "default": 5,
            },
        },
    }

    async def execute(
        self, question: str, context: SkillContext
    ) -> AsyncGenerator[CopilotEvent, None]:
        limit = int(context.tool_args.get("limit", 5))

        try:
            from backend.database import _get_async_engine, _async_session_factory
            from sqlalchemy import text
            _get_async_engine()
            assert _async_session_factory is not None
            async with _async_session_factory() as db:
                data, title = await self._dispatch(db, text, limit)
        except Exception as e:
            logger.warning(f"[ReviewQuerySkill] query failed: {e}")
            data = {"error": str(e), "hint": "数据库可能不可达或 review_cases 表缺失"}
            title = "审核队列查询（降级）"

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
                {"type": "question", "label": "有多少待审案件？"},
                {"type": "question", "label": "最近的待审案件是哪些？"},
            ],
        )
        yield CopilotEvent(
            type=EventType.TOOL_RESULT,
            data=data if isinstance(data, dict) else {"results": data},
        )

    async def _dispatch(self, db, text_fn, limit: int):
        """查询审核队列统计 + 最近待审列表。"""
        stats_result = await db.execute(
            text_fn(
                "SELECT COUNT(*) AS total, "
                "SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) AS pending, "
                "SUM(CASE WHEN status='in_review' THEN 1 ELSE 0 END) AS in_review, "
                "SUM(CASE WHEN status='approved' THEN 1 ELSE 0 END) AS approved, "
                "SUM(CASE WHEN status='rejected' THEN 1 ELSE 0 END) AS rejected "
                "FROM review_cases"
            )
        )
        srow = stats_result.fetchone()
        stats = {
            "total": int(srow[0]) if srow and srow[0] is not None else 0,
            "pending": int(srow[1]) if srow and srow[1] is not None else 0,
            "in_review": int(srow[2]) if srow and srow[2] is not None else 0,
            "approved": int(srow[3]) if srow and srow[3] is not None else 0,
            "rejected": int(srow[4]) if srow and srow[4] is not None else 0,
        }

        recent_result = await db.execute(
            text_fn(
                "SELECT case_id, review_type, priority, status, subject, created_at "
                "FROM review_cases WHERE status IN ('pending','in_review') "
                "ORDER BY created_at DESC LIMIT :lim"
            ),
            {"lim": limit},
        )
        recent_rows = recent_result.fetchall()
        recent = [
            {
                "case_id": r[0],
                "review_type": r[1],
                "priority": r[2],
                "status": r[3],
                "subject": r[4],
                "created_at": str(r[5]) if r[5] else None,
            }
            for r in recent_rows
        ]
        data = {"stats": stats, "recent": recent}
        title = f"审核队列 — {stats['pending']} 待审 / {stats['in_review']} 复审中"
        return data, title


review_query_skill = ReviewQuerySkill()
