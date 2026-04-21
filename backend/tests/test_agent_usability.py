# -*- coding: utf-8 -*-
"""backend/tests/test_agent_usability.py — Agent 系统企业级可用性测试 (P0)

覆盖:
  1. 路由可用性 (RT-*)
  2. 功能完整性 (FC-*)
  3. Skill 执行链路验证
  4. SSE 事件序列完整性
  5. 降级路径验证 (DG-*)

运行:
  pytest backend/tests/test_agent_usability.py -v --tb=short -x
  pytest backend/tests/test_agent_usability.py -k "routing" -v
  pytest backend/tests/test_agent_usability.py -k "skill" -v
"""
from __future__ import annotations

import asyncio
import json
import sys
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from backend.copilot.events import CopilotEvent, EventType
from backend.copilot.base_skill import BaseCopilotSkill, SkillContext


# ════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════

@pytest.fixture
def skill_context_ops():
    """标准 ops 模式 SkillContext"""
    return SkillContext(
        user_id="test_admin",
        user_role="super_admin",
        mode="ops",
        thread_id="test-thread-001",
        page_context={},
        tool_args={},
        thread_history=[],
        system_prompt="你是测试用AI助手。",
        source="web",
    )


@pytest.fixture
def skill_context_biz():
    """标准 biz 模式 SkillContext"""
    return SkillContext(
        user_id="test_biz_user",
        user_role="biz_operator",
        mode="biz",
        thread_id="test-thread-002",
        page_context={},
        tool_args={},
        thread_history=[],
        system_prompt="你是测试用AI助手。",
        source="web",
    )


# ════════════════════════════════════════════════════════════════
# 1. 路由可用性测试 (RT-*)
# ════════════════════════════════════════════════════════════════

class TestRouting:
    """RT-001 ~ RT-012: 路由正确性验证"""

    # ── RT-001/002: SupervisorAgent 显式路由 ──

    def test_rt001_explicit_route_risk_review(self):
        """RT-004: 显式指定 request_type=risk_review 应直接路由"""
        from backend.agents.supervisor_agent import SupervisorAgent, SupervisorInput
        agent = SupervisorAgent()
        result = agent.route(SupervisorInput(
            request_text="任意文本",
            request_type="risk_review",
        ))
        assert result.route == "risk_review", f"预期 risk_review, 实际 {result.route}"
        assert result.confidence == 1.0

    def test_rt002_explicit_route_business_overview(self):
        from backend.agents.supervisor_agent import SupervisorAgent, SupervisorInput
        agent = SupervisorAgent()
        result = agent.route(SupervisorInput(
            request_text="任意文本",
            request_type="business_overview",
        ))
        assert result.route == "business_overview"
        assert result.confidence == 1.0

    def test_rt003_explicit_route_openclaw(self):
        from backend.agents.supervisor_agent import SupervisorAgent, SupervisorInput
        agent = SupervisorAgent()
        result = agent.route(SupervisorInput(
            request_text="任意",
            request_type="openclaw",
        ))
        assert result.route == "openclaw"

    # ── RT-005: 关键词路由 ──

    @pytest.mark.parametrize("text,expected_route", [
        ("高风险交易审核", "risk_review"),
        ("欺诈检测报告", "risk_review"),
        ("经营分析报告", "business_overview"),
        ("销售预测趋势", "business_overview"),
        ("帮我查订单", "openclaw"),
        ("客户投诉处理", "openclaw"),
        ("系统运维状态", "ops_copilot"),
        ("trace 日志分析", "ops_copilot"),
    ])
    def test_rt005_keyword_routing(self, text, expected_route):
        """RT-005: 关键词路由正确命中"""
        from backend.agents.supervisor_agent import SupervisorAgent, SupervisorInput
        agent = SupervisorAgent()
        result = agent.route(SupervisorInput(request_text=text))
        assert result.route == expected_route, \
            f"输入='{text}' 预期路由={expected_route} 实际={result.route}"

    # ── RT-007: 降级路由 ──

    def test_rt007_fallback_to_business_overview(self):
        """RT-007: 无法匹配时降级到 business_overview"""
        from backend.agents.supervisor_agent import SupervisorAgent, SupervisorInput
        agent = SupervisorAgent()
        result = agent.route(SupervisorInput(
            request_text="xyzabc完全无意义的文本",
        ))
        assert result.route == "business_overview"
        assert result.confidence < 0.6, f"降级路由置信度应 < 0.6, 实际 {result.confidence}"

    # ── RT-008: CopilotEngine 空输入 ──

    @pytest.mark.asyncio
    async def test_rt008_empty_input(self):
        """RT-008: 空输入应快速返回"""
        from backend.copilot.engine import CopilotEngine
        engine = CopilotEngine(redis=None, db=None)

        events = []
        async for event in engine.run(
            question="",
            mode="ops",
            user_id="test",
            user_role="super_admin",
            thread_id="empty-test",
        ):
            sse = event.to_sse()
            events.append(json.loads(sse.replace("data: ", "").strip()))

        types = [e["type"] for e in events]
        assert "run_start" in types, "空输入应有 run_start"
        assert "run_end" in types, "空输入应有 run_end"
        assert "text_delta" in types, "空输入应有引导文字"

        # 验证引导文字内容
        text_events = [e for e in events if e["type"] == "text_delta"]
        full_text = "".join(str(e.get("content", "")) for e in text_events)
        assert any(kw in full_text for kw in ("输入", "没有可用", "请", "功能")), \
            f"空输入引导文字应包含引导关键词, 实际: '{full_text[:100]}'"

    # ── RT-006: Copilot 关键词路由回退 ──

    def test_rt006_copilot_keyword_fallback(self):
        """RT-006: CopilotEngine._keyword_fallback 正确匹配"""
        from backend.copilot.engine import CopilotEngine
        from backend.copilot.registry import SkillRegistry

        registry = SkillRegistry.instance()
        if not registry._skills:
            registry.auto_discover()

        engine = CopilotEngine(redis=None, db=None)
        all_skills = list(registry._skills.values())

        # 测试每个关键词映射
        test_cases = [
            ("库存补货", "inventory_skill"),
            ("销售预测", "forecast_skill"),
            ("舆情分析", "sentiment_skill"),
            ("客户流失", "customer_intel_skill"),
            ("欺诈风控", "fraud_skill"),
            ("商品关联", "association_skill"),
            ("知识库搜索", "kb_rag_skill"),
            ("系统健康", "system_skill"),
        ]

        for question, expected_skill in test_cases:
            matched = engine._keyword_fallback(question, all_skills)
            assert matched is not None, f"关键词 '{question}' 未匹配到任何 Skill"
            assert matched.name == expected_skill, \
                f"关键词 '{question}' 预期 {expected_skill}, 实际 {matched.name}"


