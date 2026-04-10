# -*- coding: utf-8 -*-
"""backend/agents/insight_composer_agent.py

InsightComposerAgent — 洞察合成 Agent

╔══════════════════════════════════════════════════════════════════╗
║  Agent 契约 (必须在实现前确认)                                     ║
╠══════════════════════════════════════════════════════════════════╣
║  1. 输入                                                          ║
║     InsightComposerInput:                                        ║
║       artifact_refs: List[ArtifactRef]  各 service 产物引用       ║
║       run_id / thread_id                                         ║
║       use_mock: bool  开发/测试时用 mock 数据跳过真实 service       ║
║                                                                  ║
║  2. 允许调用的 service / tool                                     ║
║     - ArtifactRef.summary 字段（读内存，不查 DB）                 ║
║     - ReportRenderingService.render()                            ║
║     - LLM（通过 langchain-openai，生成摘要解释）                  ║
║     - 禁止直接调用 CustomerIntelligenceService 等底层 service     ║
║                                                                  ║
║  3. 输出 schema                                                   ║
║     InsightComposerOutput:                                       ║
║       executive_summary: str  管理层摘要（≤300字）                ║
║       risk_highlights:   str  风险提示（≤200字）                  ║
║       action_plan:       str  行动建议（3~5条）                   ║
║       report_artifact:   ArtifactRef  渲染好的报告引用            ║
║       data_ready: bool                                           ║
║                                                                  ║
║  4. 不能做的事                                                    ║
║     - 重新调用底层 ML 服务重算指标                                 ║
║     - 直接修改数据库任何表                                         ║
║     - 生成包含具体客户 PII 的输出                                  ║
║                                                                  ║
║  5. 失败降级                                                      ║
║     - LLM 不可用 → 用模板拼接各 artifact.summary 作为 fallback    ║
║     - 缺少某 artifact → 跳过该节，标记 partial=True               ║
║     - 全部 artifact 缺失 → data_ready=False + 错误摘要            ║
║                                                                  ║
║  6. 是否进入 HITL                                                 ║
║     不需要                                                        ║
║                                                                  ║
║  7. 依赖的 artifact                                               ║
║     customer_insight / forecast / sentiment / fraud_score        ║
║     inventory / association（可选）                               ║
║                                                                  ║
║  8. 写入 trace 的关键字段                                         ║
║     agent_name="InsightComposerAgent"                            ║
║     step_type=AGENT_CALL                                         ║
║     input_summary=artifact 数量 + 类型列表                        ║
║     output_summary=executive_summary 前50字                      ║
║     model_name=LLM 模型名（或"template_fallback"）                ║
║     artifact_ids=[report_artifact.artifact_id]                   ║
╚══════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger
from pydantic import BaseModel, Field

from backend.schemas.artifact import (
    ArtifactRef, ArtifactType,
    make_mock_customer_artifact, make_mock_forecast_artifact,
    make_mock_sentiment_artifact, make_mock_fraud_artifact,
)
from backend.services.report_rendering_service import (
    ReportRenderRequest, report_rendering_service,
)
from backend.core.error_handler import execute_with_retry, error_classifier


# ── 输入/输出 schema ──────────────────────────────────────────────

class InsightComposerInput(BaseModel):
    run_id:         Optional[str] = None
    thread_id:      Optional[str] = None
    artifact_refs:  List[ArtifactRef] = Field(default_factory=list)
    use_mock:       bool = False    # True 时使用 mock artifact，无需真实 service 完成


class InsightComposerOutput(BaseModel):
    run_id:            Optional[str]
    data_ready:        bool
    partial:           bool = False

    executive_summary: str = ""
    risk_highlights:   str = ""
    action_plan:       str = ""

    report_artifact:   Optional[ArtifactRef] = None
    model_used:        str = "template_fallback"
    composed_at:       datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error_message:     Optional[str] = None


# ── LLM Prompt ────────────────────────────────────────────────────

_COMPOSE_SYSTEM_PROMPT = """你是一个专业的经营分析顾问。根据提供的多维度分析摘要，生成结构化的经营洞察报告。

你必须严格按以下格式输出，三个区块用标记分隔：

[SUMMARY]
管理层摘要，200-300字，概述核心发现和整体趋势

[RISKS]
风险提示，100-200字，列出当前需要关注的风险点

[ACTIONS]
行动建议，3-5条具体可执行的建议，每条一行

