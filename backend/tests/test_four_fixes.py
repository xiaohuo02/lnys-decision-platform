# -*- coding: utf-8 -*-
"""backend/tests/test_four_fixes.py

四项断点修复的最小回归测试。
不依赖真实 DB / LangGraph / LLM，所有外部依赖通过 MagicMock 或 patch 注入。

运行方式（在 nyshdsjpt/ 目录下）：
    pytest backend/tests/test_four_fixes.py -v

期望输出：全部 PASSED（共 18 个测试）
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ══════════════════════════════════════════════════════════════════
# Fix-1  analyze.py — 三条 workflow 都真实可达
# ══════════════════════════════════════════════════════════════════

class TestFix1AnalyzeRouting:
    """
    验证 analyze.py 对三种路由都会触发 background_tasks.add_task，
    不再走 "占位 else" 分支。
    """

    def _make_sup_output(self, route: str, confidence: float = 0.9):
        out = MagicMock()
        out.route      = route
        out.confidence = confidence
        return out

    @pytest.mark.asyncio
    @patch("backend.routers.external.analyze.input_guard")
    @patch("backend.routers.external.analyze.supervisor_agent")
    async def test_business_overview_triggers_bg_task(self, mock_sup, mock_guard):
        from backend.routers.external.analyze import (
            _run_with_status, analyze,
        )
        mock_sup.aroute = AsyncMock(return_value=self._make_sup_output("business_overview"))
        guard_result = MagicMock(passed=True, sanitized_text=None)
        mock_guard.check.return_value = guard_result

        bg    = MagicMock()
        db    = MagicMock()
        req   = MagicMock()
        req.request_text         = "经营分析"
        req.request_type         = None
        req.use_mock             = False
        req.thread_id            = None
        req.customer_id          = None
        req.transaction_features = None

        await analyze(req, bg, db)

        bg.add_task.assert_called_once()
        called_fn = bg.add_task.call_args[0][0]
        assert called_fn is _run_with_status

    @pytest.mark.asyncio
    @patch("backend.routers.external.analyze.input_guard")
    @patch("backend.routers.external.analyze.supervisor_agent")
    async def test_risk_review_triggers_bg_task(self, mock_sup, mock_guard):
        from backend.routers.external.analyze import (
            _run_with_status, analyze,
        )
        mock_sup.aroute = AsyncMock(return_value=self._make_sup_output("risk_review"))
        guard_result = MagicMock(passed=True, sanitized_text=None)
        mock_guard.check.return_value = guard_result

        bg    = MagicMock()
        db    = MagicMock()
        req   = MagicMock()
        req.request_text         = "审核高风险"
        req.request_type         = None
        req.use_mock             = False
        req.thread_id            = None
        req.customer_id          = None
        req.transaction_features = []

        await analyze(req, bg, db)

        bg.add_task.assert_called_once()
        called_fn = bg.add_task.call_args[0][0]
        assert called_fn is _run_with_status, (
            f"risk_review 路由应触发 _run_with_status，实际: {called_fn}"
        )

    @pytest.mark.asyncio
    @patch("backend.routers.external.analyze.input_guard")
    @patch("backend.routers.external.analyze.supervisor_agent")
    async def test_openclaw_triggers_bg_task(self, mock_sup, mock_guard):
        from backend.routers.external.analyze import (
            _run_with_status, analyze,
        )
        mock_sup.aroute = AsyncMock(return_value=self._make_sup_output("openclaw"))
        guard_result = MagicMock(passed=True, sanitized_text=None)
        mock_guard.check.return_value = guard_result

        bg    = MagicMock()
        db    = MagicMock()
        req   = MagicMock()
        req.request_text         = "查我的订单"
        req.request_type         = None
        req.use_mock             = False
        req.thread_id            = None
        req.customer_id          = "LY000001"
        req.transaction_features = None

        await analyze(req, bg, db)

        bg.add_task.assert_called_once()
        called_fn = bg.add_task.call_args[0][0]
        assert called_fn is _run_with_status, (
            f"openclaw 路由应触发 _run_with_status，实际: {called_fn}"
        )

    @pytest.mark.asyncio
    @patch("backend.routers.external.analyze.input_guard")
    @patch("backend.routers.external.analyze.supervisor_agent")
    async def test_unknown_route_falls_back_to_business_overview(self, mock_sup, mock_guard):
        """未知路由降级到 business_overview，不再静默丢弃。"""
        from backend.routers.external.analyze import (
            _run_with_status, analyze,
        )
        mock_sup.aroute = AsyncMock(return_value=self._make_sup_output("unknown_xyz", 0.2))
        guard_result = MagicMock(passed=True, sanitized_text=None)
        mock_guard.check.return_value = guard_result

        bg    = MagicMock()
        db    = MagicMock()
        req   = MagicMock()
        req.request_text         = "随便说什么"
        req.request_type         = None
        req.use_mock             = False
        req.thread_id            = None
        req.customer_id          = None
        req.transaction_features = None

        await analyze(req, bg, db)

        bg.add_task.assert_called_once()
        called_fn = bg.add_task.call_args[0][0]
        assert called_fn is _run_with_status


# ══════════════════════════════════════════════════════════════════
# Fix-2  business_overview.py — TraceContext 真实落库
# ══════════════════════════════════════════════════════════════════

class TestFix2TraceContext:
    """
    验证 run_business_overview 调用 TraceContext.start() / finish()。
    LangGraph / DB 全部 mock，不需要真实基础设施。
    """

    @pytest.mark.asyncio
    async def test_trace_start_and_finish_called_on_success(self):
        """
        patch 原始模块属性（非调用方），因为 run_business_overview 用 local import。
        SessionLocal → patch backend.database.SessionLocal
        TraceContext  → patch backend.governance.trace_center.tracer.TraceContext
        get_checkpointer → patch backend.agents.checkpoint.get_checkpointer
        """
        mock_ctx = MagicMock()
        mock_ctx.begin_step.return_value = uuid.uuid4()
        mock_db   = MagicMock()
        mock_step_id = uuid.uuid4()
        mock_ctx.begin_step.return_value = mock_step_id

        fake_result = {
            "status": "completed",
            "executive_summary": "经营正常",
            "node_timings": {},
        }
        mock_compiled = AsyncMock()
        mock_compiled.ainvoke.return_value = fake_result

        # async context manager for get_checkpointer
        class FakeCPCtx:
            async def __aenter__(self): return MagicMock()
            async def __aexit__(self, *_): pass

        with (
            patch("backend.database.SessionLocal", return_value=mock_db),
            patch("backend.governance.trace_center.tracer.TraceContext") as MockTC,
            patch("backend.agents.checkpoint.get_checkpointer", return_value=FakeCPCtx()),
            patch(
                "backend.agents.workflows.business_overview.build_business_overview_graph"
            ) as mock_build,
        ):
            MockTC.start.return_value = mock_ctx

            mock_graph = MagicMock()
            mock_graph.compile.return_value = mock_compiled
            mock_build.return_value = mock_graph

            from backend.agents.workflows.business_overview import run_business_overview
            result = await run_business_overview(request_text="测试", run_id="rid-001")

        MockTC.start.assert_called_once()
        mock_ctx.begin_step.assert_called_once()
        mock_ctx.end_step.assert_called_once()
        mock_ctx.finish.assert_called_once()
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_trace_finish_called_even_on_workflow_error(self):
        """workflow 抛异常时，trace 仍然写 finish（带 error_message）。"""
        mock_ctx = MagicMock()
        mock_ctx.begin_step.return_value = uuid.uuid4()
        mock_db   = MagicMock()

        mock_compiled = AsyncMock()
        mock_compiled.ainvoke.side_effect = RuntimeError("DB 连接失败")

        class FakeCPCtx:
            async def __aenter__(self): return MagicMock()
            async def __aexit__(self, *_): pass

        with (
            patch("backend.database.SessionLocal", return_value=mock_db),
            patch("backend.governance.trace_center.tracer.TraceContext") as MockTC,
            patch("backend.agents.checkpoint.get_checkpointer", return_value=FakeCPCtx()),
            patch(
                "backend.agents.workflows.business_overview.build_business_overview_graph"
            ) as mock_build,
        ):
            MockTC.start.return_value = mock_ctx

            mock_graph = MagicMock()
            mock_graph.compile.return_value = mock_compiled
            mock_build.return_value = mock_graph

            from backend.agents.workflows.business_overview import run_business_overview
            result = await run_business_overview(request_text="测试", run_id="rid-002")

        assert result.get("status") == "failed" or "error" in result
        mock_ctx.finish.assert_called_once()
        finish_kwargs = mock_ctx.finish.call_args[1]
        assert finish_kwargs.get("error_message") is not None, (
            "workflow 失败时 finish 必须携带 error_message"
        )


# ══════════════════════════════════════════════════════════════════
# Fix-3  _build_artifact_refs_from_state — 真实 ArtifactRef 组装
# ══════════════════════════════════════════════════════════════════

class TestFix3ArtifactRefs:
    """
    验证 _build_artifact_refs_from_state 从 state 摘要正确构建 ArtifactRef 列表，
    并且过滤掉失败 / 空摘要。
    """

    def setup_method(self):
        from backend.agents.workflows.business_overview import (
            _build_artifact_refs_from_state,
        )
        from backend.schemas.artifact import ArtifactType
        self._build = _build_artifact_refs_from_state
        self._ArtifactType = ArtifactType

    def test_full_state_returns_five_refs(self):
        state = {
            "run_id":           str(uuid.uuid4()),
            "customer_summary": "高流失客户 Top10，RFM 集中在低频群",
            "forecast_summary": "未来 30 天销售环比降 3.2%",
            "sentiment_summary":"负面占 12.3%，主题：物流投诉",
            "fraud_summary":    "高风险 3 笔，中风险 17 笔",
            "inventory_summary":"SKU-001 库存预警，建议补货",
        }
        refs = self._build(state)
        assert len(refs) == 5, f"应生成 5 个 ArtifactRef，实际 {len(refs)}"
        types = {r.artifact_type for r in refs}
        assert self._ArtifactType.CUSTOMER_INSIGHT in types
        assert self._ArtifactType.FORECAST         in types
        assert self._ArtifactType.SENTIMENT        in types
        assert self._ArtifactType.FRAUD_SCORE      in types
        assert self._ArtifactType.INVENTORY        in types

    def test_empty_summaries_returns_empty_refs(self):
        state = {
            "run_id": str(uuid.uuid4()),
            "customer_summary":  "",
            "forecast_summary":  None,
            "sentiment_summary": None,
            "fraud_summary":     None,
            "inventory_summary": None,
        }
        refs = self._build(state)
        assert refs == [], f"空摘要应返回 []，实际 {refs}"

    def test_failed_summaries_are_filtered(self):
        """以"失败"或"不可用"结尾的摘要不应进入 ArtifactRef。"""
        state = {
            "run_id":           str(uuid.uuid4()),
            "customer_summary": "客户洞察失败: 文件不存在",
            "forecast_summary": "预测失败: model error",
            "sentiment_summary":"舆情: 数据不可用",
            "fraud_summary":    "欺诈风控: 数据不可用",
            "inventory_summary":"有效库存摘要：SKU-001 预警",
        }
        refs = self._build(state)
        assert len(refs) == 1, f"仅库存有效，应返回 1 个 ref，实际 {len(refs)}"
        assert refs[0].artifact_type == self._ArtifactType.INVENTORY

    @pytest.mark.asyncio
    async def test_node_insight_composer_uses_real_refs_when_available(self):
        """
        当 state 有真实摘要时，InsightComposerInput.use_mock 应为 False。
        """
        from backend.agents.workflows.business_overview import _node_insight_composer

        mock_compose_output = MagicMock()
        mock_compose_output.executive_summary = "摘要正文"
        mock_compose_output.risk_highlights   = "无高风险"
        mock_compose_output.action_plan       = "行动计划"
        mock_compose_output.data_ready        = True
        mock_compose_output.partial           = False

        captured_inp = {}

        async def fake_acompose(inp):
            captured_inp["inp"] = inp
            return mock_compose_output

        state = {
            "run_id":           str(uuid.uuid4()),
            "use_mock":         False,
            "customer_summary": "有效客户摘要",
            "forecast_summary": "有效预测摘要",
            "sentiment_summary":"有效舆情摘要",
            "fraud_summary":    "有效欺诈摘要",
            "inventory_summary":"有效库存摘要",
            "node_timings":     {},
            "artifact_refs":    [],
        }

        with patch(
            "backend.agents.workflows.business_overview.insight_composer_agent"
        ) as mock_agent:
            mock_agent.acompose = AsyncMock(side_effect=fake_acompose)
            await _node_insight_composer(state)

        assert mock_agent.acompose.called
        passed_inp = captured_inp["inp"]
        assert len(passed_inp.artifact_refs) == 5, (
            f"应传入 5 个真实 refs，实际 {len(passed_inp.artifact_refs)}"
        )
        assert passed_inp.use_mock is False, (
            "有真实 refs 时 use_mock 应为 False"
        )


# ══════════════════════════════════════════════════════════════════
# Fix-4  HITL 闭环 — thread_id 存储 + workflow 恢复
# ══════════════════════════════════════════════════════════════════

class TestFix4HitlCloseLoop:
    """
    验证：
    1. create_review_case_in_db 将 thread_id 存入 context_json
    2. _schedule_workflow_resume 在有 thread_id 时调用 background_tasks.add_task
    3. _schedule_workflow_resume 在无 thread_id 时静默跳过
    """

    def test_create_review_case_stores_thread_id_in_context_json(self):
        from backend.agents.risk_review_agent import create_review_case_in_db

        mock_db = MagicMock()
        execute_result = MagicMock()
        mock_db.execute.return_value = execute_result

        thread_id = "thread-abc-123"
        case_id = create_review_case_in_db(
            db=mock_db,
            run_id="run-001",
            transaction_id="TXN-001",
            fraud_score=0.88,
            risk_level="高风险",
            thread_id=thread_id,
        )

        # 验证 execute 被调用
        assert mock_db.execute.called
        # 找到 context_json 参数
        call_params = mock_db.execute.call_args[0][1]
        ctx = json.loads(call_params["context_json"])
        assert ctx.get("thread_id") == thread_id, (
            f"thread_id 应存入 context_json，实际 context_json={ctx}"
        )
        assert ctx.get("transaction_id") == "TXN-001"
        assert ctx.get("fraud_score") == 0.88

    def test_create_review_case_without_thread_id_stores_none(self):
        """不传 thread_id 时，context_json 中 thread_id 为 None（旧接口兼容）。"""
        from backend.agents.risk_review_agent import create_review_case_in_db

        mock_db = MagicMock()
        create_review_case_in_db(
            db=mock_db,
            run_id="run-002",
            transaction_id="TXN-002",
            fraud_score=0.75,
            risk_level="高风险",
        )
        call_params = mock_db.execute.call_args[0][1]
        ctx = json.loads(call_params["context_json"])
        assert ctx.get("thread_id") is None

    def test_schedule_resume_adds_bg_task_when_thread_id_exists(self):
        from backend.routers.admin.reviews import _schedule_workflow_resume

        context_data = {"thread_id": "thread-xyz-999", "fraud_score": 0.9}
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, i: json.dumps(context_data)

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchone.return_value = mock_row

        mock_bg = MagicMock()

        _schedule_workflow_resume(mock_db, "case-001", mock_bg)

        mock_bg.add_task.assert_called_once()
        call_kwargs = mock_bg.add_task.call_args[1]
        assert call_kwargs.get("thread_id") == "thread-xyz-999"

    def test_schedule_resume_skips_when_no_thread_id(self):
        from backend.routers.admin.reviews import _schedule_workflow_resume

        context_data = {"fraud_score": 0.9}  # 没有 thread_id
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, i: json.dumps(context_data)

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchone.return_value = mock_row

        mock_bg = MagicMock()

        _schedule_workflow_resume(mock_db, "case-002", mock_bg)

        mock_bg.add_task.assert_not_called()

    def test_schedule_resume_skips_when_case_not_found(self):
        from backend.routers.admin.reviews import _schedule_workflow_resume

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchone.return_value = None

        mock_bg = MagicMock()

        _schedule_workflow_resume(mock_db, "nonexistent-case", mock_bg)

        mock_bg.add_task.assert_not_called()

    def test_schedule_resume_non_fatal_on_db_error(self):
        """DB 查询异常时不应抛出，仅 warning，不影响审批响应。"""
        from backend.routers.admin.reviews import _schedule_workflow_resume

        mock_db = MagicMock()
        mock_db.execute.side_effect = Exception("DB 连接断开")

        mock_bg = MagicMock()

        # 不应抛出异常
        _schedule_workflow_resume(mock_db, "case-003", mock_bg)

        mock_bg.add_task.assert_not_called()
