# -*- coding: utf-8 -*-
"""backend/routers/internal/smoke.py

内部冒烟测试路由（仅供调试与集成验证，不对外暴露）
- GET  /internal/smoke/health   → 基础健康检查
- POST /internal/smoke/workflow → 运行最小 LangGraph workflow，验证 checkpoint
"""
import uuid
from fastapi import APIRouter

router = APIRouter(tags=["internal-smoke"])


@router.get("/health")
async def internal_health():
    return {"status": "ok", "module": "internal-smoke"}


@router.post("/workflow")
async def smoke_workflow(thread_id: str | None = None):
    """
    运行最小 LangGraph workflow，验证 PostgreSQL checkpoint 是否正常。
    调用方式：POST /internal/smoke/workflow?thread_id=test-thread-1
    """
    _thread_id = thread_id or f"smoke-{uuid.uuid4().hex[:8]}"
    try:
        from backend.agents.base_workflow import run_minimal_workflow
        result = await run_minimal_workflow(thread_id=_thread_id)
        return {
            "status":    "ok",
            "thread_id": _thread_id,
            "run_id":    result.get("run_id"),
            "workflow_status": result.get("status"),
        }
    except Exception as e:
        from loguru import logger
        logger.error(f"[smoke] workflow failed: {e}")
        return {"status": "error", "thread_id": _thread_id, "error": type(e).__name__}
