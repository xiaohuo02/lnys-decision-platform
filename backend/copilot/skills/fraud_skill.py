# -*- coding: utf-8 -*-
"""欺诈检测 Skill — 封装 FraudScoringService（仅 ops 模式）"""
from __future__ import annotations

from typing import AsyncGenerator

from backend.copilot.base_skill import BaseCopilotSkill, SkillContext
from backend.copilot.events import CopilotEvent, EventType


class FraudSkill(BaseCopilotSkill):
    name = "fraud_skill"
    display_name = "欺诈风控分析"
    description = "查询欺诈风险评分、异常交易检测、风控统计、风控态势、拦截率、高风险交易特征。当用户询问风控、欺诈、风险、异常交易、拦截率、可疑交易、风控态势、风控概况、风控报告、风险评估、交易安全等相关问题时必须调用此工具（不要用知识库搜索）。"
    required_roles = {
        # DB 真实角色
        "platform_admin", "ops_analyst", "ml_engineer", "risk_reviewer",
        # legacy 兼容
        "super_admin", "business_admin", "biz_operator",
    }
    mode = {"ops", "biz"}
    parameters_schema = {
        "type": "object",
        "properties": {
            "top_n": {
                "type": "integer",
                "description": "返回Top N高风险交易",
                "default": 10,
            },
        },
    }
    summarization_hint = (
        "风控分析摘要要求：\n"
        "- 必须引用 final_risk_score 具体数值和 risk_level 等级\n"
        "- 必须引用 high_risk_count、hitl_count（需人工审核数）\n"
        "- 如果存在高风险交易，必须列出 transaction_id、金额、风险评分\n"
        "- 建议必须具体：'立即冻结交易 xxx'、'对客户 yyy 发起人工审核'，不能只说'建议关注'"
    )

    async def execute(self, question: str, context: SkillContext) -> AsyncGenerator[CopilotEvent, None]:
        from backend.services.fraud_scoring_service import (
            fraud_scoring_service, FraudScoringRequest,
        )

        request = FraudScoringRequest()

        result = fraud_scoring_service.score(request)

        yield CopilotEvent(
            type=EventType.ARTIFACT_START,
            artifact_type="fraud_detail",
            metadata={
                "title": "欺诈风控分析",
                "component": "FraudArtifact",
            },
        )
        yield CopilotEvent(
            type=EventType.ARTIFACT_DELTA,
            content=result.model_dump() if hasattr(result, "model_dump") else result,
        )
        yield CopilotEvent(type=EventType.ARTIFACT_END)

        # 生成文本摘要，方便 Grader / 用户快速了解结果
        data = result.model_dump() if hasattr(result, "model_dump") else {"raw": str(result)}
        summary = self._build_summary(data)
        yield CopilotEvent(type=EventType.TEXT_DELTA, content=summary)

        yield CopilotEvent(
            type=EventType.SUGGESTIONS,
            items=[
                {"type": "question", "label": "最近有哪些高风险交易？"},
                {"type": "question", "label": "风险分布趋势如何？"},
            ],
        )

        yield CopilotEvent(type=EventType.TOOL_RESULT, data=data)

    @staticmethod
    def _build_summary(data: dict) -> str:
        """将结构化 FraudScoringResult 转换为人类可读的文本摘要"""
        scores = data.get("scores", [])
        high = data.get("high_risk_count", 0)
        hitl = data.get("hitl_count", 0)
        total = len(scores)

        lines = [f"风控检测完成，共扫描 {total} 笔交易。"]
        if high:
            lines.append(f"发现 {high} 笔高风险交易，{hitl} 笔需要人工审核。")
        else:
            lines.append("未发现高风险交易。")

        for s in scores[:5]:
            txn = s.get("transaction_id", "未知")
            level = s.get("risk_level", "未知")
            score = s.get("final_score", 0)
            lines.append(f"  - 交易 {txn}：风险评分 {score:.4f}，等级 {level}")

        if total > 5:
            lines.append(f"  ... 及其余 {total - 5} 笔交易")

        return "\n".join(lines)


fraud_skill = FraudSkill()