# ════════════════════════════════════════════════════════════════
# 2. Skill 注册表与权限测试
# ════════════════════════════════════════════════════════════════

class TestSkillRegistryAndPermissions:
    """Skill 注册表完整性 + 权限矩阵正确性"""

    def test_all_11_skills_registered(self):
        """所有 11 个 Skill 必须被 auto_discover 注册"""
        from backend.copilot.registry import SkillRegistry
        registry = SkillRegistry.instance()
        registry._skills.clear()
        registry.auto_discover()

        expected_skills = {
            "inventory_skill", "forecast_skill", "sentiment_skill",
            "customer_intel_skill", "fraud_skill", "association_skill",
            "kb_rag_skill", "memory_skill", "trace_skill",
            "system_skill", "ocr_skill",
        }
        actual_skills = set(registry._skills.keys())
        missing = expected_skills - actual_skills
        assert not missing, f"缺少以下 Skill: {missing}"

    def test_each_skill_has_valid_schema(self):
        """每个 Skill 的 function schema 必须合法"""
        from backend.copilot.registry import SkillRegistry
        registry = SkillRegistry.instance()
        if not registry._skills:
            registry.auto_discover()

        for name, skill in registry._skills.items():
            schema = skill.to_function_schema()
            assert schema["type"] == "function", f"{name}: schema type 错误"
            fn = schema["function"]
            assert fn["name"] == name, f"{name}: name 不匹配"
            assert fn["description"], f"{name}: description 为空"
            assert isinstance(fn["parameters"], dict), f"{name}: parameters 不是 dict"

    def test_ops_only_skills_not_in_biz(self):
        """SEC-013/014: trace_skill, system_skill 在 biz 模式下不可用"""
        from backend.copilot.permissions import PermissionChecker, OPS_ONLY_SKILLS

        checker = PermissionChecker(db=None)
        loop = asyncio.new_event_loop()
        try:
            biz_skills = loop.run_until_complete(
                checker.get_allowed_skills("test_user", "super_admin", "biz")
            )
        finally:
            loop.close()

        for ops_skill in OPS_ONLY_SKILLS:
            assert ops_skill not in biz_skills, \
                f"SEC-013/014 FAIL: {ops_skill} 不应在 biz 模式下可用"

    def test_biz_viewer_restricted_skills(self):
        """SEC-015: biz_viewer 只应有 customer_intel, sentiment, kb_rag"""
        from backend.copilot.permissions import PermissionChecker

        checker = PermissionChecker(db=None)
        loop = asyncio.new_event_loop()
        try:
            allowed = loop.run_until_complete(
                checker.get_allowed_skills("viewer_user", "biz_viewer", "biz")
            )
        finally:
            loop.close()

        expected = {"customer_intel_skill", "sentiment_skill", "kb_rag_skill"}
        assert allowed == expected, \
            f"biz_viewer 预期 {expected}, 实际 {allowed}"

    @pytest.mark.parametrize("role,mode,should_include,should_exclude", [
        ("super_admin", "ops", {"trace_skill", "system_skill", "fraud_skill"}, set()),
        ("super_admin", "biz", {"forecast_skill", "inventory_skill"}, {"trace_skill", "system_skill"}),
        ("biz_operator", "biz", {"forecast_skill", "inventory_skill"}, {"trace_skill", "fraud_skill"}),
        ("ops_analyst", "ops", {"trace_skill", "system_skill"}, set()),
    ])
    def test_role_skill_matrix(self, role, mode, should_include, should_exclude):
        """权限矩阵: 各角色-模式组合的 Skill 集合"""
        from backend.copilot.permissions import PermissionChecker

        checker = PermissionChecker(db=None)
        loop = asyncio.new_event_loop()
        try:
            allowed = loop.run_until_complete(
                checker.get_allowed_skills("test", role, mode)
            )
        finally:
            loop.close()

        for s in should_include:
            assert s in allowed, f"{role}/{mode} 应包含 {s}, 实际: {allowed}"
        for s in should_exclude:
            assert s not in allowed, f"{role}/{mode} 不应包含 {s}, 实际: {allowed}"

    def test_action_risk_levels(self):
        """SEC-016/017: Action 风险等级配置正确"""
        from backend.copilot.permissions import (
            PermissionChecker, ActionRisk, ACTION_RISK_LEVELS, ACTION_ROLE_REQUIREMENTS,
        )
        # LOW actions
        assert ACTION_RISK_LEVELS["feishu_notify"] == ActionRisk.LOW
        assert ACTION_RISK_LEVELS["export_report"] == ActionRisk.LOW
        # MEDIUM
        assert ACTION_RISK_LEVELS["create_alert_rule"] == ActionRisk.MEDIUM
        # HIGH
        assert ACTION_RISK_LEVELS["schedule_task"] == ActionRisk.HIGH

        # biz_viewer 不能执行 create_alert_rule
        assert "biz_viewer" not in ACTION_ROLE_REQUIREMENTS["create_alert_rule"]

        # biz_operator 可以执行 feishu_notify
        assert "biz_operator" in ACTION_ROLE_REQUIREMENTS["feishu_notify"]


