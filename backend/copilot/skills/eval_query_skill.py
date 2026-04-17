# -*- coding: utf-8 -*-
"""backend/copilot/skills/eval_query_skill.py — 评测实验查询 Skill (R6-3 示范)

职责:
  从 eval_experiments 表查询评测数据, 供 ops 管理员检查测试通过率趋势。

背景 (R6-3):
  OpsCopilotAgent 里 OpsCopilotReadRepository 有 get_recent_experiments +
  get_lowest_pass_rate_experiment 两个方法; 这些都是纯数据 SELECT, 可以直接
  抽成 Skill 让 CopilotEngine 通过 FC 路由调用，不需要再走 Agent 中转。

  本 Skill 作为 R6-3 的示范成果:
    - 从 Agent 抽出的"单次能力调用" ≈ Skill 的定义
    - Agent 原样保留（渐进迁移，不破坏存量行为）
    - Skill 注册后 ops 模式可用，可被 CopilotEngine FC 路由命中

查询类型:
  - recent          返回最近 N 次评测实验列表
  - lowest_pass     返回 pass_rate 最低的一次已完成实验
  - summary         返回评测模块的整体统计（实验数 / 平均 pass_rate / 完成率）
"""
from __future__ import annotations

from typing import AsyncGenerator

from loguru import logger

from backend.copilot.base_skill import BaseCopilotSkill, SkillContext
from backend.copilot.events import CopilotEvent, EventType


class EvalQuerySkill(BaseCopilotSkill):
    name = "eval_query_skill"
    display_name = "评测实验查询"
    description = (
        "查询评测实验 (eval_experiments) 的最近记录、通过率最低的实验，以及整体评测统计。"
        "当用户询问 eval/评测/实验/pass rate/accuracy 相关问题时调用。"
    )
    required_roles = {
        # DB 真实角色
        "platform_admin", "ops_analyst", "ml_engineer", "auditor",
        # legacy 兼容
        "super_admin",
    }
    mode = {"ops"}
    summarization_hint = (
        "总结评测结果时，优先给出 pass_rate 最低的实验并提示可能原因；"
        "如果 pass_rate < 70% 标为高风险；给出具体的实验名和时间。"
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "query_type": {
                "type": "string",
                "enum": ["recent", "lowest_pass", "summary"],
                "description": "查询类型",
            },
            "limit": {
                "type": "integer",
                "description": "返回条数（query_type=recent 时有效）",
                "default": 5,
            },
        },
    }

    async def execute(
        self, question: str, context: SkillContext
    ) -> AsyncGenerator[CopilotEvent, None]:
        query_type = context.tool_args.get("query_type", "summary")
        limit = int(context.tool_args.get("limit", 5))

        try:
            from backend.database import _get_async_engine, _async_session_factory
            from sqlalchemy import text

            _get_async_engine()
            assert _async_session_factory is not None

            async with _async_session_factory() as db:
                data, title = await self._dispatch(db, text, query_type, limit)
        except Exception as e:
            logger.warning(f"[EvalQuerySkill] query failed: {e}")
            data = {"error": str(e), "hint": "数据库可能不可达或 eval_experiments 表缺失"}
            title = "评测查询（降级）"

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
                {"type": "question", "label": "最近有哪些评测实验？"},
                {"type": "question", "label": "通过率最低的实验是哪个？"},
                {"type": "question", "label": "整体评测通过率趋势怎样？"},
            ],
        )

        yield CopilotEvent(
            type=EventType.TOOL_RESULT,
            data=data if isinstance(data, dict) else {"results": data},
        )

    async def _dispatch(self, db, text_fn, query_type: str, limit: int):
        """内部路由: 按 query_type 分发到具体查询逻辑。

        拆出来是为了让测试可以 monkeypatch 单个查询路径。
        """
        if query_type == "recent":
            result = await db.execute(
                text_fn(
                    "SELECT experiment_id, name, status, pass_rate, created_at "
                    "FROM eval_experiments "
                    "ORDER BY created_at DESC LIMIT :lim"
                ),
                {"lim": limit},
            )
            rows = result.fetchall()
            data = [
                {
                    "experiment_id": r[0],
                    "name": r[1],
                    "status": r[2],
                    "pass_rate": float(r[3]) if r[3] is not None else None,
                    "created_at": str(r[4]) if r[4] else None,
                }
                for r in rows
            ]
            title = f"最近的评测实验 — {len(data)} 条"
            return data, title

        if query_type == "lowest_pass":
            result = await db.execute(
                text_fn(
                    "SELECT experiment_id, name, pass_rate, created_at "
                    "FROM eval_experiments "
                    "WHERE status='completed' "
                    "ORDER BY pass_rate ASC LIMIT 1"
                )
            )
            row = result.fetchone()
            if row is None:
                return {"error": "暂无已完成的评测实验"}, "通过率最低的评测（无数据）"
            data = {
                "experiment_id": row[0],
                "name": row[1],
                "pass_rate": float(row[2]) if row[2] is not None else None,
                "created_at": str(row[3]) if row[3] else None,
            }
            # 风险标注（对应 summarization_hint 中的阈值）
            if data["pass_rate"] is not None and data["pass_rate"] < 0.7:
                data["risk_level"] = "high"
            else:
                data["risk_level"] = "normal"
            title = f"通过率最低的评测 — {data['name']}"
            return data, title

        # summary
        result = await db.execute(
            text_fn(
                "SELECT COUNT(*) AS total, "
                "SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed, "
                "AVG(CASE WHEN status='completed' THEN pass_rate ELSE NULL END) AS avg_pass "
                "FROM eval_experiments "
                "WHERE created_at > DATE_SUB(NOW(), INTERVAL 30 DAY)"
            )
        )
        row = result.fetchone()
        total = int(row[0]) if row and row[0] is not None else 0
        completed = int(row[1]) if row and row[1] is not None else 0
        avg_pass = float(row[2]) if row and row[2] is not None else None
        data = {
            "period": "30d",
            "total": total,
            "completed": completed,
            "completion_rate": (completed / total) if total else 0.0,
            "avg_pass_rate": avg_pass,
        }
        title = "评测模块统计（近 30 天）"
        return data, title


eval_query_skill = EvalQuerySkill()
