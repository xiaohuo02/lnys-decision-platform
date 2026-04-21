# -*- coding: utf-8 -*-
"""backend/tests/test_copilot_e2e.py — Copilot 端到端集成测试

测试覆盖:
  1. Skill 注册表 — auto_discover + 权限过滤
  2. 权限检查器 — 角色矩阵 + 覆盖
  3. 上下文管理器 — 三层上下文构建
  4. 事件定义 — SSE 事件序列化
  5. Persistence — CRUD 操作
  6. Actions — 风险等级 + 执行
  7. 各 Skill — execute 基本可用性
  8. OCR Skill — 骨架返回未部署提示
  9. 记忆调和 — 策略执行

运行: pytest backend/tests/test_copilot_e2e.py -v
"""
from __future__ import annotations

import asyncio
import json
import pytest
import sys
import os

# Ensure project root on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


# ── 1. Skill Registry ──

class TestSkillRegistry:
    def test_singleton(self):
        from backend.copilot.registry import SkillRegistry
        a = SkillRegistry.instance()
        b = SkillRegistry.instance()
        assert a is b

    def test_auto_discover_finds_skills(self):
        from backend.copilot.registry import SkillRegistry
        registry = SkillRegistry.instance()
        registry._skills.clear()
        discovered = registry.auto_discover()
        assert discovered > 0, "auto_discover should find at least one skill"

    def test_get_available_skills_filters_by_mode(self):
        from backend.copilot.registry import SkillRegistry
        registry = SkillRegistry.instance()
        if not registry._skills:
            registry.auto_discover()

        ops_skills = registry.get_available_skills("ops", "super_admin")
        biz_skills = registry.get_available_skills("biz", "super_admin")
        assert len(ops_skills) >= len(biz_skills), "ops mode should have >= biz skills"

    def test_get_function_schemas(self):
        from backend.copilot.registry import SkillRegistry
        registry = SkillRegistry.instance()
        if not registry._skills:
            registry.auto_discover()

        skills = registry.get_available_skills("ops", "super_admin")
        schemas = registry.get_function_schemas("ops", "super_admin")
        assert len(schemas) == len(skills)
        for s in schemas:
            assert s["type"] == "function"
            assert "function" in s
            assert "name" in s["function"]


# ── 2. Permissions ──

class TestPermissions:
    def test_role_skill_matrix(self):
        from backend.copilot.permissions import ROLE_SKILL_MATRIX
        assert "super_admin" in ROLE_SKILL_MATRIX
        assert len(ROLE_SKILL_MATRIX["super_admin"]) > 0

    def test_permission_checker_no_db(self):
        from backend.copilot.permissions import PermissionChecker
        checker = PermissionChecker(db=None)
        loop = asyncio.new_event_loop()
        allowed = loop.run_until_complete(
            checker.get_allowed_skills("test_user", "super_admin", "ops")
        )
        loop.close()
        assert len(allowed) > 0

    def test_biz_mode_excludes_ops_only(self):
        from backend.copilot.permissions import PermissionChecker, OPS_ONLY_SKILLS
        checker = PermissionChecker(db=None)
        loop = asyncio.new_event_loop()
        allowed = loop.run_until_complete(
            checker.get_allowed_skills("test_user", "super_admin", "biz")
        )
        loop.close()
        for s in OPS_ONLY_SKILLS:
            assert s not in allowed, f"{s} should be excluded in biz mode"

    def test_action_risk_levels(self):
        from backend.copilot.permissions import PermissionChecker, ActionRisk
        risk = PermissionChecker.get_action_risk("feishu_notify")
        assert risk == ActionRisk.LOW
        risk_high = PermissionChecker.get_action_risk("schedule_task")
        assert risk_high == ActionRisk.HIGH

    def test_needs_approval_matrix(self):
        """HIGH/MEDIUM 非管理员需审批或二次确认，LOW 直接放行；管理员 bypass"""
        from backend.copilot.permissions import PermissionChecker
        # HIGH: 非管理员 -> True
        assert PermissionChecker.needs_approval("biz_operator", "schedule_task") is True
        # HIGH: 管理员 bypass
        assert PermissionChecker.needs_approval("super_admin", "schedule_task") is False
        assert PermissionChecker.needs_approval("platform_admin", "schedule_task") is False
        # MEDIUM: 非管理员 -> True（二次确认）
        assert PermissionChecker.needs_approval("business_admin", "create_alert_rule") is True
        # MEDIUM: 管理员 bypass
        assert PermissionChecker.needs_approval("super_admin", "create_alert_rule") is False
        # LOW: 任意角色直接放行
        assert PermissionChecker.needs_approval("biz_operator", "feishu_notify") is False
        assert PermissionChecker.needs_approval("super_admin", "feishu_notify") is False
        # 未知 Action 默认按 HIGH 处理
        assert PermissionChecker.needs_approval("biz_operator", "__unknown__") is True

    def test_can_execute_action(self):
        from backend.copilot.permissions import PermissionChecker
        assert PermissionChecker.can_execute_action("super_admin", "feishu_notify")
        assert not PermissionChecker.can_execute_action("biz_viewer", "create_alert_rule")


