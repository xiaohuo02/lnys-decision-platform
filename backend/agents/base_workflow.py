# -*- coding: utf-8 -*-
"""backend/agents/base_workflow.py

LangGraph 工作流基础骨架
- BaseWorkflowState: 所有 workflow 共用的最小 state 结构
- build_minimal_graph(): 用于冒烟测试的最小可运行图
- 所有真实 workflow 继承 BaseWorkflowState 并单独实现图节点
"""
from __future__ import annotations

import uuid
from typing import Annotated, Any, Dict, List, Optional, TypedDict

# ── 延迟导入 LangGraph，未安装时降级 ──────────────────────────────
try:
    from langgraph.graph import StateGraph, START, END
    from langgraph.graph.message import add_messages
    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False
    StateGraph = None   # type: ignore
    START = "__start__" # type: ignore
    END   = "__end__"   # type: ignore

from loguru import logger


# ── 公共 State 定义 ──────────────────────────────────────────────

class BaseWorkflowState(TypedDict, total=False):
    """所有 workflow 继承的最小 state 结构"""
    run_id:        str
    thread_id:     str
    request_id:    str
    workflow_name: str
    status:        str          # pending / running / paused / completed / failed
    error:         Optional[str]
    artifact_refs: List[str]    # 已生成的 artifact id 列表
    metadata:      Dict[str, Any]


# ── 最小可运行 graph（用于冒烟测试与 checkpoint 验证）─────────────

def _echo_node(state: BaseWorkflowState) -> BaseWorkflowState:
    """最简 echo 节点：将 status 设为 completed"""
    logger.info(f"[echo_node] run_id={state.get('run_id')} thread_id={state.get('thread_id')}")
    return {
        **state,
        "status":   "completed",
        "metadata": {**(state.get("metadata") or {}), "echo": True},
    }


def build_minimal_graph():
    """
    构建最小 LangGraph workflow，用于：
    - 验证 PostgreSQL checkpoint 是否正常工作
    - 作为新 workflow 的模板

    用法：
        from backend.agents.checkpoint import get_checkpointer
        async with get_checkpointer() as cp:
            graph = build_minimal_graph()
            compiled = graph.compile(checkpointer=cp)
            result = await compiled.ainvoke(
                {"run_id": "xxx", "thread_id": "t1", "status": "pending"},
                config={"configurable": {"thread_id": "t1"}}
            )
    """
    if not _LANGGRAPH_AVAILABLE:
        raise RuntimeError(
            "langgraph 未安装。请运行: pip install langgraph langchain-core"
        )

    graph = StateGraph(BaseWorkflowState)
    graph.add_node("echo", _echo_node)
    graph.add_edge(START, "echo")
    graph.add_edge("echo", END)
    return graph


# ── workflow 执行入口（供 router 和 service 调用）────────────────

async def run_minimal_workflow(thread_id: str, run_id: Optional[str] = None) -> Dict[str, Any]:
    """
    运行最小 workflow，返回最终 state。
    主要用于 LangGraph + PostgreSQL checkpoint 集成测试。
    """
    from backend.agents.checkpoint import get_checkpointer

    _run_id = run_id or str(uuid.uuid4())
    init_state: BaseWorkflowState = {
        "run_id":        _run_id,
        "thread_id":     thread_id,
        "request_id":    _run_id,
        "workflow_name": "minimal_smoke_test",
        "status":        "pending",
        "artifact_refs": [],
        "metadata":      {},
    }

    async with get_checkpointer() as checkpointer:
        graph    = build_minimal_graph()
        compiled = graph.compile(checkpointer=checkpointer)
        result   = await compiled.ainvoke(
            init_state,
            config={"configurable": {"thread_id": thread_id}},
        )

    logger.info(f"[minimal_workflow] completed: run_id={_run_id} status={result.get('status')}")
    return result