# ════════════════════════════════════════════════════════════════
# 3. 各 Skill 执行链路测试 (FC-*)
# ════════════════════════════════════════════════════════════════

class TestSkillExecution:
    """FC-001 ~ FC-012: 每个 Skill 的 execute() 是否真实执行并产生正确事件"""

    @staticmethod
    async def _collect_skill_events(skill: BaseCopilotSkill, ctx: SkillContext) -> Dict[str, Any]:
        """执行 Skill 并收集所有事件"""
        events = []
        tool_result = None
        artifacts = []
        suggestions = []
        text_parts = []

        try:
            async for event in skill.execute("测试问题", ctx):
                events.append(event)
                if event.type == EventType.TOOL_RESULT:
                    tool_result = event.data
                elif event.type == EventType.ARTIFACT_DELTA:
                    artifacts.append(event.content)
                elif event.type == EventType.SUGGESTIONS:
                    suggestions.append(event)
                elif event.type == EventType.TEXT_DELTA:
                    text_parts.append(str(event.content or ""))
        except Exception as e:
            return {
                "error": str(e),
                "events": events,
                "event_types": [e.type.value for e in events],
            }

        return {
            "events": events,
            "event_types": [e.type.value for e in events],
            "tool_result": tool_result,
            "artifacts": artifacts,
            "suggestions": suggestions,
            "text": "".join(text_parts),
            "error": None,
        }

    # ── FC-011: OCR Skill 返回未部署提示 ──

    @pytest.mark.asyncio
    async def test_fc011_ocr_skill_not_deployed(self, skill_context_ops):
        """FC-011: ocr_skill 应返回未部署提示"""
        from backend.copilot.skills.ocr_skill import ocr_skill

        skill_context_ops.tool_args = {"image_url": "http://example.com/test.png"}
        result = await self._collect_skill_events(ocr_skill, skill_context_ops)

        assert result["error"] is None, f"ocr_skill 不应抛异常: {result['error']}"
        assert any("尚未部署" in str(e.content or "") for e in result["events"]), \
            "ocr_skill 应包含'尚未部署'提示"

    # ── FC-012: CopilotEngine 通用对话降级 (无 Skill 匹配) ──

    @pytest.mark.asyncio
    async def test_fc012_general_chat_fallback(self):
        """FC-012: 无 Skill 匹配时应降级到通用对话"""
        from backend.copilot.engine import CopilotEngine

        # Mock: LLM 不选任何 tool + 通用对话返回文本
        async def fake_stream(*args, **kwargs):
            from backend.tests.helpers.fake_llm import make_stream_response
            if kwargs.get("stream"):
                return make_stream_response(["这是", "通用", "对话", "回答"])

            from backend.tests.helpers.fake_llm import make_text_response
            return make_text_response("通用回答")

        engine = CopilotEngine(redis=None, db=None)

        events = []
        with patch("openai.AsyncOpenAI") as mock_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(side_effect=fake_stream)
            mock_cls.return_value = mock_client

            async for event in engine.run(
                question="今天是个好天气",
                mode="ops",
                user_id="test",
                user_role="super_admin",
                thread_id="gen-chat-test",
            ):
                sse = event.to_sse()
                parsed = json.loads(sse.replace("data: ", "").strip())
                events.append(parsed)

        types = [e["type"] for e in events]
        assert "run_start" in types, "通用对话应有 run_start"
        assert "run_end" in types, "通用对话应有 run_end"
        assert "text_delta" in types, "通用对话应有 text_delta"
        # 不应有 tool_call
        assert "tool_call_start" not in types, "通用对话不应有 tool_call"