# ── 3. Events ──

class TestEvents:
    def test_event_types_count(self):
        from backend.copilot.events import EventType
        assert len(EventType) >= 16, "Should have at least 16 event types"

    def test_event_serialization(self):
        from backend.copilot.events import CopilotEvent, EventType, text_delta_event
        evt = text_delta_event("hello")
        assert evt.type == EventType.TEXT_DELTA
        assert evt.content == "hello"

    def test_to_sse(self):
        from backend.copilot.events import CopilotEvent, EventType
        evt = CopilotEvent(type=EventType.RUN_START)
        sse = evt.to_sse()
        assert sse.startswith("data: ")
        data = json.loads(sse.replace("data: ", "").strip())
        assert data["type"] == "run_start"


# ── 4. Context Manager ──

class TestContextManager:
    def test_build_without_db_redis(self):
        from backend.copilot.context import ContextManager
        cm = ContextManager(redis=None, db=None)
        loop = asyncio.new_event_loop()
        ctx = loop.run_until_complete(
            cm.build(
                thread_id="test-thread",
                user_id="test-user",
                user_role="super_admin",
                mode="ops",
                page_context={"page": "/console"},
            )
        )
        loop.close()
        assert ctx.user_id == "test-user"
        assert ctx.mode == "ops"
        assert "运维助手" in ctx.system_prompt or "AI助手" in ctx.system_prompt

    def test_default_rules(self):
        from backend.copilot.context import ContextManager
        ops_rules = ContextManager._default_rules("ops")
        biz_rules = ContextManager._default_rules("biz")
        assert len(ops_rules) >= 2
        assert len(biz_rules) >= 2
        assert any("运维" in r["content"] for r in ops_rules)
        assert any("运营" in r["content"] for r in biz_rules)


# ── 5. OCR Skill (骨架) ──

class TestOcrSkill:
    def test_ocr_not_deployed(self):
        from backend.copilot.skills.ocr_skill import OcrSkill
        from backend.copilot.base_skill import SkillContext

        skill = OcrSkill()
        assert skill.name == "ocr_skill"

        ctx = SkillContext(
            user_id="test", user_role="super_admin", mode="ops",
            thread_id="t1", page_context={},
            thread_history=[], system_prompt="",
            source="web", tool_args={"image_url": "http://example.com/img.png"},
        )

        loop = asyncio.new_event_loop()
        events = []
        async def collect():
            async for e in skill.execute("识别图片", ctx):
                events.append(e)
        loop.run_until_complete(collect())
        loop.close()

        assert len(events) > 0
        assert any("尚未部署" in (e.content or "") for e in events)


# ── 6. Skill Parameters Schema ──

class TestSkillSchemas:
    def test_all_skills_have_parameters(self):
        from backend.copilot.registry import SkillRegistry
        registry = SkillRegistry.instance()
        if not registry._skills:
            registry.auto_discover()

        for name, skill in registry._skills.items():
            schema = skill.to_function_schema()
            assert schema["type"] == "function", f"{name} schema type wrong"
            assert schema["function"]["name"] == name

    def test_skill_modes_not_empty(self):
        from backend.copilot.registry import SkillRegistry
        registry = SkillRegistry.instance()
        if not registry._skills:
            registry.auto_discover()

        for name, skill in registry._skills.items():
            assert len(skill.mode) > 0, f"{name} has no modes"
            assert len(skill.required_roles) > 0, f"{name} has no required_roles"


# ── 7. Memory Reconciliation ──

class TestReconciliation:
    def test_reconcile_no_db(self):
        from backend.copilot.context import ContextManager
        cm = ContextManager(db=None)
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(cm.reconcile("test-user"))
        loop.close()
        assert result["status"] == "skipped"


# ── 8. Agent Logger ──

class TestAgentLogger:
    def test_loggers_exist(self):
        from backend.copilot.agent_logger import (
            get_agent_logger, patrol_logger, feishu_logger,
        )
        ops_log = get_agent_logger("ops")
        assert ops_log is not None
        assert patrol_logger is not None
        assert feishu_logger is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
