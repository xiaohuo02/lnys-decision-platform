# -*- coding: utf-8 -*-
"""关联分析 Skill — 封装 AssociationMiningService"""
from __future__ import annotations

from typing import AsyncGenerator

from backend.copilot.base_skill import BaseCopilotSkill, SkillContext
from backend.copilot.events import CopilotEvent, EventType


class AssociationSkill(BaseCopilotSkill):
    name = "association_skill"
    display_name = "关联分析"
    description = "查询商品关联规则、购物篮分析、搭配推荐。当用户询问关联分析、商品搭配、购物篮、交叉销售相关问题时调用。"
    required_roles = {
        # DB 真实角色
        "platform_admin", "customer_service_manager",
        # legacy 兼容
        "super_admin", "business_admin", "biz_operator",
    }
    mode = {"ops", "biz"}
    parameters_schema = {
        "type": "object",
        "properties": {
            "min_lift": {
                "type": "number",
                "description": "最小提升度阈值",
                "default": 1.2,
            },
            "min_confidence": {
                "type": "number",
                "description": "最小置信度阈值",
                "default": 0.3,
            },
            "top_n": {
                "type": "integer",
                "description": "返回Top N关联规则",
                "default": 20,
            },
        },
    }

    async def execute(self, question: str, context: SkillContext) -> AsyncGenerator[CopilotEvent, None]:
        from backend.services.association_mining_service import (
            association_mining_service, AssociationRequest,
        )

        page_ctx = context.page_context or {}
        selected_node = page_ctx.get("selected_node")
        selected_rule = page_ctx.get("selected_rule")

        sku_codes = None
        if selected_node:
            sku_codes = [selected_node]
        elif selected_rule and isinstance(selected_rule, dict):
            ant = selected_rule.get("antecedents", "")
            con = selected_rule.get("consequents", "")
            sku_codes = [s.strip() for s in f"{ant},{con}".split(",") if s.strip()]

        request = AssociationRequest(
            sku_codes=sku_codes,
            min_lift=context.tool_args.get("min_lift", 1.2),
            min_confidence=context.tool_args.get("min_confidence", 0.3),
            top_n=context.tool_args.get("top_n", 20),
        )

        result = association_mining_service.query(request)

        artifact_title = "关联分析 — 商品搭配网络"
        if selected_node:
            artifact_title = f"关联分析 — {selected_node} 的商品搭配"

        yield CopilotEvent(
            type=EventType.ARTIFACT_START,
            artifact_type="association_graph",
            metadata={
                "title": artifact_title,
                "component": "AssociationArtifact",
            },
        )
        yield CopilotEvent(
            type=EventType.ARTIFACT_DELTA,
            content=result.model_dump() if hasattr(result, "model_dump") else result,
        )
        yield CopilotEvent(type=EventType.ARTIFACT_END)

        suggestions = [
            {"type": "question", "label": "哪些商品经常一起购买？"},
            {"type": "question", "label": "热门搭配推荐建议"},
        ]
        if selected_node:
            suggestions = [
                {"type": "question", "label": f"{selected_node} 的搭配促销方案"},
                {"type": "question", "label": f"查看 {selected_node} 库存状态"},
                {"type": "question", "label": "查询交叉营销 SOP 文档"},
            ]
        yield CopilotEvent(type=EventType.SUGGESTIONS, items=suggestions)

        data = result.model_dump() if hasattr(result, "model_dump") else {"raw": str(result)}
        yield CopilotEvent(type=EventType.TOOL_RESULT, data=data)


association_skill = AssociationSkill()
