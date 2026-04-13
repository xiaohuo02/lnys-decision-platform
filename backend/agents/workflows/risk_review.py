# -*- coding: utf-8 -*-
"""backend/agents/workflows/risk_review.py

Workflow B — 高风险交易审核

流程：
  FraudScoring（批量评分）
      → [高风险] RiskReviewAgent.prepare_review → 创建 review_case
      → interrupt()  ←── 等待人工审核
      → [human input] approve / edit / reject
      → 记录 action_ledger
      → 写 audit_log

LangGraph interrupt 机制：
  - 执行到 hitl_interrupt 节点时 graph.ainvoke 抛出 GraphInterrupt
  - workflow 状态被 PostgreSQL checkpoint 保存
  - 人工审核完成后，通过 admin/reviews/{case_id}/approve|edit|reject 操作
  - 再次调用 compiled.ainvoke(None, config={"configurable": {"thread_id": t}}) 恢复
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict

from loguru import logger

try:
    from langgraph.graph import StateGraph, START, END
    from langgraph.types import interrupt, Command
    _LANGGRAPH_OK = True
except ImportError:
    _LANGGRAPH_OK = False
    StateGraph = None  # type: ignore
    START = "__start__"
    END   = "__end__"

from backend.services.fraud_scoring_service import (
    fraud_scoring_service, FraudScoringRequest,
)
from backend.agents.risk_review_agent import risk_review_agent, RiskReviewInput
from backend.core.progress_channel import progress_manager
from backend.governance.guardrails.input_guard import input_guard


# ── Workflow State ─────────────────────────────────────────────────

class RiskReviewState(TypedDict, total=False):
    run_id:           str
    thread_id:        str
    request_id:       str
    workflow_name:    str
    status:           str
    error:            Optional[str]

    # 交易输入
    transaction_features: List[Dict[str, Any]]

    # FraudScoring 产物
    fraud_result:     Optional[Dict[str, Any]]
    high_risk_count:  int
    hitl_count:       int

    # HITL
    case_ids:         List[str]
    hitl_triggered:   bool

    # 审核摘要 (LLM 生成)
    review_summary:   Optional[str]

    # 人工决策（恢复后填入）
    human_decision:   Optional[str]   # approve / reject / edit
    decision_by:      Optional[str]

    node_timings:     Dict[str, float]


# ── 节点 ────────────────────────────────────────────────────────────

def _node_fraud_scoring(state: RiskReviewState) -> RiskReviewState:
    t0 = datetime.now(timezone.utc).timestamp()
    logger.info(f"[RiskReview] fraud_scoring run_id={state.get('run_id')}")
    try:
        features_list = state.get("transaction_features") or []
        if features_list:
            req = FraudScoringRequest(
                run_id=state.get("run_id"),
                batch=features_list,
            )
        else:
            req = FraudScoringRequest(run_id=state.get("run_id"), features={})

        result = fraud_scoring_service.score(req)
        timings = dict(state.get("node_timings") or {})
        timings["fraud_scoring"] = round(datetime.now(timezone.utc).timestamp() - t0, 3)
        return {
            **state,
            "fraud_result":    result.model_dump(),
            "high_risk_count": result.high_risk_count,
            "hitl_count":      result.hitl_count,
            "node_timings":    timings,
        }
    except Exception as e:
        logger.error(f"[RiskReview] fraud_scoring error: {e}")
        timings = dict(state.get("node_timings") or {})
        timings["fraud_scoring"] = round(datetime.now(timezone.utc).timestamp() - t0, 3)
        return {**state, "status": "failed", "error": str(e), "node_timings": timings}


async def _node_prepare_review(state: RiskReviewState) -> RiskReviewState:
    t0 = datetime.now(timezone.utc).timestamp()
    logger.info(f"[RiskReview] prepare_review run_id={state.get('run_id')}")
    try:
        inp = RiskReviewInput(
            run_id=state.get("run_id"),
            thread_id=state.get("thread_id"),
            fraud_result=state.get("fraud_result"),
        )
        output = await risk_review_agent.areview(inp)
        timings = dict(state.get("node_timings") or {})
        timings["prepare_review"] = round(datetime.now(timezone.utc).timestamp() - t0, 3)
        return {
            **state,
            "case_ids":       output.case_ids,
            "hitl_triggered": output.hitl_triggered,
            "review_summary": output.summary,
            "node_timings":   timings,
        }
    except Exception as e:
        logger.error(f"[RiskReview] prepare_review error: {e}")
        return {**state, "status": "failed", "error": str(e)}


def _node_hitl_interrupt(state: RiskReviewState) -> dict:
    """
    若存在高风险案例，触发 LangGraph interrupt 等待人工决策。
    interrupt() 暂停 graph 执行，状态由 PostgreSQL checkpoint 保存。
    人工审核后通过 Command(resume=decision) 恢复。
    """
    if not state.get("hitl_triggered"):
        logger.info(f"[RiskReview] no HITL needed run_id={state.get('run_id')}")
        return {"human_decision": "auto_pass"}

    case_ids = state.get("case_ids", [])
    logger.info(
        f"[RiskReview] interrupt triggered "
        f"cases={case_ids} run_id={state.get('run_id')}"
    )

    if _LANGGRAPH_OK:
        # interrupt() 暂停执行，Command(resume=...) 返回值将成为 human_input
        human_input = interrupt({
            "action":   "hitl_review_required",
            "case_ids": case_ids,
            "message":  f"请审核 {len(case_ids)} 笔高风险交易",
            "summary":  state.get("review_summary", ""),
        })
        # human_input 是审核人员的决策，如 {"decision": "approve", "by": "admin"}
        decision = "approve"
        decision_by = "system"
        if isinstance(human_input, dict):
            decision    = human_input.get("decision", "approve")
            decision_by = human_input.get("by", "unknown")
        elif isinstance(human_input, str):
            decision = human_input
        elif isinstance(human_input, bool):
            decision = "approve" if human_input else "reject"
        return {
            "human_decision": decision,
            "decision_by":    decision_by,
        }
    else:
        logger.warning("[RiskReview] LangGraph not available, skipping interrupt")
        return {"human_decision": "degraded_auto_pass"}


def _node_post_review(state: RiskReviewState) -> dict:
    """人工审核后执行：记录决策，更新状态"""
    decision = state.get("human_decision", "unknown")
    decision_by = state.get("decision_by", "system")
    case_ids = state.get("case_ids", [])

    logger.info(
        f"[RiskReview] post_review decision={decision} by={decision_by} "
        f"cases={len(case_ids)} run_id={state.get('run_id')}"
    )

    if decision in ("approve", "auto_pass", "degraded_auto_pass"):
        status = "completed"
    elif decision == "reject":
        status = "completed"
    else:
        status = "completed"

    summary = state.get("review_summary", "")
    if not summary:
        summary = (
            f"审核完成：{len(case_ids)} 笔高风险交易，"
            f"决策={decision}，审核人={decision_by}"
        )

    return {
        "status":         status,
        "review_summary": summary,
    }


# ── Graph ─────────────────────────────────────────────────────────

def build_risk_review_graph():
    if not _LANGGRAPH_OK:
        raise RuntimeError("langgraph 未安装")
    g = StateGraph(RiskReviewState)
    g.add_node("fraud_scoring",    _node_fraud_scoring)
    g.add_node("prepare_review",   _node_prepare_review)
    g.add_node("hitl_interrupt",   _node_hitl_interrupt)
    g.add_node("post_review",      _node_post_review)

    g.add_edge(START,            "fraud_scoring")
    g.add_edge("fraud_scoring",  "prepare_review")
    g.add_edge("prepare_review", "hitl_interrupt")
    g.add_edge("hitl_interrupt", "post_review")
    g.add_edge("post_review",    END)
    return g


# ── 执行入口 ────────────────────────────────────────────────────────

async def run_risk_review(
    transaction_features: Optional[List[Dict[str, Any]]] = None,
    thread_id: Optional[str] = None,
    run_id:    Optional[str] = None,
) -> Dict[str, Any]:
    from backend.agents.checkpoint import get_checkpointer
    _run_id    = run_id    or str(uuid.uuid4())
    _thread_id = thread_id or str(uuid.uuid4())

    init_state: RiskReviewState = {
        "run_id":                _run_id,
        "thread_id":             _thread_id,
        "request_id":            _run_id,
        "workflow_name":         "risk_review",
        "status":                "running",
        "transaction_features":  transaction_features or [],
        "case_ids":              [],
        "node_timings":          {},
    }

    # InputGuard 输入安全检查 (对 transaction_features 中的文本字段)
    # Workflow B 主要输入是结构化数据，轻量检查即可

    # SSE 进度通道
    channel = progress_manager.create_channel(_run_id)
    await channel.emit("route_decided", {
        "workflow": "risk_review",
        "modules": ["fraud_scoring", "prepare_review", "hitl_interrupt", "post_review"],
    })

    async with get_checkpointer() as checkpointer:
        graph    = build_risk_review_graph()
        compiled = graph.compile(checkpointer=checkpointer)
        try:
            await channel.emit("step_started", {"step_name": "fraud_scoring"})
            result = await compiled.ainvoke(
                init_state,
                config={"configurable": {"thread_id": _thread_id}},
            )
        except Exception as e:
            # LangGraph interrupt 暂停，状态已保存到 PG checkpoint
            logger.info(f"[RiskReview] interrupted (HITL) thread={_thread_id}: {e}")
            await channel.emit("hitl_required", {
                "thread_id": _thread_id,
                "message": "等待人工审核",
            })
            result = {"status": "paused", "thread_id": _thread_id, "run_id": _run_id}

    # SSE 最终事件
    if result.get("status") == "completed":
        await channel.emit("final", {
            "status": "completed",
            "review_summary": (result.get("review_summary") or "")[:200],
            "node_timings": result.get("node_timings", {}),
        })
    elif result.get("status") == "paused":
        pass  # HITL 等待中，不关闭通道
    else:
        await channel.emit("error", {
            "status": result.get("status", "failed"),
            "error": result.get("error", "unknown"),
        })

    if result.get("status") != "paused":
        await progress_manager.remove_channel(_run_id)

    logger.info(f"[RiskReview] done run_id={_run_id} status={result.get('status')}")
    return result


async def resume_risk_review(thread_id: str) -> Dict[str, Any]:
    """
    恢复因 HITL interrupt 暂停的 risk_review workflow。
    由 admin/reviews.py 在 approve / edit / reject 后触发。

    原理：
      LangGraph 将暂停状态持久化到 PostgreSQL checkpoint。
      传入 None 作为 input，LangGraph 从断点继续执行剩余节点
      （即 _node_post_review → END）。
    """
    from backend.agents.checkpoint import get_checkpointer

    logger.info(f"[RiskReview] resume triggered thread_id={thread_id}")
    result: Dict[str, Any] = {}
    try:
        async with get_checkpointer() as checkpointer:
            graph    = build_risk_review_graph()
            compiled = graph.compile(checkpointer=checkpointer)
            result = await compiled.ainvoke(
                None,
                config={"configurable": {"thread_id": thread_id}},
            )
    except Exception as e:
        logger.info(
            f"[RiskReview] resume finished (may be normal interrupt end) "
            f"thread={thread_id}: {e}"
        )
        result = {"status": "resumed", "thread_id": thread_id}

    logger.info(
        f"[RiskReview] resume done thread={thread_id} status={result.get('status')}"
    )
    return result