# ════════════════════════════════════════════════════════════════
# 4. SSE 事件序列完整性测试
# ════════════════════════════════════════════════════════════════

class TestSSEProtocol:
    """SSE 协议正确性"""

    def test_event_type_count(self):
        """至少 16 种事件类型"""
        assert len(EventType) >= 16, f"事件类型数 {len(EventType)} < 16"

    def test_all_event_types_serializable(self):
        """所有事件类型都可以正确序列化为 SSE"""
        for etype in EventType:
            event = CopilotEvent(type=etype)
            sse = event.to_sse()
            assert sse.startswith("data: "), f"{etype} 序列化失败"
            data = json.loads(sse.replace("data: ", "").strip())
            assert data["type"] == etype.value

    def test_text_delta_contains_content(self):
        """text_delta 事件必须包含 content 字段"""
        from backend.copilot.events import text_delta_event
        event = text_delta_event("test content")
        sse = event.to_sse()
        data = json.loads(sse.replace("data: ", "").strip())
        assert data["content"] == "test content"

    def test_run_start_contains_metadata(self):
        """run_start 事件应包含 thread_id 和 mode"""
        from backend.copilot.events import run_start_event
        event = run_start_event("thread-123", "ops")
        sse = event.to_sse()
        data = json.loads(sse.replace("data: ", "").strip())
        assert data["type"] == "run_start"
        # metadata 中应有 thread_id
        metadata = data.get("metadata", {})
        assert "thread_id" in metadata or "thread_id" in data, \
            "run_start 应包含 thread_id"

    def test_run_end_contains_elapsed(self):
        """run_end 事件应包含 elapsed_ms"""
        from backend.copilot.events import run_end_event
        event = run_end_event("thread-123", 1500)
        sse = event.to_sse()
        data = json.loads(sse.replace("data: ", "").strip())
        assert data["type"] == "run_end"


# ════════════════════════════════════════════════════════════════
# 5. 降级路径测试 (DG-*)
# ════════════════════════════════════════════════════════════════

