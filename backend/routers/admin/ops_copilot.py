# -*- coding: utf-8 -*-
"""backend/routers/admin/ops_copilot.py

管理后台：OpsCopilot 运维助手 API
POST /admin/ops-copilot/ask  → 自然语言问答
"""
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from loguru import logger

from backend.database import get_db
from backend.core.response import ok
from backend.middleware.auth import admin_user, CurrentUser
from backend.agents.ops_copilot_agent import ops_copilot_agent, OpsCopilotInput

router = APIRouter(tags=["admin-ops-copilot"])


class CopilotAskBody(BaseModel):
    question: str
    run_id:   Optional[str] = None


@router.post("/ops-copilot/ask")
async def admin_ops_copilot_ask(body: CopilotAskBody, user: CurrentUser = Depends(admin_user), db: Session = Depends(get_db)):
    """运维 Copilot 自然语言查询接口（LLM 增强）"""
    try:
        inp = OpsCopilotInput(question=body.question)
        result = await ops_copilot_agent.aanswer(inp, db=db)
        return ok({
            "question":          body.question,
            "answer":            result.answer,
            "intent":            result.intent,
            "confidence":        result.confidence,
            "sources":           result.sources,
            "suggested_actions": result.suggested_actions,
            "structured_data":   getattr(result, "structured_data", None),
            "related_runs":      getattr(result, "related_runs", []),
            "trace_id":          body.run_id,
            "fallback_used":     result.fallback_used,
            "fallback":          result.fallback_used,
            "error":             result.error,
        })
    except Exception as e:
        logger.error(f"[ops_copilot] ask failed: {e}")
        return ok({
            "question":      body.question,
            "answer":        "运维助手暂时不可用，请稍后重试",
            "intent":        "error",
            "confidence":    0.0,
            "sources":       [],
            "suggested_actions": [],
            "structured_data":   None,
            "related_runs":      [],
            "trace_id":      body.run_id,
            "fallback_used": True,
            "fallback":      True,
            "error":         None,
        })
