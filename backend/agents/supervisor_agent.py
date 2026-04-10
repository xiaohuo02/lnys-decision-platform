# -*- coding: utf-8 -*-
"""backend/agents/supervisor_agent.py

SupervisorAgent — 请求路由与 Workflow 调度 Agent

╔══════════════════════════════════════════════════════════════════╗
║  Agent 契约 (必须在实现前确认)                                     ║
╠══════════════════════════════════════════════════════════════════╣
║  1. 输入                                                          ║
║     SupervisorInput:                                             ║
║       request_text: str  自然语言请求                             ║
║       request_type: Optional[str]  外部入参可显式指定路由          ║
║       run_id / thread_id                                         ║
║                                                                  ║
║  2. 允许调用的 service / tool                                     ║
║     - 关键词规则匹配（本地）                                       ║
║     - LLM 意图分类（当规则无法确定时）                             ║
║     - 不允许直接调用任何 service 或底层 ML 模型                    ║
║                                                                  ║
║  3. 输出 schema                                                   ║
║     SupervisorOutput:                                            ║
║       route: WorkflowRoute  枚举：business_overview /            ║
║              risk_review / openclaw / ops_copilot / unknown      ║
║       confidence: float  路由置信度 0~1                           ║
║       reason: str  路由原因说明                                   ║
║       route_plan: dict  传给下游 workflow 的参数                  ║
║                                                                  ║
║  4. 不能做的事                                                    ║
║     - 直接运行底层业务模型                                         ║
║     - 修改数据库                                                  ║
║     - 输出最终业务结论（只路由，不分析）                           ║
║                                                                  ║
║  5. 失败降级                                                      ║
║     - 规则与 LLM 均无法确定 → 路由到 business_overview（最安全）  ║
║     - LLM 不可用 → 纯规则路由                                     ║
║                                                                  ║
║  6. 是否进入 HITL                                                 ║
║     不需要（路由层不做业务判断）                                   ║
║                                                                  ║
║  7. 依赖的 artifact                                               ║
║     无（路由层不依赖历史 artifact）                                ║
║                                                                  ║
║  8. 写入 trace 的关键字段                                         ║
║     agent_name="SupervisorAgent"                                 ║
║     step_type=AGENT_CALL                                         ║
║     input_summary=request_text[:100]                             ║
║     output_summary=route + confidence                            ║
╚══════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
from enum import Enum
from typing import Any, Dict, List, Optional

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from backend.core.error_handler import execute_with_retry, error_classifier


# ── 路由枚举 ──────────────────────────────────────────────────────

class WorkflowRoute(str, Enum):
    BUSINESS_OVERVIEW = "business_overview"   # 经营总览分析
    RISK_REVIEW       = "risk_review"         # 高风险交易审核
    OPENCLAW          = "openclaw"            # OpenClaw 客服会话
    OPS_COPILOT       = "ops_copilot"         # 运维 Copilot
    UNKNOWN           = "unknown"             # 无法路由，降级到 business_overview


# ── 规则关键词表（不依赖 LLM 的快速路由）─────────────────────────

_ROUTE_RULES: List[tuple[WorkflowRoute, List[str]]] = [
    (WorkflowRoute.RISK_REVIEW, [
        "风险", "欺诈", "冻结", "风控", "可疑交易", "高风险",
        "退款", "fraud", "risk", "suspicious",
    ]),
    (WorkflowRoute.OPS_COPILOT, [
        "运维", "系统状态", "告警", "日志", "监控", "部署",
        "服务健康", "健康状态", "指标", "trace", "ops",
        "诊断", "服务状态",
    ]),
    (WorkflowRoute.OPENCLAW, [
        "订单", "快递", "发货", "退货", "换货", "投诉",
        "查订单", "物流", "客服", "帮我查",
        "openclaw", "咨询", "客户服务",
    ]),
    (WorkflowRoute.BUSINESS_OVERVIEW, [
        "经营", "分析", "报告", "总览", "预测", "客户",
        "销售", "舆情", "库存", "关联", "洞察", "摘要",
        "分析报告", "data", "overview", "insight",
    ]),
]


# ── 输入/输出 schema ──────────────────────────────────────────────

class SupervisorInput(BaseModel):
    request_text:  str
    request_type:  Optional[str] = None   # 显式指定路由，跳过规则推断
    run_id:        Optional[str] = None
    thread_id:     Optional[str] = None
    context:       Dict[str, Any] = Field(default_factory=dict)


class SupervisorOutput(BaseModel):
    run_id:      Optional[str]
    route:       WorkflowRoute
    confidence:  float        # 0.0 ~ 1.0
    reason:      str
    route_plan:  Dict[str, Any] = Field(default_factory=dict)
    used_llm:    bool = False

    model_config = ConfigDict(use_enum_values=True)


# ── LLM 意图分类 Prompt ──────────────────────────────────────────

_CLASSIFY_SYSTEM_PROMPT = """你是一个请求路由分类器。根据用户输入，判断应该路由到哪个工作流。