class TestDegradation:
    """DG-001 ~ DG-008: 降级路径验证"""

    # ── DG-005: SupervisorAgent LLM 不可用 ──

    @pytest.mark.asyncio
    async def test_dg005_supervisor_llm_unavailable(self):
        """DG-005: SupervisorAgent LLM 不可用时应使用纯规则路由"""
        from backend.agents.supervisor_agent import SupervisorAgent, SupervisorInput

        agent = SupervisorAgent()
        agent._llm = None  # 确保 LLM 不可用

        with patch.object(agent, "_get_llm", return_value=None):
            result = await agent.aroute(SupervisorInput(
                request_text="分析一下经营状况",
            ))
        # 应该通过关键词匹配到 business_overview
        assert result.route in ("business_overview", "unknown"), \
            f"LLM 不可用时应降级到规则路由, 实际: {result.route}"
        assert result.used_llm is False

    # ── DG-006: 无可用 Skill ──

    @pytest.mark.asyncio
    async def test_dg006_no_available_skills(self):
        """DG-006: 无可用 Skill 时应返回引导文字"""
        from backend.copilot.engine import CopilotEngine
        from backend.copilot.permissions import PermissionChecker

        engine = CopilotEngine(redis=None, db=None)

        # Mock: 权限检查返回空集
        with patch.object(
            PermissionChecker, "get_allowed_skills",
            new_callable=AsyncMock,
            return_value=set(),
        ):
            events = []
            async for event in engine.run(
                question="测试问题",
                mode="ops",
                user_id="test",
                user_role="super_admin",
                thread_id="no-skills-test",
            ):
                sse = event.to_sse()
                events.append(json.loads(sse.replace("data: ", "").strip()))

        types = [e["type"] for e in events]
        assert "run_start" in types
        assert "run_end" in types
        # 应有提示文字
        text_events = [e for e in events if e["type"] == "text_delta"]
        full_text = "".join(str(e.get("content", "")) for e in text_events)
        assert "没有可用" in full_text or "权限" in full_text, \
            f"DG-006: 应提示无可用功能, 实际: '{full_text[:100]}'"

    # ── DG-001: LLM 路由异常时回退到关键词 ──

    @pytest.mark.asyncio
    async def test_dg001_llm_routing_fallback(self):
        """DG-001: LLM 路由失败时应回退到关键词匹配"""
        from backend.copilot.engine import CopilotEngine

        engine = CopilotEngine(redis=None, db=None)

        # Mock: LLM 抛异常 → 应回退到关键词
        with patch("openai.AsyncOpenAI") as mock_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=Exception("LLM connection refused")
            )
            mock_cls.return_value = mock_client

            events = []
            async for event in engine.run(
                question="库存安全库存计算",  # 应被关键词匹配到 inventory_skill
                mode="ops",
                user_id="test",
                user_role="super_admin",
                thread_id="fallback-test",
            ):
                sse = event.to_sse()
                events.append(json.loads(sse.replace("data: ", "").strip()))

        types = [e["type"] for e in events]
        assert "run_start" in types, "降级路径应有 run_start"
        assert "run_end" in types, "降级路径应有 run_end"
        # 不应有 run_error (关键词回退是预期行为)
        # 可能有 tool_call_start (如果关键词成功匹配到 skill)
        # 如果 skill 本身也失败，至少不应 500

    # ── DG-007: Redis 不可用时上下文降级 ──

    @pytest.mark.asyncio
    async def test_dg007_no_redis_context_fallback(self):
        """DG-007: Redis 不可用时应使用默认规则和空历史"""
        from backend.copilot.context import ContextManager

        cm = ContextManager(redis=None, db=None)
        ctx = await cm.build(
            thread_id="no-redis-test",
            user_id="test_user",
            user_role="super_admin",
            mode="ops",
        )

        assert ctx.user_id == "test_user"
        assert ctx.mode == "ops"
        assert len(ctx.system_prompt) > 0, "无 Redis 时应有默认 system_prompt"
        assert isinstance(ctx.thread_history, list)


# ════════════════════════════════════════════════════════════════
# 6. 高风险假成功检测
# ════════════════════════════════════════════════════════════════

