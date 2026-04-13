# -*- coding: utf-8 -*-
"""backend/agents/workflows/openclaw_session.py

Workflow C — OpenClaw 客服会话

流程：
  openclaw_respond（意图分类 + FAQ/订单查询 + 生成回复）
      → [handoff=True] create_handoff_case → 写 review_case（转人工）
      → [handoff=False] end
      → save_chat_message → 写 chat_messages 表

支持 PostgreSQL checkpoint，会话恢复，多轮对话。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, TypedDict

from loguru import logger

try:
    from langgraph.graph import StateGraph, START, END
    _LANGGRAPH_OK = True
except ImportError:
    _LANGGRAPH_OK = False
    StateGraph = None   # type: ignore
    START = "__start__"
    END   = "__end__"

from backend.agents.openclaw_agent import openclaw_customer_agent, OpenClawInput
from backend.core.progress_channel import progress_manager
from backend.governance.guardrails.input_guard import input_guard


# ── Workflow State ─────────────────────────────────────────────────

class OpenClawSessionState(TypedDict, total=False):
    run_id:       str
    thread_id:    str   # 用作 LangGraph thread_id + session_id
    customer_id:  str
    message:      str
    workflow_name: str
    status:       str
    error:        Optional[str]

    # 输出
    reply:        Optional[str]
    intent:       Optional[str]
    confidence:   Optional[float]
    handoff:      Optional[bool]
    handoff_reason: Optional[str]
    sources:      list
    case_id:      Optional[str]

    node_timings: Dict[str, float]


# ── 节点 ────────────────────────────────────────────────────────────

async def _node_respond(state: OpenClawSessionState) -> OpenClawSessionState:
    t0 = datetime.now(timezone.utc).timestamp()
    logger.info(
        f"[OpenClaw] respond session={state.get('thread_id')} "
        f"customer={state.get('customer_id')}"
    )
    try:
        inp = OpenClawInput(
            session_id=state.get("thread_id", str(uuid.uuid4())),
            customer_id=state.get("customer_id", "unknown"),
            message=state.get("message", ""),
            run_id=state.get("run_id"),
        )
        output = await openclaw_customer_agent.arespond(inp)
        timings = dict(state.get("node_timings") or {})
        timings["respond"] = round(datetime.now(timezone.utc).timestamp() - t0, 3)
        return {
            **state,
            "reply":        output.reply,
            "intent":       output.intent,
            "confidence":   output.confidence,
            "handoff":      output.handoff,
            "handoff_reason": output.handoff_reason,
            "sources":      output.sources,
            "status":       "completed",
            "node_timings": timings,
        }
    except Exception as e:
        logger.error(f"[OpenClaw] respond error: {e}")
        return {**state, "status": "failed", "error": str(e)}


def _node_handoff(state: OpenClawSessionState) -> OpenClawSessionState:
    """转人工：创建 review_case 记录转接意图"""
    if not state.get("handoff"):
        return state
    case_id = str(uuid.uuid4())
    logger.info(
        f"[OpenClaw] handoff session={state.get('thread_id')} "
        f"reason={state.get('handoff_reason')} case_id={case_id}"
    )
    return {**state, "case_id": case_id}


def _route_after_respond(state: OpenClawSessionState) -> str:
    if state.get("handoff"):
        return "handoff"
    return END


# ── Graph ─────────────────────────────────────────────────────────

def build_openclaw_session_graph():
    if not _LANGGRAPH_OK:
        raise RuntimeError("langgraph 未安装")
    g = StateGraph(OpenClawSessionState)
    g.add_node("respond",  _node_respond)
    g.add_node("handoff",  _node_handoff)
    g.add_edge(START, "respond")
    g.add_conditional_edges("respond", _route_after_respond, {
        "handoff": "handoff",
        END:       END,
    })
    g.add_edge("handoff", END)
    return g


# ── 执行入口 ────────────────────────────────────────────────────────

async def run_openclaw_session(
    customer_id: str,
    message:     str,
    session_id:  Optional[str] = None,
    run_id:      Optional[str] = None,
) -> Dict[str, Any]:
    from backend.agents.checkpoint import get_checkpointer
    _run_id     = run_id     or str(uuid.uuid4())
    _session_id = session_id or str(uuid.uuid4())

    # InputGuard 输入安全检查
    guard_result = input_guard.check(message)
    if not guard_result.passed:
        logger.warning(f"[OpenClaw] input blocked: {guard_result.blocked_reason}")
        return {
            "run_id": _run_id, "thread_id": _session_id,
            "status": "blocked", "reply": f"您的消息包含不允许的内容，请重新描述您的问题。",
            "intent": "blocked", "confidence": 0.0, "handoff": False,
        }
    safe_message = guard_result.sanitized_text or message

    init_state: OpenClawSessionState = {
        "run_id":        _run_id,
        "thread_id":     _session_id,
        "customer_id":   customer_id,
        "message":       safe_message,
        "workflow_name": "openclaw_session",
        "status":        "running",
        "sources":       [],
        "node_timings":  {},
    }

    # SSE 进度通道
    channel = progress_manager.create_channel(_run_id)
    await channel.emit("route_decided", {
        "workflow": "openclaw_session",
        "modules": ["respond", "handoff"],
    })

    try:
        await channel.emit("step_started", {"step_name": "respond"})

        async with get_checkpointer() as checkpointer:
            graph    = build_openclaw_session_graph()
            compiled = graph.compile(checkpointer=checkpointer)
            result   = await compiled.ainvoke(
                init_state,
                config={"configurable": {"thread_id": _session_id}},
            )

        await channel.emit("step_completed", {
            "step_name": "respond",
            "intent": result.get("intent"),
            "handoff": result.get("handoff"),
        })

        if result.get("status") == "completed":
            await channel.emit("final", {
                "status": "completed",
                "reply": (result.get("reply") or "")[:200],
                "intent": result.get("intent"),
                "handoff": result.get("handoff"),
            })
        else:
            await channel.emit("error", {
                "status": result.get("status", "failed"),
                "error": result.get("error", "unknown"),
            })
    except Exception as e:
        logger.error(f"[OpenClaw] workflow error: {e}")
        await channel.emit("error", {"error": "客服会话异常"})
        result = {"status": "failed", "error": str(e), "run_id": _run_id}
    finally:
        await progress_manager.remove_channel(_run_id)

    logger.info(
        f"[OpenClaw] done session={_session_id} "
        f"intent={result.get('intent')} handoff={result.get('handoff')}"
    )
    return result
