# -*- coding: utf-8 -*-
"""销售预测 Skill — 封装 SalesForecastService"""
from __future__ import annotations

from typing import AsyncGenerator

from backend.copilot.base_skill import BaseCopilotSkill, SkillContext
from backend.copilot.events import CopilotEvent, EventType


class ForecastSkill(BaseCopilotSkill):
    name = "forecast_skill"
    display_name = "销售预测"
    description = "查询未来N天销售预测数据、模型对比、预测趋势。当用户询问销售预测、销量趋势、未来销售、预测准确率相关问题时调用。"
    required_roles = {
        # DB 真实角色
        "platform_admin", "ops_analyst", "ml_engineer",
        # legacy 兼容
        "super_admin", "business_admin", "biz_operator",
    }
    mode = {"ops", "biz"}
    parameters_schema = {
        "type": "object",
        "properties": {
            "forecast_days": {
                "type": "integer",
                "description": "预测天数，默认7天",
                "default": 7,
            },
            "compare_models": {
                "type": "boolean",
                "description": "是否进行模型对比",
                "default": False,
            },
        },
    }

    async def execute(self, question: str, context: SkillContext) -> AsyncGenerator[CopilotEvent, None]:
        from backend.services.sales_forecast_service import (
            sales_forecast_service, ForecastRequest,
        )

        request = ForecastRequest(
            forecast_days=context.tool_args.get("forecast_days", 7),
            compare_models=context.tool_args.get("compare_models", False),
        )

        result = sales_forecast_service.forecast(request)

        yield CopilotEvent(
            type=EventType.ARTIFACT_START,
            artifact_type="forecast_chart",
            metadata={
                "title": f"销售预测 — 未来{result.forecast_days}天（{result.model_used}）",
                "component": "ForecastArtifact",
            },
        )
        yield CopilotEvent(
            type=EventType.ARTIFACT_DELTA,
            content={
                "summary": {
                    "model_used": result.model_used,
                    "forecast_days": result.forecast_days,
                    "total_forecast": result.total_forecast,
                    "mape": result.mape,
                    "degraded": result.degraded,
                },
                "daily_forecast": [
                    {"date": d.ds, "value": d.forecast, "lower": d.lower_bound, "upper": d.upper_bound}
                    for d in result.daily_forecast
                ],
                "model_comparison": [m.model_dump() for m in result.model_comparison] if result.model_comparison else [],
            },
        )
        yield CopilotEvent(type=EventType.ARTIFACT_END)

        yield CopilotEvent(
            type=EventType.SUGGESTIONS,
            items=[
                {"type": "question", "label": "预测准确率如何？MAPE是多少？"},
                {"type": "question", "label": "对比不同预测模型的表现"},
                {"type": "question", "label": "基于预测结果，库存需要怎么调整？"},
            ],
        )

        yield CopilotEvent(type=EventType.TOOL_RESULT, data=result.model_dump())


forecast_skill = ForecastSkill()