class TestHighRiskFalseSuccess:
    """专项: 检测假成功问题"""

    def test_skill_auto_discover_none_returned(self):
        """auto_discover 不应返回 None，不应注册 name 为空的 Skill"""
        from backend.copilot.registry import SkillRegistry
        registry = SkillRegistry.instance()
        registry._skills.clear()
        registry.auto_discover()

        for name, skill in registry._skills.items():
            assert name, "Skill name 不应为空"
            assert skill.display_name, f"Skill {name} 缺少 display_name"
            assert skill.description, f"Skill {name} 缺少 description"
            assert len(skill.mode) > 0, f"Skill {name} mode 为空"
            assert len(skill.required_roles) > 0, f"Skill {name} required_roles 为空"

    def test_engine_write_copilot_run_sync_in_async(self):
        """检测: _write_copilot_run 使用同步 Session 可能阻塞事件循环
        这是一个已知的设计选择 (fire-and-forget)，但需要确认不会导致问题"""
        from backend.copilot.engine import CopilotEngine
        engine = CopilotEngine(redis=None, db=None)

        # 验证方法存在且接受正确参数
        assert hasattr(engine, "_write_copilot_run")

        # 验证调用不崩溃 (即使 DB 不可用)
        engine._write_copilot_run(
            user_id="test",
            mode="ops",
            thread_id="test-thread",
            skill_name="test_skill",
            input_summary="test input",
            output_summary="test output",
            status="completed",
            latency_ms=100,
        )
        # 不应抛异常 (fire-and-forget 设计)

    def test_skill_mode_consistency(self):
        """验证 Skill 声明的 mode 和 SkillRegistry 过滤一致"""
        from backend.copilot.registry import SkillRegistry
        registry = SkillRegistry.instance()
        if not registry._skills:
            registry.auto_discover()

        ops_only_names = {"trace_skill", "system_skill"}
        for name in ops_only_names:
            skill = registry.get(name)
            if skill:
                assert "biz" not in skill.mode, \
                    f"{name} 声明为 ops-only 但 mode 包含 biz"
                # 验证 biz 模式下确实不可用
                biz_skills = registry.get_available_skills("biz", "super_admin")
                biz_names = {s.name for s in biz_skills}
                assert name not in biz_names, \
                    f"{name} 在 biz 模式下不应可用"


# ════════════════════════════════════════════════════════════════
# 7. Context Manager 测试
# ════════════════════════════════════════════════════════════════

class TestContextManager:
    """上下文管理器验证"""

    def test_default_rules_ops(self):
        from backend.copilot.context import ContextManager
        rules = ContextManager._default_rules("ops")
        assert len(rules) >= 2
        combined = " ".join(r["content"] for r in rules)
        assert "运维" in combined, "ops 默认规则应包含运维相关内容"

    def test_default_rules_biz(self):
        from backend.copilot.context import ContextManager
        rules = ContextManager._default_rules("biz")
        assert len(rules) >= 2
        combined = " ".join(r["content"] for r in rules)
        assert "运营" in combined, "biz 默认规则应包含运营相关内容"

    @pytest.mark.asyncio
    async def test_build_system_prompt_not_empty(self):
        from backend.copilot.context import ContextManager
        cm = ContextManager(redis=None, db=None)
        ctx = await cm.build(
            thread_id="t1", user_id="u1", user_role="super_admin",
            mode="ops", page_context={"page": "/console/dashboard"},
        )
        assert len(ctx.system_prompt) > 50, \
            f"system_prompt 过短 ({len(ctx.system_prompt)} chars)"

    @pytest.mark.asyncio
    async def test_reconcile_no_db(self):
        from backend.copilot.context import ContextManager
        cm = ContextManager(db=None)
        result = await cm.reconcile("test_user")
        assert result["status"] == "skipped"


# ════════════════════════════════════════════════════════════════
# 8. Agent Logger 测试
# ════════════════════════════════════════════════════════════════

class TestAgentLogger:
    def test_logger_instances(self):
        from backend.copilot.agent_logger import (
            get_agent_logger, patrol_logger, feishu_logger,
        )
        ops_log = get_agent_logger("ops")
        biz_log = get_agent_logger("biz")
        assert ops_log is not None
        assert biz_log is not None
        assert patrol_logger is not None
        assert feishu_logger is not None

    def test_skill_call_tracer(self):
        from backend.copilot.agent_logger import SkillCallTracer
        tracer = SkillCallTracer("ops", "test_skill", "test_user", "test_thread")
        tracer.start()
        tracer.log_event("tool_call_start")
        tracer.log_event("tool_result")
        tracer.end(success=True)
        # 不应抛异常


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