可选工作流:
- business_overview: 经营分析、数据报告、销售预测、客户分析、舆情分析、库存优化、关联推荐
- risk_review: 风险审核、欺诈检测、可疑交易、冻结账户
- openclaw: 客服咨询、订单查询、物流追踪、退换货、投诉
- ops_copilot: 系统运维、平台监控、日志查询、Trace 分析、部署状态

请只返回 JSON，格式:
{"route": "工作流名称", "confidence": 0.0到1.0, "reason": "判断原因"}
"""

_LLM_CONFIDENCE_THRESHOLD = 0.6  # 规则置信度低于此值时调用 LLM


# ── Agent 实现 ────────────────────────────────────────────────────

class SupervisorAgent:
    """
    v4.0 SupervisorAgent：先规则路由，置信度不足时调用 LLM 分类。

    路由策略优先级:
      1. 显式指定 request_type → 直接路由
      2. 规则关键词匹配 → 置信度 >= 0.6 直接返回
      3. 规则置信度 < 0.6 → 调用 LLM 分类
      4. LLM 失败 → 降级到规则结果或 business_overview
    """

    def __init__(self):
        self._llm = None  # 延迟初始化

    def _get_llm(self):
        """延迟初始化 LLM 客户端"""
        if self._llm is None:
            try:
                from langchain_openai import ChatOpenAI
                from backend.config import settings
                self._llm = ChatOpenAI(
                    api_key=settings.LLM_API_KEY,
                    base_url=settings.LLM_BASE_URL,
                    model=settings.LLM_MODEL_NAME,
                    temperature=0,
                    max_tokens=200,
                    timeout=30,
                )
                logger.info(
                    f"[SupervisorAgent] LLM 初始化: model={settings.LLM_MODEL_NAME} "
                    f"base_url={settings.LLM_BASE_URL}"
                )
            except Exception as e:
                logger.warning(f"[SupervisorAgent] LLM 初始化失败 (将使用纯规则路由): {e}")
                self._llm = None
        return self._llm

    def route(self, inp: SupervisorInput) -> SupervisorOutput:
        """同步路由 (仅规则，向后兼容)"""
        # 1. 显式指定路由
        if inp.request_type:
            try:
                explicit_route = WorkflowRoute(inp.request_type)
                logger.info(
                    f"[SupervisorAgent] 显式路由: {explicit_route} run_id={inp.run_id}"
                )
                return SupervisorOutput(
                    run_id=inp.run_id,
                    route=explicit_route,
                    confidence=1.0,
                    reason=f"显式指定 request_type={inp.request_type}",
                    route_plan={"workflow": explicit_route.value},
                )
            except ValueError:
                pass

        # 2. 规则关键词匹配
        text_lower = inp.request_text.lower()
        for route, keywords in _ROUTE_RULES:
            hits = [kw for kw in keywords if kw in text_lower]
            if hits:
                confidence = min(0.5 + len(hits) * 0.1, 0.95)
                logger.info(
                    f"[SupervisorAgent] 规则路由: {route} "
                    f"hits={hits} conf={confidence:.2f} run_id={inp.run_id}"
                )
                return SupervisorOutput(
                    run_id=inp.run_id,
                    route=route,
                    confidence=confidence,
                    reason=f"规则命中关键词: {', '.join(hits[:3])}",
                    route_plan=self._build_route_plan(route, inp),
                )

        # 3. 降级：无法确定时路由到 business_overview
        logger.warning(
            f"[SupervisorAgent] 无法路由，降级到 business_overview. "
            f"text='{inp.request_text[:50]}' run_id={inp.run_id}"
        )
        return SupervisorOutput(
            run_id=inp.run_id,
            route=WorkflowRoute.BUSINESS_OVERVIEW,
            confidence=0.3,
            reason="规则无法匹配，降级到经营总览",
            route_plan=self._build_route_plan(WorkflowRoute.BUSINESS_OVERVIEW, inp),
        )

    @staticmethod
    def _build_route_plan(
        route: WorkflowRoute, inp: SupervisorInput
    ) -> Dict[str, Any]:
        """构造传给下游 workflow 的参数包"""
        base = {
            "workflow":     route.value,
            "run_id":       inp.run_id,
            "thread_id":    inp.thread_id,
            "request_text": inp.request_text,
        }
        if route == WorkflowRoute.BUSINESS_OVERVIEW:
            base["analysis_module"] = "business_overview"
            base["use_mock"] = False
        elif route == WorkflowRoute.RISK_REVIEW:
            base["review_type"] = "fraud_hitl"
        elif route == WorkflowRoute.OPENCLAW:
            base["session_mode"] = "customer_service"
        return base


    # ── 异步路由 (规则 + LLM) ────────────────────────────────────

    async def aroute(self, inp: SupervisorInput) -> SupervisorOutput:
        """
        异步路由：规则优先，置信度不足时调用 LLM。

        流程:
          1. 显式指定 → 直接返回
          2. 规则匹配 → 置信度 > 0.6 → 直接返回（严格大于，避免单 hit 边界）
          3. 规则置信度 <= 0.6 → 调用 LLM 复查
          4. LLM 失败 → 降级到规则结果
        """
        # 先执行规则路由
        rule_result = self.route(inp)

        # 规则置信度足够，直接返回
        # 注意：使用严格大于，确保单关键词命中（conf=0.6，恰好等于阈值）
        # 也能触发 LLM 复查——避免对抗样本（如"分析风险投资"）被规则误路由
        if rule_result.confidence > _LLM_CONFIDENCE_THRESHOLD:
            return rule_result

        # 尝试 LLM 路由（设置独立超时，避免耗尽中间件 30s 限制）
        llm = self._get_llm()
        if llm is None:
            logger.info("[SupervisorAgent] LLM 不可用，使用规则结果")
            return rule_result

        import asyncio
        try:
            async with asyncio.timeout(15):
                llm_result = await self._llm_classify(inp)
                if llm_result is not None:
                    return llm_result
        except asyncio.TimeoutError:
            logger.warning("[SupervisorAgent] LLM 分类超时(15s)，快速降级到规则结果")
        except Exception as e:
            logger.warning(f"[SupervisorAgent] LLM 路由失败，降级到规则: {e}")

        return rule_result

    async def _llm_classify(self, inp: SupervisorInput) -> Optional[SupervisorOutput]:
        """调用 LLM 进行意图分类"""
        from langchain_core.messages import SystemMessage, HumanMessage

        llm = self._get_llm()
        if llm is None:
            return None

        messages = [
            SystemMessage(content=_CLASSIFY_SYSTEM_PROMPT),
            HumanMessage(content=inp.request_text[:2000]),  # 截断防止超长
        ]

        async def _call_llm():
            return await llm.ainvoke(messages)

        response = await execute_with_retry(
            _call_llm,
            classifier=error_classifier,
        )

        # 解析 LLM 响应
        raw = response.content.strip()
        # 尝试提取 JSON (可能被 markdown 代码块包裹)
        if "```" in raw:
            json_start = raw.find("{")
            json_end = raw.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                raw = raw[json_start:json_end]

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"[SupervisorAgent] LLM 返回无法解析: {raw[:200]}")
            return None

        route_str = parsed.get("route", "").lower().strip()
        confidence = float(parsed.get("confidence", 0.5))
        reason = parsed.get("reason", "LLM 分类")

        # 映射到 WorkflowRoute
        try:
            route = WorkflowRoute(route_str)
        except ValueError:
            logger.warning(f"[SupervisorAgent] LLM 返回未知路由: {route_str}")
            return None

        # 计算 token 使用
        token_info = ""
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            usage = response.usage_metadata
            token_info = f" tokens={usage.get('total_tokens', '?')}"

        logger.info(
            f"[SupervisorAgent] LLM 路由: {route} conf={confidence:.2f} "
            f"reason={reason}{token_info} run_id={inp.run_id}"
        )

        return SupervisorOutput(
            run_id=inp.run_id,
            route=route,
            confidence=confidence,
            reason=f"[LLM] {reason}",
            route_plan=self._build_route_plan(route, inp),
            used_llm=True,
        )


# ── 单例 ──────────────────────────────────────────────────────────
supervisor_agent = SupervisorAgent()
