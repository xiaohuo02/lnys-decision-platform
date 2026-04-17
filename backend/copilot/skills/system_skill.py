# -*- coding: utf-8 -*-
"""系统健康 Skill — 查询系统状态（仅 ops 模式）"""
from __future__ import annotations

from typing import AsyncGenerator

from loguru import logger

from backend.copilot.base_skill import BaseCopilotSkill, SkillContext
from backend.copilot.events import CopilotEvent, EventType


class SystemSkill(BaseCopilotSkill):
    name = "system_skill"
    display_name = "系统健康监控"
    description = "查询系统健康状态、数据库连接、Redis 连接、Agent 就绪状态、服务运行指标。当用户询问系统状态、健康检查、服务是否正常相关问题时调用。"
    required_roles = {
        # DB 真实角色
        "platform_admin", "ops_analyst",
        # legacy 兼容
        "super_admin",
    }
    mode = {"ops"}
    parameters_schema = {
        "type": "object",
        "properties": {
            "check_type": {
                "type": "string",
                "enum": ["full", "db", "redis", "agents", "services"],
                "description": "检查类型",
                "default": "full",
            },
        },
    }

    async def execute(self, question: str, context: SkillContext) -> AsyncGenerator[CopilotEvent, None]:
        check_type = context.tool_args.get("check_type", "full")
        health_data = {}

        try:
            if check_type in ("full", "db"):
                from backend.database import check_db_health
                health_data["mysql"] = await check_db_health()

            if check_type in ("full", "redis"):
                from backend.database import check_redis_health
                health_data["redis"] = await check_redis_health()

            if check_type in ("full", "agents"):
                # Agent 注册表状态从 app.state 获取（此处做安全回退）
                try:
                    from backend.services import (
                        customer_intelligence_service,
                        sales_forecast_service,
                        fraud_scoring_service,
                        sentiment_intelligence_service,
                        inventory_optimization_service,
                        association_mining_service,
                    )
                    health_data["services"] = {
                        "customer_intelligence": "ready" if customer_intelligence_service else "not_loaded",
                        "sales_forecast": "ready" if sales_forecast_service else "not_loaded",
                        "fraud_scoring": "ready" if fraud_scoring_service else "not_loaded",
                        "sentiment_intelligence": "ready" if sentiment_intelligence_service else "not_loaded",
                        "inventory_optimization": "ready" if inventory_optimization_service else "not_loaded",
                        "association_mining": "ready" if association_mining_service else "not_loaded",
                    }
                except Exception as e:
                    health_data["services"] = {"error": str(e)}

            if check_type in ("full", "services"):
                try:
                    from backend.config import settings
                    health_data["config"] = {
                        "env": settings.ENV,
                        "llm_model": settings.LLM_MODEL_NAME,
                        "llm_base_url": settings.LLM_BASE_URL[:50],
                        "mock_data": settings.ENABLE_MOCK_DATA,
                        "sentiment_kb": settings.SENTIMENT_KB_ENABLED,
                    }
                except Exception as e:
                    health_data["config"] = {"error": str(e)}

        except Exception as e:
            health_data["error"] = str(e)

        # 判定整体状态
        all_ok = all(
            v == "ok" for k, v in health_data.items()
            if k in ("mysql", "redis") and isinstance(v, str)
        )
        status = "healthy" if all_ok else "degraded"

        yield CopilotEvent(
            type=EventType.ARTIFACT_START,
            artifact_type="generic_table",
            metadata={
                "title": f"系统健康状态 — {status.upper()}",
                "component": "GenericTableArtifact",
            },
        )
        yield CopilotEvent(
            type=EventType.ARTIFACT_DELTA,
            content={"status": status, **health_data},
        )
        yield CopilotEvent(type=EventType.ARTIFACT_END)

        suggestions = [
            {"type": "question", "label": "最近有失败的 Run 吗？"},
            {"type": "question", "label": "各 Agent 的加载状态详情"},
        ]
        if status != "healthy":
            suggestions.insert(0, {
                "type": "action",
                "label": "通知运维群: 系统状态异常",
                "action": "feishu_notify",
                "payload": {
                    "group": "ops_alert",
                    "message": f"系统健康检查: {status}，请及时排查",
                },
            })

        yield CopilotEvent(type=EventType.SUGGESTIONS, items=suggestions)
        yield CopilotEvent(type=EventType.TOOL_RESULT, data={"status": status, **health_data})


system_skill = SystemSkill()
