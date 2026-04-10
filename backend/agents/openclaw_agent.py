# -*- coding: utf-8 -*-
"""backend/agents/openclaw_agent.py  v4.0

OpenClawCustomerAgent — 客服对话 Agent

╔══════════════════════════════════════════════════════════════════╗
║  Agent 契约 (必须在实现前确认)                                     ║
╠══════════════════════════════════════════════════════════════════╣
║  1. 输入                                                          ║
║     OpenClawInput:                                               ║
║       session_id: str   会话 ID（LangGraph thread_id）           ║
║       customer_id: str  客户 ID                                  ║
║       message: str      用户消息                                  ║
║       run_id: Optional[str]                                      ║
║                                                                  ║
║  2. 允许调用的 service / tool                                     ║
║     - faq_lookup()：从 faq_documents 表查询 FAQ                  ║
║     - order_query()：从 orders 表查询订单状态                     ║
║     - memory_read()：读取 memory_records（低风险）                ║
║     - memory_write()：写入 memory_records（附 risk_level 检查）   ║
║     - policy_check()：检查回复是否符合 Policy 规则                ║
║     - LLM（生成回复，受 Policy 约束）                             ║
║                                                                  ║
║  3. 输出 schema                                                   ║
║     OpenClawOutput:                                              ║
║       reply: str  对客户的回复                                    ║
║       intent: str  识别的意图                                     ║
║       confidence: float  置信度                                   ║
║       handoff: bool  是否转人工                                   ║
║       handoff_reason: Optional[str]                              ║
║       sources: List[str]  使用了哪些 FAQ/订单数据                  ║
║                                                                  ║
║  4. 不能做的事                                                    ║
║     - 直接修改订单状态、退款、冻结                                 ║
║     - 写入高风险 / pii 记忆                                       ║
║     - 暴露员工备注或内部风控阈值                                   ║
║     - 自动提交任何业务操作（必须转 HITL 或转人工）                 ║
║                                                                  ║
║  5. 失败降级                                                      ║
║     - FAQ 查不到 → 回复"暂时无法解答，正在为您转接客服"           ║
║     - LLM 不可用 → 使用 FAQ 正文直接回答，标记 degraded=True      ║
║     - 订单查不到 → 回复"请确认订单号后重试"                       ║
║                                                                  ║
║  6. 是否进入 HITL                                                 ║
║     confidence < 0.5 时触发 handoff=True，转人工审核              ║
║                                                                  ║
║  7. 依赖的 artifact                                               ║
║     无（实时工具调用，不依赖历史 artifact）                        ║
║                                                                  ║
║  8. 写入 trace 的关键字段                                         ║
║     agent_name="OpenClawCustomerAgent"                           ║
║     step_type=AGENT_CALL                                         ║
║     input_summary=intent + message[:80]                          ║
║     output_summary=reply[:80] + handoff                          ║
╚══════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import sqlalchemy
from loguru import logger
from pydantic import BaseModel, Field

from backend.config import settings


# ── Intent 规则（简单关键词分类）─────────────────────────────────

_INTENT_RULES: List[tuple[str, List[str]]] = [
    ("order_query",    ["订单", "快递", "物流", "发货", "到货", "查单", "订单号"]),
    ("return_refund",  ["退货", "退款", "换货", "申请退", "不想要"]),
    ("complaint",      ["投诉", "差评", "太差", "不满意", "骗人", "投诉你们"]),
    ("product_inquiry",["商品", "产品", "规格", "颜色", "尺寸", "有货吗"]),
    ("account",        ["账号", "密码", "登录", "注册", "修改信息"]),
    ("general_faq",    ["怎么", "如何", "可以", "能不能", "帮我"]),
]

_HANDOFF_THRESHOLD = 0.5


# ── 输入/输出 schema ──────────────────────────────────────────────

class OpenClawInput(BaseModel):
    session_id:  str
    customer_id: Optional[str] = None
    message:     str
    run_id:      Optional[str] = None


class OpenClawOutput(BaseModel):
    session_id:    str
    customer_id:   Optional[str] = None
    reply:         str
    intent:        str = "unknown"
    confidence:    float = 0.0
    handoff:       bool = False
    handoff_reason: Optional[str] = None
    sources:       List[str] = Field(default_factory=list)
    degraded:      bool = False
    responded_at:  datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── 工具函数 ──────────────────────────────────────────────────────

def _faq_lookup(db, query: str, limit: int = 3) -> List[Dict[str, Any]]:
    """在 faq_documents 表中模糊搜索 FAQ（SQL LIKE 降级方案）"""
    try:
        rows = db.execute(sqlalchemy.text(
            "SELECT doc_id, title, content FROM faq_documents "
            "WHERE is_active=1 AND (title LIKE :q OR content LIKE :q) "
            "LIMIT :limit"
        ), {"q": f"%{query[:30]}%", "limit": limit}).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception as e:
        logger.debug(f"[OpenClaw] faq_lookup error: {e}")
        return []


async def _avector_faq_search(query: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """异步向量检索 FAQ（推荐路径，直接 await kb.search）。

    应在 async 上下文（arespond / workflow 节点）中使用。
    """
    try:
        from backend.services.enterprise_kb_service import EnterpriseKBService
        kb = EnterpriseKBService.get_instance()
        results = await kb.search(query, top_k=top_k)
        if results:
            logger.info(
                f"[OpenClaw] avector search: {len(results)} hits, "
                f"best={results[0].get('similarity', 0):.3f}"
            )
        return results or []
    except Exception as e:
        logger.debug(f"[OpenClaw] avector_faq_search fallback: {e}")
        return []


def _vector_faq_search(query: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """同步向量检索 FAQ（仅供 sync respond 的 threadpool 路径使用，如 chat.py）。

    - 若调用时已处于 async 上下文（有 running loop），直接返回 []，
      调用方应预先 `await _avector_faq_search(...)` 把结果通过 `vector_hits`
      参数传给 respond()，彻底消除 sandwich（async-in-sync-in-async）。
    - 若调用时无 running loop（run_in_threadpool worker 场景），
      则创建独立 loop 执行 kb.search。kb.search 声明为 async 但内部全同步，
      此路径安全且可复用 SQL LIKE 降级链。
    """
    import asyncio

    try:
        asyncio.get_running_loop()
        # 已在 async 上下文 — 不做嵌套 run，由调用方改用 _avector_faq_search
        logger.debug(
            "[OpenClaw] _vector_faq_search called in async context — "
            "skip (use _avector_faq_search and pass vector_hits to respond)"
        )
        return []
    except RuntimeError:
        pass

    try:
        from backend.services.enterprise_kb_service import EnterpriseKBService
        kb = EnterpriseKBService.get_instance()
        results = asyncio.run(kb.search(query, top_k=top_k))
        if results:
            logger.info(
                f"[OpenClaw] vector search: {len(results)} hits, "
                f"best={results[0].get('similarity', 0):.3f}"
            )
        return results or []
    except Exception as e:
        logger.debug(f"[OpenClaw] vector_faq_search fallback: {e}")
        return []


def _order_query(db, customer_id: str, message: str) -> Optional[Dict[str, Any]]:
    """从 message 中提取订单号，查询订单状态"""
    # 简单提取：找形如 LY-xxx 或纯数字长串的订单号
    order_match = re.search(r"([A-Z]{2,}-\w{5,}|\d{8,})", message)
    if not order_match:
        return None
    order_id = order_match.group(1)
    try:
        row = db.execute(sqlalchemy.text(
            "SELECT order_id, total_amount, order_date, channel "
            "FROM orders WHERE order_id = :oid AND customer_id = :cid"
        ), {"oid": order_id, "cid": customer_id}).fetchone()
        return dict(row._mapping) if row else None
    except Exception as e:
        logger.debug(f"[OpenClaw] order_query error: {e}")
        return None


def _classify_intent(message: str) -> tuple[str, float]:
    """简单关键词意图分类，返回 (intent, confidence)"""
    text = message.lower()
    best_intent, best_hits = "general_faq", 0
    for intent, keywords in _INTENT_RULES:
        hits = sum(1 for kw in keywords if kw in text)
        if hits > best_hits:
            best_hits, best_intent = hits, intent
    confidence = min(0.5 + best_hits * 0.12, 0.95) if best_hits > 0 else 0.35
    return best_intent, confidence


# ── Agent 实现 ────────────────────────────────────────────────────

class OpenClawCustomerAgent:
    """
    v4.0 OpenClaw 客服 Agent。
    工具调用顺序：意图分类 → FAQ/订单查询 → 生成回复 → 置信度检查 → 转人工
    """

    def __init__(self, redis=None):
        self.redis = redis

    async def run(self, input_data: dict, *, db=None) -> dict:
        """兼容 AgentGateway.call() 的入口"""
        inp = OpenClawInput(**input_data)
        output = await self.arespond(inp, db=db)
        return output.model_dump()

    # ── 异步 LLM 回复 ──────────────────────────────────────────

    async def arespond(self, inp: OpenClawInput, db=None) -> OpenClawOutput:
        """异步回复：async 上下文下的推荐入口。

        设计：
          1. 预先 await 异步向量检索（避免 respond 内部嵌套 asyncio.run）
          2. 把同步 respond 放到线程池跑，防止同步 DB 操作阻塞主 event loop
          3. 失败降级 → 同步 respond 仍会走 SQL LIKE fallback
          4. 最后用 LLM 增强回复（async，失败则沿用 base_reply）
        """
        from fastapi.concurrency import run_in_threadpool

        # 1. 预先 async 检索（在主 loop 中 await，无 sandwich）
        vector_hits = await _avector_faq_search(inp.message)

        # 2. 同步 respond 含同步 DB 查询，移到线程池避免阻塞 event loop
        base_output = await run_in_threadpool(
            self.respond, inp, db, vector_hits,
        )

        # 3. LLM 优化回复
        llm_reply = await self._llm_reply(
            message=inp.message,
            intent=base_output.intent,
            base_reply=base_output.reply,
            sources=base_output.sources,
        )
        if llm_reply:
            base_output.reply = llm_reply
            base_output.degraded = False

        return base_output

    async def _llm_reply(
        self,
        message: str,
        intent: str,
        base_reply: str,
        sources: List[str],
    ) -> Optional[str]:
        """用 qwen3.5-plus 生成客服回复"""
        try:
            from langchain_openai import ChatOpenAI

            api_key  = os.getenv("LLM_API_KEY", "")
            base_url = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
            model    = os.getenv("LLM_MODEL_NAME", "qwen3.5-plus-2026-02-15")

            if not api_key:
                return None

            system_prompt = (
                "你是柠优生活平台的智能客服助手'小柠'。\n"
                "规则：\n"
                "- 回复简洁友好，使用中文，100字以内\n"
                "- 不能承诺退款、修改订单等操作\n"
                "- 不能透露内部信息、员工备注、风控阈值\n"
                "- 遇到退款/投诉等敏感话题，引导转人工客服\n"
                "- 基于提供的上下文信息回答，不要编造\n"
            )

            context_info = ""
            if sources:
                context_info = f"\n已查询到的信息来源: {', '.join(sources)}"
            if base_reply:
                context_info += f"\n参考回复内容: {base_reply[:200]}"

            user_prompt = (
                f"客户消息: {message}\n"
                f"识别意图: {intent}\n"
                f"{context_info}\n\n"
                f"请生成对客户的回复:"
            )

            llm = ChatOpenAI(
                api_key=api_key,
                base_url=base_url,
                model=model,
                max_tokens=300,
                temperature=0.5,
                timeout=15,
            )
            from langchain_core.messages import SystemMessage, HumanMessage
            resp = await llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ])
            content = resp.content.strip() if resp.content else ""

            if len(content) >= 5:
                logger.info(
                    f"[OpenClaw] LLM reply: {len(content)}c, model={model}"
                )
                return content
            return None
        except Exception as e:
            logger.warning(f"[OpenClaw] LLM reply failed (fallback): {e}")
            return None

    def respond(
        self,
        inp: OpenClawInput,
        db=None,
        vector_hits: Optional[List[Dict[str, Any]]] = None,
    ) -> OpenClawOutput:
        """同步回复入口。

        vector_hits: 可选的预检索向量结果（由 arespond 异步预取）；
          - 传入非 None 时跳过内部向量检索
          - 传入 None 时，尝试 sync `_vector_faq_search`（仅无 running loop 时有效，
            如 chat.py 的 run_in_threadpool 场景）
        """
        intent, confidence = _classify_intent(inp.message)
        sources: List[str] = []
        reply = ""
        degraded = False

        # 1. 订单查询
        if intent == "order_query" and db:
            order = _order_query(db, inp.customer_id, inp.message)
            if order:
                reply = (
                    f"您好！已为您查询到订单 {order['order_id']}，"
                    f"金额 ¥{order['total_amount']}，"
                    f"下单时间 {order['order_date']}，"
                    f"渠道：{order['channel']}。"
                    f"如需进一步帮助请告知。"
                )
                sources.append(f"order:{order['order_id']}")
                confidence = max(confidence, 0.85)
            else:
                reply = "您好，请提供完整的订单号，我来为您查询最新状态。"
                confidence = 0.6

        # 2. FAQ 查询 — 优先向量检索，降级 SQL LIKE
        if not reply:
            # 2a. 向量语义检索：优先使用调用方预检索结果
            vector_results = (
                vector_hits if vector_hits is not None
                else _vector_faq_search(inp.message)
            )
            if vector_results:
                best = vector_results[0]
                reply = f"您好！根据我们的常见问题解答：\n\n{best['content'][:300]}"
                sources.append(f"faq:{best['doc_id']}")
                sim = best.get('similarity', 0)
                confidence = max(confidence, min(0.6 + sim * 0.3, 0.92))
            # 2b. 降级：SQL LIKE 模糊匹配
            elif db:
                faqs = _faq_lookup(db, inp.message)
                if faqs:
                    best = faqs[0]
                    reply = f"您好！根据我们的常见问题解答：\n\n{best['content'][:300]}"
                    sources.append(f"faq:{best['doc_id']}")
                    confidence = max(confidence, 0.72)

        # 3. 无法解答 → fallback
        if not reply:
            if intent in ("return_refund", "complaint"):
                reply = "您好，退换货及投诉事宜需要人工协助，正在为您转接专属客服，请稍候。"
                confidence = 0.3   # 强制转人工
            else:
                reply = "您好，感谢您联系柠优客服！请问有什么可以帮您的？"
                degraded = True
                confidence = max(confidence, 0.4)

        # 4. 低置信度转人工
        handoff = confidence < _HANDOFF_THRESHOLD
        handoff_reason = (
            f"意图置信度 {confidence:.2f} 低于阈值 {_HANDOFF_THRESHOLD}" if handoff else None
        )

        logger.info(
            f"[OpenClaw] session={inp.session_id} customer={inp.customer_id} "
            f"intent={intent} conf={confidence:.2f} handoff={handoff}"
        )

        return OpenClawOutput(
            session_id=inp.session_id,
            customer_id=inp.customer_id,
            reply=reply,
            intent=intent,
            confidence=confidence,
            handoff=handoff,
            handoff_reason=handoff_reason,
            sources=sources,
            degraded=degraded,
        )


openclaw_customer_agent = OpenClawCustomerAgent()
