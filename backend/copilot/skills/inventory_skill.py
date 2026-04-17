# -*- coding: utf-8 -*-
"""库存优化 Skill — 封装 InventoryOptimizationService"""
from __future__ import annotations

from typing import AsyncGenerator

from backend.copilot.base_skill import BaseCopilotSkill, SkillContext
from backend.copilot.events import CopilotEvent, EventType


class InventorySkill(BaseCopilotSkill):
    name = "inventory_skill"
    display_name = "库存优化分析"
    description = "查询库存状态、计算安全库存和EOQ、识别紧急补货SKU、生成补货建议。当用户询问库存、补货、缺货、安全库存、SKU相关问题时调用。"
    required_roles = {
        # DB 真实角色
        "platform_admin", "ops_analyst", "customer_service_manager",
        # legacy 兼容
        "super_admin", "business_admin", "biz_operator",
    }
    mode = {"ops", "biz"}
    parameters_schema = {
        "type": "object",
        "properties": {
            "store_id": {"type": "string", "description": "门店ID，可选，不指定则查询所有门店"},
            "action": {
                "type": "string",
                "enum": ["overview", "urgent_only", "specific_sku"],
                "description": "查询类型：overview=全局概览, urgent_only=仅看紧急补货, specific_sku=指定SKU",
            },
        },
    }
    summarization_hint = (
        "库存分析摘要要求：\n"
        "- 必须引用 total_skus、urgent_count、total_reorder_qty 三个核心指标\n"
        "- 如果用户要求列出SKU，必须从 recommendations 中挑出 urgent=true 的条目，列出 sku_code、store_id、current_stock、shortage_days、eoq\n"
        "- 如果用户只要求数量，直接给出 urgent_count 数字即可，不需要长篇分析\n"
        "- 补货建议必须具体到'立即采购 SKU xxx，补货量 yyy'"
    )

    async def execute(self, question: str, context: SkillContext) -> AsyncGenerator[CopilotEvent, None]:
        import asyncio
        from backend.services.inventory_optimization_service import (
            inventory_optimization_service, InventoryRequest,
        )

        request = InventoryRequest(
            store_id=context.tool_args.get("store_id"),
            lead_time_days=7.0,
        )

        result = await asyncio.to_thread(inventory_optimization_service.optimize, request)

        # Artifact: 交互式库存表格
        yield CopilotEvent(
            type=EventType.ARTIFACT_START,
            artifact_type="inventory_table",
            metadata={
                "title": f"库存优化建议 — {result.total_skus} 支SKU",
                "component": "InventoryArtifact",
            },
        )
        yield CopilotEvent(
            type=EventType.ARTIFACT_DELTA,
            content={
                "summary": {
                    "total_skus": result.total_skus,
                    "urgent_count": result.urgent_count,
                    "total_reorder_qty": result.total_reorder_qty,
                },
                "recommendations": [r.model_dump() for r in result.recommendations[:20]],
            },
        )
        yield CopilotEvent(type=EventType.ARTIFACT_END)

        # 紧急补货时触发 Action 建议
        if result.urgent_count > 0:
            yield CopilotEvent(
                type=EventType.SUGGESTIONS,
                items=[
                    {
                        "type": "action",
                        "label": f"通知采购群: {result.urgent_count} 支SKU需紧急补货",
                        "action": "feishu_notify",
                        "payload": {
                            "group": "procurement",
                            "message": (
                                f"库存预警: {result.urgent_count} 支SKU库存低于安全水位，"
                                f"建议补货总量 {result.total_reorder_qty:,}"
                            ),
                        },
                    },
                    {"type": "question", "label": "哪些SKU预计3天内缺货？"},
                    {"type": "question", "label": "按门店分组查看库存状态"},
                ],
            )

        yield CopilotEvent(type=EventType.TOOL_RESULT, data=result.model_dump())


# 模块级实例 — 供 auto_discover 注册
inventory_skill = InventorySkill()
