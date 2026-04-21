# -*- coding: utf-8 -*-
"""backend/tests/test_knowledge_abstain.py — §3.2 Abstain 单元测试

覆盖 should_abstain() + build_abstain() 四场景 + 边界：
  1. KB_ABSTAIN_ENABLED=False → 永不拒答
  2. no_evidence (hits=[])
  3. low_confidence
  4. none 档（confidence=none 且 hits 非空）
  5. ambiguous
  6. high / medium → 不拒答
  7. domain_forbidden（全部越权）
  8. 部分越权（存在允许 domain）→ 不触发 domain_forbidden
  9. 无 allowed_domains 参数时不做越权检查
 10. build_abstain 未知 reason 抛错
 11. _to_options 字段完整性
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.knowledge.abstain import (  # noqa: E402
    ABSTAIN_REASONS,
    build_abstain,
    should_abstain,
    _to_options,
    _default_fallback_suggestions,
)


# ════════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════════

def _make_settings(**overrides):
    """构造 mock settings：默认启用 abstain 且候选数=3。"""
    base = {
        "KB_ABSTAIN_ENABLED": True,
        "KB_ABSTAIN_FALLBACK_SUGGEST_COUNT": 3,
        "KB_ABSTAIN_MSG_NO_EVIDENCE": "无证据文案",
        "KB_ABSTAIN_MSG_LOW_CONFIDENCE": "低置信文案",
        "KB_ABSTAIN_MSG_AMBIGUOUS": "歧义文案",
        "KB_ABSTAIN_MSG_DOMAIN_FORBIDDEN": "越权文案",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_hit(**overrides):
    """构造单个 SearchEngine hit。"""
    base = {
        "chunk_id": "c1",
        "document_id": "d1",
        "kb_id": "kb_a",
        "kb_name": "企业库A",
        "kb_domain": "enterprise",
        "title": "标题 A",
        "content": "这是一段测试内容。" * 5,
        "score": 0.85,
    }
    base.update(overrides)
    return base


def _make_result(**overrides):
    """构造 SearchEngine.search() 返回 dict。"""
    base = {
        "query": "测试",
        "hits": [],
        "total": 0,
        "search_mode": "hybrid",
        "degraded": False,
        "confidence": "none",
        "confidence_score": 0.0,
        "ambiguous": False,
        "ambiguous_reason": None,
        "suggestion": "transfer_human",
    }
    base.update(overrides)
    return base


# ════════════════════════════════════════════════════════════════════
# Tests
# ════════════════════════════════════════════════════════════════════

class TestShouldAbstain:
    """should_abstain() 主判定函数测试。"""

    def test_disabled_returns_none(self):
        """KB_ABSTAIN_ENABLED=False 时不拒答任何场景。"""
        cfg = _make_settings(KB_ABSTAIN_ENABLED=False)
        result = _make_result(hits=[], confidence="none")
        assert should_abstain(result, settings=cfg) is None

    def test_no_evidence_triggers_abstain(self):
        """场景 1：hits=[] → reason=no_evidence。"""
        cfg = _make_settings()
        result = _make_result(hits=[], confidence="none")
        payload = should_abstain(result, settings=cfg)
        assert payload is not None
        assert payload["reason"] == "no_evidence"
        assert payload["message"] == "无证据文案"
        assert payload["candidates"] == []
        assert payload["disambiguate_options"] == []
        assert payload["abstain"] is True
        assert len(payload["suggestions"]) >= 2

    def test_low_confidence_triggers_with_candidates(self):
        """场景 2a：confidence=low → reason=low_confidence + 候选。"""
        cfg = _make_settings()
        hits = [
            _make_hit(chunk_id="c1", title="低分候选 1", score=0.40),
            _make_hit(chunk_id="c2", title="低分候选 2", score=0.38),
            _make_hit(chunk_id="c3", title="低分候选 3", score=0.36),
            _make_hit(chunk_id="c4", title="低分候选 4", score=0.34),
        ]
        result = _make_result(hits=hits, confidence="low", confidence_score=0.40)
        payload = should_abstain(result, settings=cfg)
        assert payload is not None
        assert payload["reason"] == "low_confidence"
        # 候选数量受 KB_ABSTAIN_FALLBACK_SUGGEST_COUNT 控制
        assert len(payload["candidates"]) == 3
        assert payload["candidates"][0]["title"] == "低分候选 1"
        assert payload["disambiguate_options"] == []
        assert payload["confidence"] == "low"

    def test_none_with_hits_triggers_low_confidence(self):
        """场景 2b：confidence=none 且 hits 非空（罕见）→ 同 low_confidence。"""
        cfg = _make_settings()
        hits = [_make_hit(score=0.20)]
        result = _make_result(hits=hits, confidence="none", confidence_score=0.20)
        payload = should_abstain(result, settings=cfg)
        assert payload is not None
        assert payload["reason"] == "low_confidence"
        assert len(payload["candidates"]) == 1

    def test_ambiguous_triggers_with_disambiguate_options(self):
        """场景 3：confidence=ambiguous → reason=ambiguous + disambiguate_options。"""
        cfg = _make_settings()
        hits = [
            _make_hit(chunk_id="c1", kb_id="kb_a", title="方向 A", score=0.80),
            _make_hit(chunk_id="c2", kb_id="kb_b", title="方向 B", score=0.76),
        ]
        result = _make_result(
            hits=hits, confidence="ambiguous",
            confidence_score=0.80, ambiguous_reason="cross_kb_tie",
        )
        payload = should_abstain(result, settings=cfg)
        assert payload is not None
        assert payload["reason"] == "ambiguous"
        assert len(payload["disambiguate_options"]) == 2
        assert payload["disambiguate_options"][0]["title"] == "方向 A"
        assert payload["candidates"] == []
        assert payload["ambiguous_reason"] == "cross_kb_tie"

    def test_high_confidence_does_not_abstain(self):
        """场景反：confidence=high → None。"""
        cfg = _make_settings()
        hits = [_make_hit(score=0.90)]
        result = _make_result(hits=hits, confidence="high", confidence_score=0.90)
        assert should_abstain(result, settings=cfg) is None

    def test_medium_confidence_does_not_abstain(self):
        """场景反：confidence=medium → None。"""
        cfg = _make_settings()
        hits = [_make_hit(score=0.60)]
        result = _make_result(hits=hits, confidence="medium", confidence_score=0.60)
        assert should_abstain(result, settings=cfg) is None

    def test_domain_forbidden_all_hits_blocked(self):
        """场景 4：所有 hits 的 kb_domain 都不在 allowed_domains → domain_forbidden。"""
        cfg = _make_settings()
        hits = [
            _make_hit(kb_domain="ops", title="运维手册"),
            _make_hit(kb_domain="sentiment", title="舆情数据"),
        ]
        result = _make_result(hits=hits, confidence="high", confidence_score=0.85)
        payload = should_abstain(
            result, allowed_domains={"enterprise"}, settings=cfg,
        )
        assert payload is not None
        assert payload["reason"] == "domain_forbidden"
        assert payload["message"] == "越权文案"

    def test_partial_forbidden_does_not_trigger_domain_abstain(self):
        """允许集合覆盖了至少 1 个 hit 时，不触发 domain_forbidden，继续按 confidence 判。"""
        cfg = _make_settings()
        hits = [
            _make_hit(kb_domain="enterprise", title="企业 hit"),
            _make_hit(kb_domain="ops", title="运维 hit（越权）"),
        ]
        result = _make_result(hits=hits, confidence="high", confidence_score=0.85)
        payload = should_abstain(
            result, allowed_domains={"enterprise"}, settings=cfg,
        )
        # high 置信 + 存在允许 domain → 不拒答
        assert payload is None

    def test_allowed_domains_none_skips_domain_check(self):
        """allowed_domains=None 时完全不做 domain 校验。"""
        cfg = _make_settings()
        hits = [_make_hit(kb_domain="ops", title="运维 hit")]
        result = _make_result(hits=hits, confidence="high", confidence_score=0.85)
        # allowed_domains 不传 → 即使 domain 不匹配也不拒答
        assert should_abstain(result, settings=cfg) is None

    def test_ambiguous_takes_priority_over_low(self):
        """ambiguous 优先级高于 low：同时满足时按 ambiguous 处理。"""
        cfg = _make_settings()
        hits = [_make_hit(score=0.40), _make_hit(chunk_id="c2", score=0.38)]
        # confidence="ambiguous" 由 SearchEngine 决定，即使 score 落在 low 区段
        result = _make_result(
            hits=hits, confidence="ambiguous", confidence_score=0.40,
            ambiguous_reason="small_gap",
        )
        payload = should_abstain(result, settings=cfg)
        assert payload is not None
        assert payload["reason"] == "ambiguous"

    def test_candidates_respect_suggest_count(self):
        """候选数量严格受 KB_ABSTAIN_FALLBACK_SUGGEST_COUNT 控制。"""
        cfg = _make_settings(KB_ABSTAIN_FALLBACK_SUGGEST_COUNT=2)
        hits = [_make_hit(chunk_id=f"c{i}", score=0.30) for i in range(5)]
        result = _make_result(hits=hits, confidence="low", confidence_score=0.30)
        payload = should_abstain(result, settings=cfg)
        assert payload is not None
        assert len(payload["candidates"]) == 2


class TestBuildAbstain:
    """build_abstain() 通用构造器测试。"""

    def test_valid_reason_ok(self):
        payload = build_abstain(
            reason="no_evidence",
            message="msg",
            candidates=[{"title": "t", "score": 0.1}],
        )
        assert payload["abstain"] is True
        assert payload["reason"] == "no_evidence"
        assert payload["candidates"] == [{"title": "t", "score": 0.1}]
        assert isinstance(payload["suggestions"], list)

    def test_unknown_reason_raises(self):
        with pytest.raises(ValueError):
            build_abstain(reason="xxxx_unknown", message="m")

    def test_all_known_reasons_accepted(self):
        """ABSTAIN_REASONS 里枚举的所有原因都可构造成功。"""
        for reason in ABSTAIN_REASONS:
            payload = build_abstain(reason=reason, message="m")
            assert payload["reason"] == reason
            assert payload["abstain"] is True

    def test_partial_answer_propagated(self):
        """§3.1 Grounding 场景：ungrounded_llm_output 时可挂 partial_answer。"""
        payload = build_abstain(
            reason="ungrounded_llm_output",
            message="部分答复",
            partial_answer="这是核实过的部分。",
        )
        assert payload["partial_answer"] == "这是核实过的部分。"

    def test_extra_merged(self):
        payload = build_abstain(
            reason="no_evidence", message="m",
            extra={"trace_id": "t-1"},
        )
        assert payload["trace_id"] == "t-1"


class TestToOptions:
    """_to_options 字段完整性测试。"""

    def test_full_fields(self):
        hits = [_make_hit(content="x" * 200, score=0.5)]
        opts = _to_options(hits)
        assert len(opts) == 1
        o = opts[0]
        # 必须有 title/kb_id/kb_name/kb_domain/document_id/score/snippet
        for key in ("title", "kb_id", "kb_name", "kb_domain",
                    "document_id", "score", "snippet"):
            assert key in o
        # snippet 截断到 160
        assert len(o["snippet"]) <= 160

    def test_prefers_rerank_score(self):
        hits = [_make_hit(score=0.4, rerank_score=0.9)]
        opts = _to_options(hits)
        assert opts[0]["score"] == 0.9

    def test_empty_hits(self):
        assert _to_options([]) == []


class TestDefaultFallbackSuggestions:
    """_default_fallback_suggestions 场景映射测试。"""

    def test_base_always_present(self):
        for reason in ABSTAIN_REASONS:
            sugs = _default_fallback_suggestions(reason)
            labels = [s["label"] for s in sugs]
            assert "换个问法重新提问" in labels
            assert "浏览知识库目录" in labels

    def test_no_evidence_has_contact_admin(self):
        labels = [s["label"] for s in _default_fallback_suggestions("no_evidence")]
        assert "联系知识库管理员补充资料" in labels

    def test_unknown_reason_returns_base_only(self):
        sugs = _default_fallback_suggestions("__non_existent__")
        assert len(sugs) == 2  # 只有 base 两项


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
