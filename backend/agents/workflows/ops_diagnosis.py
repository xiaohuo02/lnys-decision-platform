# -*- coding: utf-8 -*-
"""backend/agents/workflows/ops_diagnosis.py

Workflow D — OpsCopilot 运维诊断

流程：
  input_guard（输入安全检查）
      → ops_respond（意图分类 + 数据查询 + LLM 增强回答）
      → END

支持 PostgreSQL checkpoint 多轮对话，SSE 进度推送。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict

from loguru import logger

try:
    from langgraph.graph import StateGraph, START, END
    _LANGGRAPH_OK = True
except ImportError:
    _LANGGRAPH_OK = False
    StateGraph = None  # type: ignore
    START = "__start__"
    END   = "__end__"

from backend.agents.ops_copilot_agent import ops_copilot_agent
from backend.schemas.ops_copilot import OpsCopilotInput
from backend.core.progress_channel import progress_manager
from backend.governance.guardrails.input_guard import input_guard


# ── Workflow State ─────────────────────────────────────────────────

class OpsDiagnosisState(TypedDict, total=False):
    run_id:        str
    thread_id:     str
    workflow_name: str
    status:        str
    error:         Optional[str]

    # 输入
    question:      str

    # 输出
    intent:        Optional[str]
    answer:        Optional[str]
    confidence:    Optional[float]
    sources:       List[str]
    suggested_actions: List[str]
    fallback_used: bool

    node_timings:  Dict[str, float]


# ── 节点 ────────────────────────────────────────────────────────────

async def _node_ops_respond(state: OpsDiagnosisState) -> dict:
    """OpsCopilot 回答节点：意图分类 + 数据查询 + LLM 增强"""
    t0 = datetime.now(timezone.utc).timestamp()
    logger.info(
        f"[OpsDiagnosis] respond run_id={state.get('run_id')} "
        f"q_len={len(state.get('question', ''))}"
    )
    try:
        inp = OpsCopilotInput(
            question=state.get("question", ""),
            thread_id=state.get("thread_id"),
        )
        # 无 DB 时使用 aanswer (LLM 增强) ，有 DB 时也用 aanswer
        output = await ops_copilot_agent.aanswer(inp, db=None)
        timings = dict(state.get("node_timings") or {})
        timings["ops_respond"] = round(datetime.now(timezone.utc).timestamp() - t0, 3)
        return {
            "intent":            output.intent,
            "answer":            output.answer,
            "confidence":        output.confidence,
            "sources":           output.sources,
            "suggested_actions": output.suggested_actions,
            "fallback_used":     output.fallback_used,
            "status":            "completed",
            "node_timings":      timings,
        }
    except Exception as e:
        logger.error(f"[OpsDiagnosis] respond error: {e}")
        timings = dict(state.get("node_timings") or {})
        timings["ops_respond"] = round(datetime.now(timezone.utc).timestamp() - t0, 3)
        return {
            "status": "failed",
            "error": str(e),
            "answer": "查询时遇到内部异常，请稍后重试。",
            "fallback_used": True,
            "node_timings": timings,
        }


# ── Graph ─────────────────────────────────────────────────────────

def build_ops_diagnosis_graph():
    if not _LANGGRAPH_OK:
        raise RuntimeError("langgraph 未安装")
    g = StateGraph(OpsDiagnosisState)
    g.add_node("ops_respond", _node_ops_respond)
    g.add_edge(START, "ops_respond")
    g.add_edge("ops_respond", END)
    return g


# ── 执行入口 ────────────────────────────────────────────────────────

async def run_ops_diagnosis(
    question:  str,
    thread_id: Optional[str] = None,
    run_id:    Optional[str] = None,
) -> Dict[str, Any]:
    from backend.agents.checkpoint import get_checkpointer
    _run_id    = run_id    or str(uuid.uuid4())
    _thread_id = thread_id or str(uuid.uuid4())

    # InputGuard 输入安全检查
    guard_result = input_guard.check(question)
    if not guard_result.passed:
        logger.warning(f"[OpsDiagnosis] input blocked: {guard_result.blocked_reason}")
        return {
            "run_id": _run_id, "thread_id": _thread_id,
            "status": "blocked",
            "answer": "您的输入包含不允许的内容，请重新提问。",
            "intent": "blocked", "confidence": 0.0,
        }
    safe_question = guard_result.sanitized_text or question

    init_state: OpsDiagnosisState = {
        "run_id":        _run_id,
        "thread_id":     _thread_id,
        "workflow_name": "ops_diagnosis",
        "status":        "running",
        "question":      safe_question,
        "sources":       [],
        "suggested_actions": [],
        "node_timings":  {},
    }

    # SSE 进度通道
    channel = progress_manager.create_channel(_run_id)
    await channel.emit("route_decided", {
        "workflow": "ops_diagnosis",
        "modules": ["ops_respond"],
    })

    try:
        await channel.emit("step_started", {"step_name": "ops_respond"})

        async with get_checkpointer() as checkpointer:
            graph    = build_ops_diagnosis_graph()
            compiled = graph.compile(checkpointer=checkpointer)
            result   = await compiled.ainvoke(
                init_state,
                config={"configurable": {"thread_id": _thread_id}},
            )

        await channel.emit("step_completed", {
            "step_name": "ops_respond",
            "intent": result.get("intent"),
        })

        if result.get("status") == "completed":
            await channel.emit("final", {
                "status": "completed",
                "answer": (result.get("answer") or "")[:200],
                "intent": result.get("intent"),
            })
        else:
            await channel.emit("error", {
                "status": result.get("status", "failed"),
                "error": result.get("error", "unknown"),
            })
    except Exception as e:
        logger.error(f"[OpsDiagnosis] workflow error: {e}")
        await channel.emit("error", {"error": "运维诊断异常"})
        result = {"status": "failed", "error": str(e), "run_id": _run_id}
    finally:
        await progress_manager.remove_channel(_run_id)

    logger.info(
        f"[OpsDiagnosis] done run_id={_run_id} "
        f"intent={result.get('intent')} status={result.get('status')}"
    )
    return result
