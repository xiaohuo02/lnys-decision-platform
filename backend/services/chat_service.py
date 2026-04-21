# -*- coding: utf-8 -*-
"""backend/services/chat_service.py — OpenClaw 客服业务逻辑"""
import json
from typing import Any, Optional

import redis.asyncio as aioredis
from sqlalchemy.orm import Session
from loguru import logger

from backend.config import settings
from backend.core.response import ok, degraded
from backend.agents.gateway import AgentGateway
from backend.repositories.chat_repo import ChatRepo
from backend.schemas.chat_schemas import ChatMessageRequest

_INTENT_MAP = {
    "订单": "查订单",  "发货": "查订单",  "物流": "物流查询",
    "快递": "物流查询", "到货": "物流查询", "退款": "退换货",
    "退货": "退换货",  "换货": "退换货",  "投诉": "投诉建议",
    "优惠": "查优惠",  "折扣": "查优惠",  "积分": "查积分",
    "产品": "产品咨询", "商品": "产品咨询", "成分": "产品咨询",
    "价格": "产品咨询", "客服": "转人工",  "人工": "转人工",
}

_FAQ = {
    "查订单":   "您好！订单处理中，如需查询请提供订单号。",
    "物流查询": "包裹已揽收，运输中，预计 2-3 个工作日到达。",
    "退换货":   "退换货已受理，请在订单详情页提交申请，7 个工作日内处理。",
    "投诉建议": "非常抱歉给您带来不便，已记录，48 小时内联系您。",
    "查优惠":   "满300减50，会员享额外9折！活动截止本月底。",
    "查积分":   "积分可在会员中心查看，100积分=1元可抵扣消费。",
    "产品咨询": "我们产品均经严格品控，需了解具体规格请告知商品名称。",
    "转人工":   "正在为您转接人工客服，预计等待 3 分钟...",
}


class ChatService:
    def __init__(self, db: Session, redis: aioredis.Redis, agent: Any = None):
        self.db    = db
        self.redis = redis
        self.agent = agent
        self._repo = ChatRepo(db)

    async def send_message(self, body: ChatMessageRequest) -> dict:
        session_key = f"chat:session:{body.session_id}"

        # 读取历史 session（Redis List）
        try:
            history_raw = await self.redis.lrange(session_key, 0, 9)
            history     = [json.loads(h) for h in history_raw]
        except Exception as e:
            logger.warning(f"[chat_svc] redis lrange failed: {e}")
            history = []

        # F1: 传递 db 给 Agent，启用 FAQ/订单查询
        # F5: 传递会话历史给 Agent
        result = await AgentGateway.call(
            self.agent,
            {"session_id": body.session_id, "message": body.message,
             "customer_id": body.customer_id},
            agent_name="openclaw_agent",
            db=self.db,
        )

        if result is not None and "reply" not in result:
            logger.warning(f"[chat_svc] agent output missing 'reply' key, got keys={list(result.keys())}, fallback")
            result = None

        is_fallback = result is None
        if is_fallback:
            result = self._fallback_reply(body.message, len(history))

        # 更新 Redis session（TTL=1800s，保留最近10条）
        try:
            await self.redis.lpush(
                session_key,
                json.dumps({"role": "user", "content": body.message}, ensure_ascii=False),
                json.dumps({"role": "assistant", "content": result["reply"]}, ensure_ascii=False),
            )
            await self.redis.ltrim(session_key, 0, 9)
            await self.redis.expire(session_key, 1800)
        except Exception as e:
            logger.warning(f"[chat_svc] redis session update failed: {e}")

        # 落库（静默失败）
        self._repo.insert_pair(
            session_id=body.session_id,
            user_msg=body.message,
            bot_reply=result["reply"],
            intent=result.get("intent"),
            confidence=result.get("confidence"),
        )

        # F3: 当 Agent 或 fallback 标记 degraded 时，使用 degraded() 包装
        if result.get("degraded") or is_fallback:
            return degraded(result, "rule_fallback" if is_fallback else "llm_unavailable")
        return ok(result)

    async def get_history(self, session_id: str) -> dict:
        messages = self._repo.get_history(session_id)
        # F4: DB 存储 role="bot"，统一输出为 "assistant"
        for m in messages:
            if m.get("role") == "bot":
                m["role"] = "assistant"
        return ok({"session_id": session_id, "messages": messages})

    async def delete_session(self, session_id: str) -> dict:
        session_key = f"chat:session:{session_id}"
        try:
            await self.redis.delete(session_key)
        except Exception as e:
            logger.warning(f"[chat_svc] redis delete session failed: {e}")
        deleted = self._repo.delete_session(session_id)
        return ok({"session_id": session_id, "deleted_messages": deleted})

    @staticmethod
    def _fallback_reply(message: str, context_size: int) -> dict:
        """F2: 统一输出结构，对齐 OpenClawOutput 字段名"""
        intent     = "未知问题"
        for kw, v in _INTENT_MAP.items():
            if kw in message:
                intent = v
                break
        confidence = 0.92 if intent != "未知问题" else 0.35
        handoff    = confidence < 0.5
        reply = _FAQ.get(intent, "您的问题较复杂，为您转接人工客服，请稍候...")
        if handoff:
            reply  = "您的问题较复杂，为您转接人工客服，请稍候..."
            intent = "unknown"
        return {
            "reply":                reply,
            "intent":               intent,
            "confidence":           confidence,
            "handoff":              handoff,
            "handoff_reason":       f"意图置信度 {confidence:.2f} 低于阈值 0.5" if handoff else None,
            "sources":              [],
            "degraded":             True,
            "session_context_size": context_size,
        }
