# -*- coding: utf-8 -*-
"""运维 Trace Skill — 查询 Run/Trace 信息（仅 ops 模式）"""
from __future__ import annotations

from typing import AsyncGenerator

from loguru import logger

from backend.copilot.base_skill import BaseCopilotSkill, SkillContext
from backend.copilot.events import CopilotEvent, EventType


class TraceSkill(BaseCopilotSkill):
    name = "trace_skill"
    display_name = "Trace 诊断"
    description = "查询最近的 Run 记录、失败 Run、最慢 Run、Run 详情。当用户询问 trace、run、执行记录、失败任务、延迟相关问题时调用。"
    required_roles = {
        # DB 真实角色
        "platform_admin", "ops_analyst", "ml_engineer", "auditor",
        # legacy 兼容
        "super_admin",
    }
    mode = {"ops"}
    parameters_schema = {
        "type": "object",
        "properties": {
            "query_type": {
                "type": "string",
                "enum": ["recent_failures", "slowest", "run_detail", "summary"],
                "description": "查询类型",
            },
            "run_id": {
                "type": "string",
                "description": "指定 Run ID（query_type=run_detail 时使用）",
            },
            "limit": {
                "type": "integer",
                "description": "返回条数",
                "default": 5,
            },
        },
    }

    async def execute(self, question: str, context: SkillContext) -> AsyncGenerator[CopilotEvent, None]:
        query_type = context.tool_args.get("query_type", "summary")
        limit = context.tool_args.get("limit", 5)

        try:
            from backend.database import _get_async_engine, _async_session_factory
            from sqlalchemy import text
            _get_async_engine()
            assert _async_session_factory is not None

            async with _async_session_factory() as db:
                if query_type == "recent_failures":
                    result = await db.execute(
                        text(
                            "SELECT run_id, workflow_name, status, error_message, started_at "
                            "FROM runs WHERE status = 'failed' "
                            "ORDER BY started_at DESC LIMIT :lim"
                        ),
                        {"lim": limit},
                    )
                    rows = result.fetchall()
                    data = [
                        {"run_id": r[0], "workflow": r[1], "status": r[2], "error": r[3], "started_at": str(r[4])}
                        for r in rows
                    ]
                    title = f"最近失败的 Run — {len(data)} 条"

                elif query_type == "slowest":
                    result = await db.execute(
                        text(
                            "SELECT run_id, workflow_name, status, "
                            "TIMESTAMPDIFF(SECOND, started_at, ended_at) AS duration_sec "
                            "FROM runs WHERE ended_at IS NOT NULL "
                            "ORDER BY duration_sec DESC LIMIT :lim"
                        ),
                        {"lim": limit},
                    )
                    rows = result.fetchall()
                    data = [
                        {"run_id": r[0], "workflow": r[1], "status": r[2], "duration_sec": r[3]}
                        for r in rows
                    ]
                    title = f"最慢的 Run — Top {len(data)}"

                elif query_type == "run_detail":
                    run_id = context.tool_args.get("run_id", "")
                    result = await db.execute(
                        text("SELECT * FROM runs WHERE run_id = :rid"),
                        {"rid": run_id},
                    )
                    row = result.fetchone()
                    data = dict(row._mapping) if row else {"error": f"Run {run_id} 不存在"}
                    title = f"Run 详情 — {run_id[:8]}"

                else:  # summary
                    result = await db.execute(
                        text(
                            "SELECT COUNT(*) as total, "
                            "SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed, "
                            "SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) as success "
                            "FROM runs WHERE started_at > DATE_SUB(NOW(), INTERVAL 24 HOUR)"
                        )
                    )
                    row = result.fetchone()
                    data = {"total": row[0], "failed": row[1], "success": row[2], "period": "24h"}
                    title = "Run 统计概览（24h）"

        except Exception as e:
            logger.warning(f"[TraceSkill] 查询失败: {e}")
            data = {"error": str(e), "hint": "数据库可能不可达"}
            title = "Trace 查询"

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
                {"type": "question", "label": "最近有失败的 Run 吗？"},
                {"type": "question", "label": "最慢的 5 个 Run 是哪些？"},
                {"type": "question", "label": "系统整体健康状态如何？"},
            ],
        )

        yield CopilotEvent(type=EventType.TOOL_RESULT, data=data if isinstance(data, dict) else {"results": data})


trace_skill = TraceSkill()
