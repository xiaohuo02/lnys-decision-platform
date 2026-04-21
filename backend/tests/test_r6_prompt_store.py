# -*- coding: utf-8 -*-
"""backend/tests/test_r6_prompt_store.py — R6-4 PromptStore 单元测试

覆盖:
  1. register / get / list_keys / list_versions
  2. render 变量替换 + PROMPT_USED 遥测
  3. 多版本 + 默认版本语义
  4. 灰度分桶 (resolve_version)
  5. load_from_yaml_dir（使用临时 YAML 目录）
  6. load_from_db（mock CopilotRule row）
  7. load_from_skill_registry（mock skill.summarization_hint）
  8. summary
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.core.prompt_store import (  # noqa: E402
    PromptStore,
    PromptTemplate,
    GrayscaleRule,
)


# ── Helpers ──────────────────────────────────────────────────

def _make_tpl(key: str, version: str = "v1", content: str = "hello {name}",
              source: str = "inline") -> PromptTemplate:
    return PromptTemplate(
        key=key, version=version, content=content,
        variables=["name"], source=source,
    )


# ── 测试 1: 基础注册/查询 ─────────────────────────────────────

class TestPromptStoreBasic:
    def test_register_and_get(self):
        ps = PromptStore()
        tpl = _make_tpl("a.b.c")
        ps.register(tpl)

        assert ps.get("a.b.c") is tpl
        assert ps.get("a.b.c", version="v1") is tpl
        assert ps.get("nonexistent") is None

    def test_register_requires_key_and_version(self):
        ps = PromptStore()
        with pytest.raises(ValueError):
            ps.register(PromptTemplate(key="", version="v1", content=""))
        with pytest.raises(ValueError):
            ps.register(PromptTemplate(key="x", version="", content=""))

    def test_list_keys_and_versions(self):
        ps = PromptStore()
        ps.register(_make_tpl("a.b", version="v1"))
        ps.register(_make_tpl("a.b", version="v2"))
        ps.register(_make_tpl("x.y", version="v1"))

        assert ps.list_keys() == ["a.b", "x.y"]
        assert ps.list_versions("a.b") == ["v1", "v2"]
        assert ps.list_versions("missing") == []

    def test_set_as_default_is_last_registered(self):
        ps = PromptStore()
        ps.register(_make_tpl("a.b", version="v1"), set_as_default=True)
        ps.register(_make_tpl("a.b", version="v2"), set_as_default=True)

        # get 不带 version → 默认 = v2（最后注册的）
        assert ps.get("a.b").version == "v2"

    def test_set_as_default_false_keeps_previous(self):
        ps = PromptStore()
        ps.register(_make_tpl("a.b", version="v1"), set_as_default=True)
        ps.register(_make_tpl("a.b", version="v2"), set_as_default=False)

        assert ps.get("a.b").version == "v1"
        assert ps.get("a.b", version="v2").version == "v2"


# ── 测试 2: render 变量替换 + 遥测 ─────────────────────────

class TestPromptStoreRender:
    def test_render_simple_replacement(self):
        ps = PromptStore()
        ps.register(_make_tpl("greet", content="Hello {name}!"))

        assert ps.render("greet", variables={"name": "Alice"}) == "Hello Alice!"

    def test_render_missing_var_keeps_placeholder(self):
        """未提供变量值时，{placeholder} 原样保留（不抛异常）。"""
        ps = PromptStore()
        ps.register(_make_tpl("greet", content="Hello {name}, age {age}"))

        assert ps.render("greet", variables={"name": "Bob"}) == "Hello Bob, age {age}"

    def test_render_missing_key_raises(self):
        ps = PromptStore()
        with pytest.raises(KeyError):
            ps.render("nonexistent")

    def test_render_emits_telemetry(self, monkeypatch):
        """render 调用应发 PROMPT_USED 事件到 telemetry。"""
        from backend.core.telemetry import telemetry, TelemetryEventType

        telemetry.clear()
        ps = PromptStore()
        ps.register(_make_tpl("tele.key", content="hi"))

        ps.render("tele.key", user_id="u123")

        events = telemetry.recent()
        types = [e["type"] for e in events]
        assert TelemetryEventType.PROMPT_USED.value in types
        # 找到那条事件，检查 metadata
        prompt_events = [e for e in events if e["type"] == TelemetryEventType.PROMPT_USED.value]
        assert len(prompt_events) == 1
        data = prompt_events[0]["data"]
        assert data["key"] == "tele.key"
        assert data["version"] == "v1"
        assert data["user_id"] == "u123"


# ── 测试 3: 灰度分桶 ─────────────────────────────────────────

class TestPromptStoreGrayscale:
    def test_no_rule_uses_default_version(self):
        ps = PromptStore()
        ps.register(_make_tpl("g.test", version="v1"), set_as_default=True)
        ps.register(_make_tpl("g.test", version="v2"), set_as_default=False)

        # 无规则，始终返回默认 v1
        assert ps.resolve_version("g.test", user_id="anyone") == "v1"

    def test_100_percent_rule_always_hits(self):
        ps = PromptStore()
        ps.register(_make_tpl("g.test", version="v1"), set_as_default=True)
        ps.register(_make_tpl("g.test", version="v2"), set_as_default=False)
        ps.add_gray_rule(GrayscaleRule(
            key="g.test", target_version="v2", percent=100,
        ))

        # 任何 user_id 都分到 v2
        assert ps.resolve_version("g.test", user_id="u1") == "v2"
        assert ps.resolve_version("g.test", user_id="u2") == "v2"
        assert ps.resolve_version("g.test", user_id="u3") == "v2"

    def test_0_percent_rule_never_hits(self):
        ps = PromptStore()
        ps.register(_make_tpl("g.test", version="v1"), set_as_default=True)
        ps.register(_make_tpl("g.test", version="v2"))
        ps.add_gray_rule(GrayscaleRule(
            key="g.test", target_version="v2", percent=0,
        ))

        # 0% 规则永不命中 → 返回默认 v2（register 最后设为 default）
        assert ps.resolve_version("g.test", user_id="u1") == "v2"

    def test_50_percent_rule_splits(self):
        """50% 灰度，大量 user_id 样本应大致 50:50 分流。"""
        ps = PromptStore()
        ps.register(_make_tpl("g.test", version="v1"), set_as_default=True)
        ps.register(_make_tpl("g.test", version="v2"), set_as_default=False)
        ps.add_gray_rule(GrayscaleRule(
            key="g.test", target_version="v2", percent=50,
        ))

        v2_hits = 0
        total = 1000
        for i in range(total):
            if ps.resolve_version("g.test", user_id=f"user_{i}") == "v2":
                v2_hits += 1

        # 误差容忍 ±10%
        assert 350 < v2_hits < 650, f"v2 分桶比例={v2_hits/total:.2%}"

    def test_invalid_percent_raises(self):
        ps = PromptStore()
        with pytest.raises(ValueError):
            ps.add_gray_rule(GrayscaleRule(key="x", target_version="v1", percent=-1))
        with pytest.raises(ValueError):
            ps.add_gray_rule(GrayscaleRule(key="x", target_version="v1", percent=101))


# ── 测试 4: YAML 加载 ───────────────────────────────────────

class TestPromptStoreYaml:
    def test_load_existing_governance_dir(self):
        """加载项目内 backend/governance/prompt_center/ 的示例 YAML。"""
        ps = PromptStore()
        dir_path = Path(__file__).parent.parent / "governance" / "prompt_center"
        count = ps.load_from_yaml_dir(dir_path)

        # 至少有 3 个示例文件（general_chat.v1 / synthesize_base.v1/v2）
        assert count >= 3
        assert "agent.general_chat" in ps.list_keys()
        assert "agent.synthesize_base" in ps.list_keys()
        # synthesize_base 有两个版本
        versions = ps.list_versions("agent.synthesize_base")
        assert "v1" in versions and "v2" in versions

    def test_load_nonexistent_dir_returns_zero(self):
        ps = PromptStore()
        count = ps.load_from_yaml_dir(Path("/this/does/not/exist"))
        assert count == 0


# ── 测试 5: DB 加载（mock CopilotRule row） ──────────────

class TestPromptStoreLoadFromDb:
    def test_load_from_db_normalizes_key(self):
        ps = PromptStore()

        # 构造 mock row 模拟 CopilotRule
        row = MagicMock()
        row.id = 42
        row.scope = "biz"
        row.title = "Daily Report Rule"
        row.content = "每天生成经营日报，关注 Top 3 品类"
        row.priority = 10
        row.created_by = "admin"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [row]

        count = ps.load_from_db(mock_db)
        assert count == 1
        # key 按规则归一化: rule.biz.daily_report_rule
        assert "rule.biz.daily_report_rule" in ps.list_keys()
        tpl = ps.get("rule.biz.daily_report_rule")
        assert tpl.version == "db-42"
        assert tpl.source == "db"
        assert tpl.metadata["title"] == "Daily Report Rule"

    def test_load_from_db_query_fails_gracefully(self):
        ps = PromptStore()
        mock_db = MagicMock()
        mock_db.query.side_effect = Exception("db down")

        count = ps.load_from_db(mock_db)
        assert count == 0


# ── 测试 6: SkillRegistry 加载 ──────────────────────────

class TestPromptStoreLoadFromSkillRegistry:
    def test_load_summarization_hints(self):
        ps = PromptStore()

        skill_a = MagicMock()
        skill_a.summarization_hint = "总结库存数据时请按 SKU 分组"
        skill_a.display_name = "库存分析"

        skill_b = MagicMock()
        skill_b.summarization_hint = ""  # 空 hint 应被跳过
        skill_b.display_name = "空 hint"

        skill_c = MagicMock()
        skill_c.summarization_hint = "预测时要带置信区间"
        skill_c.display_name = "销售预测"

        mock_registry = MagicMock()
        mock_registry.all_skills.return_value = {
            "inventory_skill": skill_a,
            "empty_skill": skill_b,
            "forecast_skill": skill_c,
        }

        count = ps.load_from_skill_registry(mock_registry)
        # skill_b 因 hint 空被跳过
        assert count == 2
        assert "skill.inventory_skill.summarization_hint" in ps.list_keys()
        assert "skill.forecast_skill.summarization_hint" in ps.list_keys()
        assert "skill.empty_skill.summarization_hint" not in ps.list_keys()


# ── 测试 7: summary ──────────────────────────────────────

class TestPromptStoreSummary:
    def test_summary_shape(self):
        ps = PromptStore()
        ps.register(_make_tpl("a", source="yaml:x.yaml"))
        ps.register(_make_tpl("a", version="v2", source="yaml:y.yaml"), set_as_default=False)
        ps.register(_make_tpl("b", source="db"))
        ps.add_gray_rule(GrayscaleRule(key="a", target_version="v2", percent=30))

        summary = ps.summary()
        assert summary["total_keys"] == 2
        assert summary["total_templates"] == 3
        assert summary["by_source"]["yaml"] == 2
        assert summary["by_source"]["db"] == 1
        assert summary["gray_rules"] == 1
