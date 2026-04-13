# -*- coding: utf-8 -*-
"""backend/agents/workflows/business_overview.py

Workflow A — 经营总览分析

流程：
  DataPreparation
      → [CustomerIntel, SalesForecast, SentimentIntel, FraudScoring] (并行)
      → InventoryOptimization
      → InsightComposer
      → ReportRendering

每个节点都记录 TraceContext step，输出统一写入 workflow state。
支持 PostgreSQL checkpoint，可在任意节点挂起/恢复。
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from loguru import logger

try:
    from langgraph.graph import StateGraph, START, END
    _LANGGRAPH_OK = True
except ImportError:
    _LANGGRAPH_OK = False
    StateGraph = None  # type: ignore
    START = "__start__"
    END   = "__end__"

from backend.schemas.artifact import ArtifactRef, ArtifactType
from backend.schemas.run_state import RunStatus, StepType

# ── Services ───────────────────────────────────────────────────────
from backend.services.data_preparation_service     import (
    data_preparation_service, DataPrepRequest, DataSource,
)
from backend.services.customer_intelligence_service import (
    customer_intelligence_service, CustomerIntelRequest,
)
from backend.services.sales_forecast_service        import (
    sales_forecast_service, ForecastRequest,
)
from backend.services.sentiment_intelligence_service import (
    sentiment_intelligence_service, SentimentRequest,
)
from backend.services.fraud_scoring_service         import (
    fraud_scoring_service, FraudScoringRequest,
)
from backend.services.inventory_optimization_service import (
    inventory_optimization_service, InventoryRequest,
)
from backend.agents.insight_composer_agent          import (
    insight_composer_agent, InsightComposerInput,
)
from backend.core.progress_channel import (
    progress_manager, make_progress_callback,
)
from backend.governance.guardrails.input_guard import input_guard


# ── Workflow State ─────────────────────────────────────────────────

class BusinessOverviewState(TypedDict, total=False):
    # 输入
    run_id:         str
    thread_id:      str
    request_id:     str
    request_text:   str
    use_mock:       bool

    # 流程控制
    workflow_name:  str
    status:         str
    error:          Optional[str]

    # 各步骤产物摘要（用于传递给下游节点）
    data_quality_summary:  Optional[str]
    customer_summary:      Optional[str]
    forecast_summary:      Optional[str]
    sentiment_summary:     Optional[str]
    fraud_summary:         Optional[str]
    inventory_summary:     Optional[str]

    # artifact refs
    artifact_refs:  List[Dict[str, Any]]   # 序列化后的 ArtifactRef

    # 最终输出
    executive_summary: Optional[str]
    risk_highlights:   Optional[str]
    action_plan:       Optional[str]
    report_uri:        Optional[str]

    # trace 辅助
    node_timings:   Dict[str, float]


# ── SSE 辅助：节点级进度推送 ────────────────────────────────────────

def _emit_sync(run_id: str, event_type: str, data: dict):
    """在同步节点中发送 SSE 事件。

    节点可能运行在 asyncio.run_in_executor 的 worker 线程池里，此线程
    没有 running loop；channel.emit_threadsafe 内部用
    asyncio.run_coroutine_threadsafe 把 coroutine 提交回 channel 创建时
    所在的主 loop，避免手动桥接 event loop 的反模式。
    """
    channel = progress_manager.get_channel(run_id)
    if channel is not None:
        channel.emit_threadsafe(event_type, data)

_NODE_NAMES = {
    "data_preparation": "数据准备",
    "customer_intel": "客户洞察",
    "sales_forecast": "销售预测",
    "sentiment_intel": "舆情分析",
    "fraud_scoring": "欺诈风控",
    "inventory": "库存优化",
    "insight_composer": "智能报告",
}

_NODE_ORDER = [
    "data_preparation",
    "customer_intel", "sales_forecast", "sentiment_intel", "fraud_scoring", "inventory",
    "insight_composer",
]

def _calc_progress(node_name: str) -> int:
    """根据节点顺序计算进度百分比（并行节点共享同一进度段）"""
    _PARALLEL = {"customer_intel", "sales_forecast", "sentiment_intel", "fraud_scoring", "inventory"}
    if node_name in _PARALLEL:
        return 50  # 并行节点统一 50%
    try:
        idx = _NODE_ORDER.index(node_name)
        return int((idx + 1) / len(_NODE_ORDER) * 95)
    except ValueError:
        return 50

def _calc_confidence(result=None, *, exception: bool = False) -> float:
    """从 service result 的 data_ready / degraded 推导置信度 (0~1)"""
    if exception or result is None:
        return 0.2
    data_ready = getattr(result, 'data_ready', None)
    if data_ready is None:
        return 0.7  # 无 data_ready 字段，给中性默认值
    if not data_ready:
        return 0.2
    degraded = getattr(result, 'degraded', False)
    return 0.6 if degraded else 0.9


# ── 节点实现 ────────────────────────────────────────────────────────

def _node_data_preparation(state: BusinessOverviewState) -> BusinessOverviewState:
    run_id = state.get('run_id', '')
    _emit_sync(run_id, 'step_started', {'step_name': 'data_preparation', 'message': '正在准备数据…'})
    t0 = datetime.now(timezone.utc).timestamp()
    logger.info(f"[BizOverview] data_preparation run_id={run_id}")
    try:
        req = DataPrepRequest(
            sources=[
                DataSource.ORDERS, DataSource.CUSTOMERS,
                DataSource.FRAUD, DataSource.REVIEWS, DataSource.INVENTORY,
            ],
            run_id=state.get("run_id"),
            analysis_module="business_overview",
        )
        result = data_preparation_service.prepare(req)
        summary = (
            result.artifact.summary if result.artifact
            else f"数据准备: {result.overall_row_count:,} 行, "
                 f"缺失率={result.overall_missing_ratio:.1%}, "
                 f"ready={result.data_ready}"
        )
        art = [result.artifact.model_dump()] if result.artifact else []
        _conf = _calc_confidence(result)
    except Exception as e:
        logger.error(f"[BizOverview] data_preparation error: {e}")
        summary = f"数据准备失败: {e}"
        art = []
        _conf = _calc_confidence(exception=True)

    timings = dict(state.get("node_timings") or {})
    latency = round(datetime.now(timezone.utc).timestamp() - t0, 3)
    timings["data_preparation"] = latency
    _emit_sync(run_id, 'step_completed', {'step_name': 'data_preparation', 'latency_ms': int(latency * 1000), 'progress_pct': _calc_progress('data_preparation'), 'confidence': _conf})
    return {
        **state,
        "data_quality_summary": summary,
        "artifact_refs": (state.get("artifact_refs") or []) + art,
        "node_timings": timings,
    }


def _node_customer_intel(state: BusinessOverviewState) -> BusinessOverviewState:
    run_id = state.get('run_id', '')
    _emit_sync(run_id, 'step_started', {'step_name': 'customer_intel', 'message': '分析客户数据…'})
    t0 = datetime.now(timezone.utc).timestamp()
    logger.info(f"[BizOverview] customer_intel run_id={run_id}")
    try:
        result = customer_intelligence_service.analyze(
            CustomerIntelRequest(run_id=state.get("run_id"))
        )
        summary = result.artifact.summary if result.artifact else "客户洞察: 数据不可用"
        art = [result.artifact.model_dump()] if result.artifact else []
        _conf = _calc_confidence(result)
    except Exception as e:
        logger.warning(f"[BizOverview] customer_intel error: {e}")
        summary, art = f"客户洞察失败: {e}", []
        _conf = _calc_confidence(exception=True)

    timings = dict(state.get("node_timings") or {})
    latency = round(datetime.now(timezone.utc).timestamp() - t0, 3)
    timings["customer_intel"] = latency
    _emit_sync(run_id, 'step_completed', {'step_name': 'customer_intel', 'latency_ms': int(latency * 1000), 'progress_pct': _calc_progress('customer_intel'), 'confidence': _conf})
    return {
        **state,
        "customer_summary": summary,
        "artifact_refs": (state.get("artifact_refs") or []) + art,
        "node_timings": timings,
    }


def _node_sales_forecast(state: BusinessOverviewState) -> BusinessOverviewState:
    run_id = state.get('run_id', '')
    _emit_sync(run_id, 'step_started', {'step_name': 'sales_forecast', 'message': '预测销售趋势…'})
    t0 = datetime.now(timezone.utc).timestamp()
    logger.info(f"[BizOverview] sales_forecast run_id={run_id}")
    try:
        result = sales_forecast_service.forecast(
            ForecastRequest(run_id=state.get("run_id"), forecast_days=30)
        )
        summary = result.artifact.summary if result.artifact else "预测: 数据不可用"
        art = [result.artifact.model_dump()] if result.artifact else []
        _conf = _calc_confidence(result)
    except Exception as e:
        logger.warning(f"[BizOverview] sales_forecast error: {e}")
        summary, art = f"预测失败: {e}", []
        _conf = _calc_confidence(exception=True)

    timings = dict(state.get("node_timings") or {})
    latency = round(datetime.now(timezone.utc).timestamp() - t0, 3)
    timings["sales_forecast"] = latency
    _emit_sync(run_id, 'step_completed', {'step_name': 'sales_forecast', 'latency_ms': int(latency * 1000), 'progress_pct': _calc_progress('sales_forecast'), 'confidence': _conf})
    return {
        **state,
        "forecast_summary": summary,
        "artifact_refs": (state.get("artifact_refs") or []) + art,
        "node_timings": timings,
    }


def _node_sentiment_intel(state: BusinessOverviewState) -> BusinessOverviewState:
    run_id = state.get('run_id', '')
    _emit_sync(run_id, 'step_started', {'step_name': 'sentiment_intel', 'message': '分析舆情数据…'})
    t0 = datetime.now(timezone.utc).timestamp()
    logger.info(f"[BizOverview] sentiment_intel run_id={run_id}")
    try:
        result = sentiment_intelligence_service.analyze(
            SentimentRequest(run_id=state.get("run_id"))
        )
        summary = result.artifact.summary if result.artifact else "舆情: 数据不可用"
        art = [result.artifact.model_dump()] if result.artifact else []
        _conf = _calc_confidence(result)
    except Exception as e:
        logger.warning(f"[BizOverview] sentiment_intel error: {e}")
        summary, art = f"舆情失败: {e}", []
        _conf = _calc_confidence(exception=True)

    timings = dict(state.get("node_timings") or {})
    latency = round(datetime.now(timezone.utc).timestamp() - t0, 3)
    timings["sentiment_intel"] = latency
    _emit_sync(run_id, 'step_completed', {'step_name': 'sentiment_intel', 'latency_ms': int(latency * 1000), 'progress_pct': _calc_progress('sentiment_intel'), 'confidence': _conf})
    return {
        **state,
        "sentiment_summary": summary,
        "artifact_refs": (state.get("artifact_refs") or []) + art,
        "node_timings": timings,
    }


def _node_fraud_scoring(state: BusinessOverviewState) -> BusinessOverviewState:
    """经营总览场景：用已有批量欺诈评分结果做汇总，不需要单笔实时评分"""
    run_id = state.get('run_id', '')
    _emit_sync(run_id, 'step_started', {'step_name': 'fraud_scoring', 'message': '分析欺诈风险…'})
    t0 = datetime.now(timezone.utc).timestamp()
    logger.info(f"[BizOverview] fraud_scoring run_id={run_id}")
    try:
        # 批量模式：传空特征，服务内部读预计算结果
        result = fraud_scoring_service.score(
            FraudScoringRequest(run_id=state.get("run_id"), features={})
        )
        summary = result.artifact.summary if result.artifact else "欺诈风控: 数据不可用"
        art = [result.artifact.model_dump()] if result.artifact else []
        _conf = _calc_confidence(result)
    except Exception as e:
        logger.warning(f"[BizOverview] fraud_scoring error: {e}")
        summary, art = f"欺诈风控失败: {e}", []
        _conf = _calc_confidence(exception=True)

    timings = dict(state.get("node_timings") or {})
    latency = round(datetime.now(timezone.utc).timestamp() - t0, 3)
    timings["fraud_scoring"] = latency
    _emit_sync(run_id, 'step_completed', {'step_name': 'fraud_scoring', 'latency_ms': int(latency * 1000), 'progress_pct': _calc_progress('fraud_scoring'), 'confidence': _conf})
    return {
        **state,
        "fraud_summary": summary,
        "artifact_refs": (state.get("artifact_refs") or []) + art,
        "node_timings": timings,
    }


def _node_inventory(state: BusinessOverviewState) -> BusinessOverviewState:
    run_id = state.get('run_id', '')
    _emit_sync(run_id, 'step_started', {'step_name': 'inventory', 'message': '优化库存策略…'})
    t0 = datetime.now(timezone.utc).timestamp()
    logger.info(f"[BizOverview] inventory run_id={run_id}")
    try:
        result = inventory_optimization_service.optimize(
            InventoryRequest(run_id=state.get("run_id"))
        )
        summary = result.artifact.summary if result.artifact else "库存: 数据不可用"
        art = [result.artifact.model_dump()] if result.artifact else []
        _conf = _calc_confidence(result)
    except Exception as e:
        logger.warning(f"[BizOverview] inventory error: {e}")
        summary, art = f"库存优化失败: {e}", []
        _conf = _calc_confidence(exception=True)

    timings = dict(state.get("node_timings") or {})
    latency = round(datetime.now(timezone.utc).timestamp() - t0, 3)
    timings["inventory"] = latency
    _emit_sync(run_id, 'step_completed', {'step_name': 'inventory', 'latency_ms': int(latency * 1000), 'progress_pct': _calc_progress('inventory'), 'confidence': _conf})
    return {
        **state,
        "inventory_summary": summary,
        "artifact_refs": (state.get("artifact_refs") or []) + art,
        "node_timings": timings,
    }


# ── state 字段 → ArtifactType 映射表 ────────────────────────────
_SUMMARY_TO_ARTIFACT: List[tuple] = [
    ("customer_summary",  ArtifactType.CUSTOMER_INSIGHT),
    ("forecast_summary",  ArtifactType.FORECAST),
    ("sentiment_summary", ArtifactType.SENTIMENT),
    ("fraud_summary",     ArtifactType.FRAUD_SCORE),
    ("inventory_summary", ArtifactType.INVENTORY),
]


def _build_artifact_refs_from_state(state: BusinessOverviewState) -> List[ArtifactRef]:
    """从 workflow state 摘要字段构建真实 ArtifactRef 列表。
    只收录非空、非错误的摘要，避免把失败提示当数据传给 InsightComposer。
    """
    run_uuid = None
    raw_run_id = state.get("run_id")
    if raw_run_id:
        try:
            run_uuid = uuid.UUID(raw_run_id)
        except (ValueError, AttributeError):
            pass

    refs: List[ArtifactRef] = []
    for field, atype in _SUMMARY_TO_ARTIFACT:
        summary = state.get(field) or ""
        # 过滤 workflow 节点生成的错误摘要：
        #   "xxx失败: <exception>"    —— 包含 "失败:"
        #   "xxx: 数据不可用"         —— 包含 "不可用"
        if summary and "失败:" not in summary and "不可用" not in summary:
            refs.append(ArtifactRef(
                artifact_type=atype,
                run_id=run_uuid,
                summary=summary,
            ))
    return refs


async def _node_insight_composer(state: BusinessOverviewState) -> BusinessOverviewState:
    """异步节点：使用 LLM 生成高质量经营洞察（降级到模板）"""
    run_id = state.get('run_id', '')
    channel = progress_manager.get_channel(run_id)
    if channel:
        await channel.emit('step_started', {'step_name': 'insight_composer', 'message': '生成智能报告…'})
    t0 = datetime.now(timezone.utc).timestamp()
    logger.info(f"[BizOverview] insight_composer run_id={run_id}")
    try:
        use_mock = bool(state.get("use_mock", False))

        # 从 state 构建真实 artifact refs；仅在无真实数据时才降级为 mock
        real_refs = _build_artifact_refs_from_state(state)
        logger.info(
            f"[BizOverview] insight_composer real_refs={len(real_refs)} "
            f"use_mock={use_mock} run_id={state.get('run_id')}"
        )

        inp = InsightComposerInput(
            run_id=state.get("run_id"),
            thread_id=state.get("thread_id"),
            artifact_refs=real_refs,
            use_mock=use_mock or len(real_refs) == 0,
        )
        # 优先使用 LLM 异步合成，失败自动降级到模板
        result = await insight_composer_agent.acompose(inp)
        timings = dict(state.get("node_timings") or {})
        latency = round(datetime.now(timezone.utc).timestamp() - t0, 3)
        timings["insight_composer"] = latency
        _conf = 0.9 if result.data_ready and not result.partial else (0.55 if result.data_ready else 0.2)
        if getattr(result, 'model_used', '') == 'template_fallback':
            _conf = max(_conf - 0.15, 0.3)
        if channel:
            await channel.emit('step_completed', {'step_name': 'insight_composer', 'latency_ms': int(latency * 1000), 'progress_pct': 98, 'confidence': _conf})
        return {
            **state,
            "executive_summary": result.executive_summary,
            "risk_highlights":   result.risk_highlights,
            "action_plan":       result.action_plan,
            "report_uri":        None,
            "status":            "completed" if result.data_ready else "failed",
            "node_timings":      timings,
        }
    except Exception as e:
        logger.error(f"[BizOverview] insight_composer error: {e}")
        timings = dict(state.get("node_timings") or {})
        timings["insight_composer"] = round(datetime.now(timezone.utc).timestamp() - t0, 3)
        return {
            **state,
            "status": "failed",
            "error": str(e),
            "node_timings": timings,
        }


# ── 并行分析节点 (Fan-out / Fan-in) ──────────────────────────────

_PARALLEL_NODES = [
    ("customer_intel",  "客户洞察",   _node_customer_intel),
    ("sales_forecast",  "销售预测",   _node_sales_forecast),
    ("sentiment_intel", "舆情分析",   _node_sentiment_intel),
    ("fraud_scoring",   "欺诈风控",   _node_fraud_scoring),
    ("inventory",       "库存优化",   _node_inventory),
]


async def _node_parallel_analysis(state: BusinessOverviewState) -> BusinessOverviewState:
    """并行执行 5 个分析节点 — asyncio.gather fan-out / fan-in

    关键优化:
    - 5 个节点同时启动 → 总延迟 ≈ max(单节点延迟) 而非 sum
    - 每个节点独立 try/except，单个失败不阻断其他
    - 实时 SSE 推送并行状态
    - Telemetry 记录并行执行指标
    """
    run_id = state.get('run_id', '')
    t0 = datetime.now(timezone.utc).timestamp()

    # SSE: 通知并行阶段开始
    _emit_sync(run_id, 'parallel_started', {
        'nodes': [n[0] for n in _PARALLEL_NODES],
        'message': f'并行执行 {len(_PARALLEL_NODES)} 个分析节点…',
    })

    # Telemetry
    try:
        from backend.core.telemetry import telemetry, TelemetryEventType
        telemetry.emit(TelemetryEventType.WORKFLOW_PARALLEL_STARTED, {
            'nodes': [n[0] for n in _PARALLEL_NODES],
            'count': len(_PARALLEL_NODES),
        }, run_id=run_id, component="BusinessOverviewWorkflow")
    except Exception:
        pass

    async def _run_node(name: str, label: str, fn):
        """在线程池中运行同步节点函数"""
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, fn, state)
            return name, result, None
        except Exception as e:
            logger.error(f"[BizOverview:parallel] {name} failed: {e}")
            return name, None, str(e)

    # Fan-out: 所有节点并行启动
    tasks = [_run_node(n, label, fn) for n, label, fn in _PARALLEL_NODES]
    results = await asyncio.gather(*tasks, return_exceptions=False)

    # Fan-in: 合并所有结果到 state
    merged_state = dict(state)
    merged_timings = dict(state.get("node_timings") or {})
    merged_artifacts = list(state.get("artifact_refs") or [])
    completed_nodes = []
    failed_nodes = []

    for name, result, error in results:
        if error:
            failed_nodes.append(name)
            continue
        if result:
            completed_nodes.append(name)
            # 合并各节点的 summary、artifact_refs、node_timings
            for key in ("customer_summary", "forecast_summary", "sentiment_summary",
                        "fraud_summary", "inventory_summary"):
                if result.get(key):
                    merged_state[key] = result[key]
            if result.get("node_timings"):
                merged_timings.update(result["node_timings"])
            if result.get("artifact_refs"):
                # 取增量部分
                base_len = len(state.get("artifact_refs") or [])
                merged_artifacts.extend(result["artifact_refs"][base_len:])

    total_latency = round(datetime.now(timezone.utc).timestamp() - t0, 3)
    merged_timings["parallel_analysis"] = total_latency

    # SSE: 通知并行阶段完成
    _emit_sync(run_id, 'parallel_completed', {
        'completed': completed_nodes,
        'failed': failed_nodes,
        'latency_ms': int(total_latency * 1000),
        'progress_pct': 75,
    })

    # Telemetry
    try:
        from backend.core.telemetry import telemetry, TelemetryEventType
        telemetry.emit(TelemetryEventType.WORKFLOW_PARALLEL_COMPLETED, {
            'completed': completed_nodes,
            'failed': failed_nodes,
            'latency_ms': int(total_latency * 1000),
            'node_timings': {k: merged_timings.get(k) for k in [n[0] for n in _PARALLEL_NODES] if k in merged_timings},
        }, run_id=run_id, component="BusinessOverviewWorkflow")
    except Exception:
        pass

    logger.info(
        f"[BizOverview:parallel] DONE run_id={run_id} "
        f"completed={completed_nodes} failed={failed_nodes} "
        f"total={total_latency:.2f}s"
    )

    merged_state["artifact_refs"] = merged_artifacts
    merged_state["node_timings"] = merged_timings
    return merged_state


# ── Graph 构建 ─────────────────────────────────────────────────────

def build_business_overview_graph():
    """
    构建经营总览 LangGraph workflow (并行优化版)。

    拓扑：
      START
        → data_preparation
        → parallel_analysis  ← [customer, forecast, sentiment, fraud, inventory 并行]
        → insight_composer
        → END

    并行加速: 5 节点同时执行，总延迟 ≈ max(单节点) 而非 sum(全部)
    """
    if not _LANGGRAPH_OK:
        raise RuntimeError("langgraph 未安装")

    g = StateGraph(BusinessOverviewState)
    g.add_node("data_preparation",   _node_data_preparation)
    g.add_node("parallel_analysis",  _node_parallel_analysis)
    g.add_node("insight_composer",   _node_insight_composer)

    g.add_edge(START,                "data_preparation")
    g.add_edge("data_preparation",   "parallel_analysis")
    g.add_edge("parallel_analysis",  "insight_composer")
    g.add_edge("insight_composer",   END)

    return g


# ── 执行入口 ────────────────────────────────────────────────────────

async def run_business_overview(
    request_text: str = "经营总览分析",
    use_mock:     bool = False,
    thread_id:    Optional[str] = None,
    run_id:       Optional[str] = None,
) -> Dict[str, Any]:
    """
    异步运行经营总览 workflow，返回最终 state。
    供 external router /api/v1/analyze 调用。
    运行全程包裹 TraceContext，确保 runs / run_steps 真实落库。
    """
    from backend.agents.checkpoint import get_checkpointer
    from backend.database import SessionLocal
    from backend.governance.trace_center.tracer import TraceContext
    from backend.schemas.run_state import RunCreate, StepType

    _run_id    = run_id    or str(uuid.uuid4())
    _thread_id = thread_id or str(uuid.uuid4())

    # ── InputGuard 检查 ─────────────────────────────────────────
    guard_result = input_guard.check(request_text or "")
    if not guard_result.passed:
        logger.warning(f"[BizOverview] InputGuard blocked: {guard_result.blocked_reason}")
        return {
            "run_id": _run_id, "status": "blocked",
            "error": guard_result.blocked_reason,
        }
    request_text = guard_result.sanitized_text or request_text

    # ── 创建 SSE 进度通道 ───────────────────────────────────────
    channel = progress_manager.create_channel(_run_id)
    await channel.emit("route_decided", {
        "workflow": "business_overview",
        "topology": "parallel",
        "modules": [
            "data_preparation",
            {"parallel": ["customer_intel", "sales_forecast", "sentiment_intel", "fraud_scoring", "inventory"]},
            "insight_composer",
        ],
    })

    # ── 初始化 TraceContext（后台任务专用 DB session）──────────────
    _db  = None
    ctx  = None
    _wf_step_id = None
    try:
        _db = SessionLocal()
        ctx = TraceContext.start(
            _db,
            RunCreate(
                thread_id=_thread_id,
                request_id=_run_id,
                entrypoint="/api/v1/analyze",
                workflow_name="business_overview",
                input_summary=(request_text or "")[:500],
            ),
        )
        _wf_step_id = ctx.begin_step(
            step_type=StepType.AGENT_CALL,
            step_name="business_overview_graph",
            agent_name="BusinessOverviewWorkflow",
            input_summary=f"use_mock={use_mock} text={(request_text or '')[:60]}",
        )
    except Exception as _te:
        logger.warning(f"[BizOverview] TraceContext init failed (non-fatal): {_te}")
        if _db:
            try:
                _db.close()
            except Exception:
                pass
        _db  = None
        ctx  = None

    # ── 运行 LangGraph workflow ────────────────────────────────────
    _error_msg: Optional[str] = None
    result: Dict[str, Any] = {}
    try:
        init_state: BusinessOverviewState = {
            "run_id":        _run_id,
            "thread_id":     _thread_id,
            "request_id":    _run_id,
            "request_text":  request_text,
            "use_mock":      use_mock,
            "workflow_name": "business_overview",
            "status":        "running",
            "artifact_refs": [],
            "node_timings":  {},
        }
        async with get_checkpointer() as checkpointer:
            graph    = build_business_overview_graph()
            compiled = graph.compile(checkpointer=checkpointer)
            result   = await compiled.ainvoke(
                init_state,
                config={"configurable": {"thread_id": _thread_id}},
            )
    except Exception as _we:
        logger.error(f"[BizOverview] workflow error run_id={_run_id}: {_we}")
        _error_msg = str(_we)
        result = {"status": "failed", "error": _error_msg, "run_id": _run_id}

    # ── 写 trace finish（run + workflow step）─────────────────────
    if ctx and _db and _wf_step_id:
        try:
            _out_summary = (
                (result.get("executive_summary") or "")[:500]
                or result.get("status", "")
            )
            ctx.end_step(
                _wf_step_id,
                output_summary=_out_summary,
                error_message=_error_msg,
            )
            ctx.finish(
                output_summary=_out_summary,
                error_message=_error_msg,
            )
        except Exception as _fe:
            logger.warning(f"[BizOverview] TraceContext finish failed (non-fatal): {_fe}")
        finally:
            try:
                _db.close()
            except Exception:
                pass

    # ── SSE: 发送最终事件并清理通道 ─────────────────────────────────
    if result.get("status") == "completed":
        await channel.emit("final", {
            "status": "completed",
            "executive_summary": result.get("executive_summary") or "",
            "risk_highlights": result.get("risk_highlights") or "",
            "action_plan": result.get("action_plan") or "",
            "node_timings": result.get("node_timings", {}),
        })
    else:
        await channel.emit("error", {
            "status": result.get("status", "failed"),
            "error": result.get("error", "unknown"),
        })
    await progress_manager.remove_channel(_run_id)

    logger.info(
        f"[BizOverview] DONE run_id={_run_id} "
        f"status={result.get('status')} "
        f"timings={result.get('node_timings')}"
    )
    return result
