# -*- coding: utf-8 -*-
"""客户洞察 Skill — 封装 CustomerIntelligenceService"""
from __future__ import annotations

from typing import AsyncGenerator

from backend.copilot.base_skill import BaseCopilotSkill, SkillContext
from backend.copilot.events import CopilotEvent, EventType


class CustomerIntelSkill(BaseCopilotSkill):
    name = "customer_intel_skill"
    display_name = "客户洞察分析"
    description = "查询客户RFM分群、流失风险预测、客户生命周期价值(CLV)排行、客户聚类分析。当用户询问客户分析、流失预警、高价值客户、RFM、CLV相关问题时调用。"
    required_roles = {
        # DB 真实角色
        "platform_admin", "ops_analyst",
        "risk_reviewer", "customer_service_manager", "employee",
        # legacy 兼容
        "super_admin", "business_admin", "biz_operator", "biz_viewer",
    }
    mode = {"ops", "biz"}
    parameters_schema = {
        "type": "object",
        "properties": {
            "analysis_types": {
                "type": "array",
                "items": {"type": "string", "enum": ["rfm", "churn", "clv", "cluster", "all"]},
                "description": "分析类型列表，可选: rfm/churn/clv/cluster/all",
                "default": ["rfm", "churn", "clv"],
            },
            "top_n": {
                "type": "integer",
                "description": "返回Top N客户数量",
                "default": 10,
            },
            "segment_filter": {
                "type": "string",
                "description": "仅分析指定客户分群，可选",
            },
        },
    }
    summarization_hint = (
        "客户洞察摘要要求：\n"
        "- 必须引用 rfm_total_customers、churn_high_risk_count、churn_high_risk_ratio、clv_avg_90d\n"
        "- 如果用户问流失率，必须给出 churn_high_risk_ratio 的百分比和 churn_high_risk_count 的人数\n"
        "- 如果用户问高价值客户，必须从 clv_top_customers 中列出 customer_id 和 clv_90d 金额\n"
        "- 客户分群必须列出每个群的名称、人数占比、特征描述\n"
        "- 运营建议必须具体到'对 xx 群的 yy 名客户执行 zz 动作'"
    )

    async def execute(self, question: str, context: SkillContext) -> AsyncGenerator[CopilotEvent, None]:
        from backend.services.customer_intelligence_service import (
            customer_intelligence_service, CustomerIntelRequest,
        )

        request = CustomerIntelRequest(
            analysis_types=context.tool_args.get("analysis_types", ["rfm", "churn", "clv"]),
            top_n=context.tool_args.get("top_n", 10),
            segment_filter=context.tool_args.get("segment_filter"),
        )

        result = customer_intelligence_service.analyze(request)

        yield CopilotEvent(
            type=EventType.ARTIFACT_START,
            artifact_type="customer_insight",
            metadata={
                "title": f"客户洞察 — {result.rfm_total_customers} 名客户",
                "component": "CustomerArtifact",
            },
        )
        yield CopilotEvent(
            type=EventType.ARTIFACT_DELTA,
            content={
                "summary": {
                    "rfm_total_customers": result.rfm_total_customers,
                    "churn_high_risk_count": result.churn_high_risk_count,
                    "churn_high_risk_ratio": result.churn_high_risk_ratio,
                    "clv_avg_90d": result.clv_avg_90d,
                    "clv_median_90d": result.clv_median_90d,
                    "cluster_count": result.cluster_count,
                },
                "rfm_segment_distribution": [s.model_dump() for s in result.rfm_segment_distribution],
                "churn_top_risk": [c.model_dump() for c in result.churn_top_risk],
                "clv_top_customers": [c.model_dump() for c in result.clv_top_customers],
                "cluster_distribution": [c.model_dump() for c in result.cluster_distribution],
            },
        )
        yield CopilotEvent(type=EventType.ARTIFACT_END)

        suggestions = [
            {"type": "question", "label": "高流失风险客户有哪些特征？"},
            {"type": "question", "label": "Top10高价值客户详情"},
            {"type": "question", "label": "各分群的购买行为差异"},
        ]

        if result.churn_high_risk_count > 0:
            suggestions.insert(0, {
                "type": "action",
                "label": f"通知运营群: {result.churn_high_risk_count} 名客户流失风险高",
                "action": "feishu_notify",
                "payload": {
                    "group": "biz_daily",
                    "message": (
                        f"客户流失预警: {result.churn_high_risk_count} 名客户流失风险高 "
                        f"({result.churn_high_risk_ratio:.1%})，建议及时干预"
                    ),
                },
            })

        yield CopilotEvent(type=EventType.SUGGESTIONS, items=suggestions)
        yield CopilotEvent(type=EventType.TOOL_RESULT, data=result.model_dump())


customer_intel_skill = CustomerIntelSkill()
