# -*- coding: utf-8 -*-
"""舆情分析 Skill — 封装 SentimentIntelligenceService"""
from __future__ import annotations

from typing import AsyncGenerator

from backend.copilot.base_skill import BaseCopilotSkill, SkillContext
from backend.copilot.events import CopilotEvent, EventType


class SentimentSkill(BaseCopilotSkill):
    name = "sentiment_skill"
    display_name = "舆情分析"
    description = "查询用户评价的情感分布、负面舆情占比、热门话题。当用户询问舆情、评价、口碑、负面反馈、情感分析相关问题时调用。"
    required_roles = {
        # DB 真实角色
        "platform_admin", "ops_analyst", "ml_engineer",
        "customer_service_manager", "employee",
        # legacy 兼容
        "super_admin", "business_admin", "biz_operator", "biz_viewer",
    }
    mode = {"ops", "biz"}
    parameters_schema = {
        "type": "object",
        "properties": {
            "negative_threshold": {
                "type": "number",
                "description": "负面预警阈值，默认0.3（超过30%触发预警）",
                "default": 0.3,
            },
            "top_n_themes": {
                "type": "integer",
                "description": "返回热门主题数量",
                "default": 5,
            },
        },
    }

    async def execute(self, question: str, context: SkillContext) -> AsyncGenerator[CopilotEvent, None]:
        from backend.services.sentiment_intelligence_service import (
            sentiment_intelligence_service, SentimentRequest,
        )

        request = SentimentRequest(
            negative_threshold=context.tool_args.get("negative_threshold", 0.3),
            top_n_themes=context.tool_args.get("top_n_themes", 5),
        )

        result = sentiment_intelligence_service.analyze(request)

        yield CopilotEvent(
            type=EventType.ARTIFACT_START,
            artifact_type="sentiment_overview",
            metadata={
                "title": f"舆情分析 — {result.total_reviews} 条评价",
                "component": "SentimentArtifact",
            },
        )
        yield CopilotEvent(
            type=EventType.ARTIFACT_DELTA,
            content={
                "summary": {
                    "total_reviews": result.total_reviews,
                    "positive_ratio": result.positive_ratio,
                    "neutral_ratio": result.neutral_ratio,
                    "negative_ratio": result.negative_ratio,
                    "negative_alert": result.negative_alert,
                },
                "top_themes": [t.model_dump() for t in result.top_themes],
            },
        )
        yield CopilotEvent(type=EventType.ARTIFACT_END)

        suggestions = [
            {"type": "question", "label": "负面评价集中在哪些方面？"},
            {"type": "question", "label": "最近负面趋势有变化吗？"},
        ]

        if result.negative_alert:
            suggestions.insert(0, {
                "type": "action",
                "label": "通知运营群: 舆情负面占比过高",
                "action": "feishu_notify",
                "payload": {
                    "group": "biz_daily",
                    "message": (
                        f"舆情预警: 负面占比 {result.negative_ratio:.1%}，"
                        f"共 {result.total_reviews} 条评价"
                    ),
                },
            })

        yield CopilotEvent(type=EventType.SUGGESTIONS, items=suggestions)
        yield CopilotEvent(type=EventType.TOOL_RESULT, data=result.model_dump())


sentiment_skill = SentimentSkill()