要求：
- 语言简洁专业，使用中文
- 摘要要有全局观，提炼跨维度关联
- 风险只列真正需要关注的，不要无中生有
- 建议每条要具体、可执行，不要空泛
- 如果某维度数据缺失，在摘要中说明，不要编造
"""


# ── 分段格式解析 ──────────────────────────────────────────────────

def _parse_sections(raw: str) -> Optional[Dict[str, str]]:
    """
    解析 LLM 返回的 [SUMMARY]/[RISKS]/[ACTIONS] 分段格式。
    比 JSON 更可靠，不受换行符影响。
    """
    import re
    sections: Dict[str, str] = {}

    # 提取三个区块
    markers = [
        ("executive_summary", r"\[SUMMARY\]"),
        ("risk_highlights",   r"\[RISKS\]"),
        ("action_plan",       r"\[ACTIONS\]"),
    ]

    for i, (key, pattern) in enumerate(markers):
        match = re.search(pattern, raw, re.IGNORECASE)
        if match is None:
            continue
        start = match.end()
        # 找下一个标记或末尾
        end = len(raw)
        for _, next_pattern in markers[i + 1:]:
            next_match = re.search(next_pattern, raw[start:], re.IGNORECASE)
            if next_match:
                end = start + next_match.start()
                break
        sections[key] = raw[start:end].strip()

    if not sections:
        return None
    return sections


# ── Agent 实现 ────────────────────────────────────────────────────

class InsightComposerAgent:
    """
    读取多个 artifact refs，生成经营摘要。
    先支持 mock 模式快速验证输出 schema，再接真实 service artifact。

    路由策略:
      1. acompose() — 异步 LLM 生成（优先）
      2. compose()  — 同步模板拼接（fallback / 向后兼容）
    """

    def __init__(self):
        self._llm = None

    def compose(self, inp: InsightComposerInput) -> InsightComposerOutput:
        # 1. 准备 artifact 上下文
        if inp.use_mock or not inp.artifact_refs:
            refs = self._build_mock_refs(inp.run_id)
            logger.info("[InsightComposer] 使用 mock artifact 跑通最小闭环")
        else:
            refs = inp.artifact_refs

        if not refs:
            return InsightComposerOutput(
                run_id=inp.run_id,
                data_ready=False,
                error_message="无可用 artifact",
            )

        # 2. 从 artifact summaries 组装上下文
        ctx = self._build_context(refs)

        # 3. 生成三类输出
        exec_summary  = self._gen_executive_summary(ctx)
        risk_highlights = self._gen_risk_highlights(ctx)
        action_plan   = self._gen_action_plan(ctx)

        # 4. 渲染报告
        render_req = ReportRenderRequest(
            run_id=inp.run_id,
            report_type="business_overview",
            executive_summary=exec_summary,
            risk_highlights=risk_highlights,
            action_plan=action_plan,
            customer_summary=ctx.get("customer_insight"),
            forecast_summary=ctx.get("forecast"),
            sentiment_summary=ctx.get("sentiment"),
            fraud_summary=ctx.get("fraud_score"),
            inventory_summary=ctx.get("inventory"),
            association_summary=ctx.get("association"),
            generated_by="InsightComposerAgent",
        )
        render_result = report_rendering_service.render(render_req)

        output = InsightComposerOutput(
            run_id=inp.run_id,
            data_ready=True,
            partial=render_result.partial,
            executive_summary=exec_summary,
            risk_highlights=risk_highlights,
            action_plan=action_plan,
            report_artifact=render_result.artifact,
            model_used="template_fallback",
        )

        logger.info(
            f"[InsightComposer] run_id={inp.run_id} "
            f"artifacts={len(refs)} partial={output.partial} "
            f"summary_len={len(exec_summary)}"
        )
        return output

    # ── 上下文构建 ────────────────────────────────────────────────

    @staticmethod
    def _build_context(refs: List[ArtifactRef]) -> Dict[str, str]:
        """将 artifact refs 按类型索引 summary"""
        ctx: Dict[str, str] = {}
        for ref in refs:
            atype = ref.artifact_type if isinstance(ref.artifact_type, str) else ref.artifact_type.value
            ctx[atype] = ref.summary
        return ctx

    @staticmethod
    def _build_mock_refs(run_id: Optional[str]) -> List[ArtifactRef]:
        rid = None
        if run_id:
            try:
                rid = uuid.UUID(run_id)
            except ValueError:
                rid = uuid.uuid4()
        return [
            make_mock_customer_artifact(rid),
            make_mock_forecast_artifact(rid),
            make_mock_sentiment_artifact(rid),
            make_mock_fraud_artifact(rid),
        ]

    @staticmethod
    def _truncate(text: str, limit: int = 88) -> str:
        compact = " ".join((text or "").split())
        if len(compact) <= limit:
            return compact
        return compact[:limit - 3] + "..."

    # ── 模板生成（LLM 未接通时的 fallback）────────────────────────

    @staticmethod
    def _gen_executive_summary(ctx: Dict[str, str]) -> str:
        if not ctx:
            return "（暂无足够数据生成摘要）"

        labels = {
            "customer_insight": "客户洞察",
            "forecast": "销售预测",
            "sentiment": "舆情分析",
            "fraud_score": "欺诈风控",
            "inventory": "库存优化",
            "association": "关联分析",
        }
        lines = [
            "本次经营总览已整合多维分析结果，可直接用于管理层汇报与答辩展示。"
        ]
        for key in ("customer_insight", "forecast", "inventory", "fraud_score", "sentiment", "association"):
            if ctx.get(key):
                lines.append(f"{labels[key]}：{InsightComposerAgent._truncate(ctx[key])}")

        missing = [labels[key] for key in labels if not ctx.get(key)]
        if missing:
            lines.append(f"当前暂缺 {', '.join(missing)} 维度，建议在正式汇报前补充对应分析。")

        return "\n\n".join(lines[:5])

    @staticmethod
    def _gen_risk_highlights(ctx: Dict[str, str]) -> str:
        risks = []
        if ctx.get("customer_insight"):
            risks.append(f"- 客户留存：{InsightComposerAgent._truncate(ctx['customer_insight'])}")
        if ctx.get("fraud_score"):
            risks.append(f"- 欺诈风控：{InsightComposerAgent._truncate(ctx['fraud_score'])}")
        if ctx.get("sentiment"):
            risks.append(f"- 舆情风险：{InsightComposerAgent._truncate(ctx['sentiment'])}")
        if ctx.get("inventory"):
            risks.append(f"- 库存履约：{InsightComposerAgent._truncate(ctx['inventory'])}")
        if not risks:
            return "当前未检测到高优先级风险。"
        return "\n".join(risks[:4])

    @staticmethod
    def _gen_action_plan(ctx: Dict[str, str]) -> str:
        plans = []
        if ctx.get("customer_insight"):
            plans.append("复核高价值与高流失客群，安排分层运营和挽回动作。")
        if ctx.get("forecast"):
            plans.append("根据销售预测结果更新未来一周备货、排班和预算节奏。")
        if ctx.get("fraud_score"):
            plans.append("抽查高风险交易与规则命中样本，确保审核链路可回放。")
        if ctx.get("sentiment"):
            plans.append("跟进负面舆情主题与高频投诉点，准备统一回应口径。")
        if ctx.get("inventory"):
            plans.append("优先处理库存预警 SKU，校准安全库存阈值与补货计划。")
        if ctx.get("association"):
            plans.append("将高置信关联规则同步给营销侧，验证组合推荐转化。")
        if not plans:
            plans = [
                "确认本期分析使用的数据范围和生成时间。",
                "复核报告中的关键指标与截图口径。",
                "同步重点风险与优先动作给相关负责人。",
            ]
        return "\n".join(f"{idx}. {text}" for idx, text in enumerate(plans[:5], start=1))


    # ── LLM 异步合成 ─────────────────────────────────────────────

    def _get_llm(self):
        """延迟初始化 LLM 客户端"""
        if self._llm is None:
            try:
                from langchain_openai import ChatOpenAI
                from backend.config import settings
                extra_kw = {}
                if "qwen" in settings.LLM_MODEL_NAME.lower():
                    extra_kw["model_kwargs"] = {"extra_body": {"enable_thinking": True}}
                self._llm = ChatOpenAI(
                    api_key=settings.LLM_API_KEY,
                    base_url=settings.LLM_BASE_URL,
                    model=settings.LLM_MODEL_NAME,
                    temperature=0.3,
                    max_tokens=4000,
                    timeout=90,
                    **extra_kw,
                )
            except Exception as e:
                logger.warning(f"[InsightComposer] LLM 初始化失败: {e}")
        return self._llm

    async def acompose(self, inp: InsightComposerInput) -> InsightComposerOutput:
        """
        异步合成：优先用 LLM 生成高质量摘要，失败降级到模板。

        流程:
          1. 准备 artifact 上下文
          2. 尝试 LLM 生成三类输出
          3. 输出验证 (字段非空 + 长度)
          4. 验证失败或 LLM 不可用 → 模板 fallback
          5. 渲染报告
        """
        # 1. 准备 artifact 上下文
        if inp.use_mock or not inp.artifact_refs:
            refs = self._build_mock_refs(inp.run_id)
            logger.info("[InsightComposer] 使用 mock artifact")
        else:
            refs = inp.artifact_refs

        if not refs:
            return InsightComposerOutput(
                run_id=inp.run_id,
                data_ready=False,
                error_message="无可用 artifact",
            )

        ctx = self._build_context(refs)
        partial = len(ctx) < 3  # 少于 3 个维度视为 partial

        # 2. 尝试 LLM 生成
        exec_summary = ""
        risk_highlights = ""
        action_plan = ""
        model_used = "template_fallback"

        llm = self._get_llm()
        if llm is not None:
            try:
                llm_output = await self._llm_compose(ctx)
                if llm_output is not None:
                    exec_summary = llm_output.get("executive_summary", "")
                    risk_highlights = llm_output.get("risk_highlights", "")
                    action_plan = llm_output.get("action_plan", "")
                    model_used = "qwen3.5-plus-2026-02-15"
            except Exception as e:
                logger.warning(f"[InsightComposer] LLM 合成失败，降级到模板: {e}")

        # 3. 输出验证 + 降级
        if not self._validate_output(exec_summary, risk_highlights, action_plan):
            logger.info("[InsightComposer] LLM 输出未通过验证，使用模板 fallback")
            exec_summary = self._gen_executive_summary(ctx)
            risk_highlights = self._gen_risk_highlights(ctx)
            action_plan = self._gen_action_plan(ctx)
            model_used = "template_fallback"

        # 4. 渲染报告
        render_req = ReportRenderRequest(
            run_id=inp.run_id,
            report_type="business_overview",
            executive_summary=exec_summary,
            risk_highlights=risk_highlights,
            action_plan=action_plan,
            customer_summary=ctx.get("customer_insight"),
            forecast_summary=ctx.get("forecast"),
            sentiment_summary=ctx.get("sentiment"),
            fraud_summary=ctx.get("fraud_score"),
            inventory_summary=ctx.get("inventory"),
            association_summary=ctx.get("association"),
            generated_by=f"InsightComposerAgent/{model_used}",
        )
        render_result = report_rendering_service.render(render_req)

        output = InsightComposerOutput(
            run_id=inp.run_id,
            data_ready=True,
            partial=partial or render_result.partial,
            executive_summary=exec_summary,
            risk_highlights=risk_highlights,
            action_plan=action_plan,
            report_artifact=render_result.artifact,
            model_used=model_used,
        )

        logger.info(
            f"[InsightComposer] run_id={inp.run_id} model={model_used} "
            f"artifacts={len(refs)} partial={output.partial} "
            f"summary_len={len(exec_summary)}"
        )
        return output

    async def _llm_compose(self, ctx: Dict[str, str]) -> Optional[Dict[str, str]]:
        """调用 LLM 生成三类输出"""
        from langchain_core.messages import SystemMessage, HumanMessage

        llm = self._get_llm()
        if llm is None:
            return None

        # 构建用户消息：列出各维度摘要
        parts = []
        dim_names = {
            "customer_insight": "客户洞察",
            "forecast": "销售预测",
            "sentiment": "舆情分析",
            "fraud_score": "风控评估",
            "inventory": "库存状况",
            "association": "关联推荐",
            "data_quality": "数据质量",
        }
        for key, summary in ctx.items():
            label = dim_names.get(key, key)
            parts.append(f"【{label}】\n{summary}")

        if not parts:
            return None

        user_msg = "以下是本次经营分析各维度的摘要，请生成洞察报告：\n\n" + "\n\n".join(parts)

        messages = [
            SystemMessage(content=_COMPOSE_SYSTEM_PROMPT),
            HumanMessage(content=user_msg),
        ]

        import asyncio

        async def _call_llm():
            return await llm.ainvoke(messages)

        async with asyncio.timeout(60):
            response = await execute_with_retry(
                _call_llm,
                classifier=error_classifier,
            )

        # 解析分段格式 [SUMMARY] / [RISKS] / [ACTIONS]
        raw = response.content.strip()
        parsed = _parse_sections(raw)
        if parsed is None:
            logger.warning(f"[InsightComposer] LLM 输出解析失败: {raw[:300]}")
            return None

        # 记录 token 使用
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            usage = response.usage_metadata
            logger.info(f"[InsightComposer] LLM tokens={usage.get('total_tokens', '?')}")

        return parsed

    @staticmethod
    def _validate_output(
        exec_summary: str, risk_highlights: str, action_plan: str
    ) -> bool:
        """输出验证：三个字段必须非空且长度合理"""
        if not exec_summary or len(exec_summary) < 20:
            return False
        if not risk_highlights or len(risk_highlights) < 10:
            return False
        if not action_plan or len(action_plan) < 10:
            return False
        return True


# ── 单例 ──────────────────────────────────────────────────────────
insight_composer_agent = InsightComposerAgent()
