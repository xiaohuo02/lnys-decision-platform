# -*- coding: utf-8 -*-
"""测试检索引擎：低置信度策略 + Rerank + schemas 新字段。

不依赖 ChromaDB/MySQL/Embedding 外部服务，直接测试内部纯函数。
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


# ═══════════════════════════════════════════════════════════
#  1. _analyze_confidence 置信度分析
# ═══════════════════════════════════════════════════════════

from backend.knowledge.search_engine import SearchEngine

# 构造一个类似 settings 的 mock 对象（v2 §2.2 新阈值）
_MOCK_SETTINGS = SimpleNamespace(
    KB_CONFIDENCE_HIGH=0.72,
    KB_CONFIDENCE_MEDIUM=0.55,
    KB_CONFIDENCE_LOW=0.35,
    KB_AMBIGUOUS_GAP=0.08,
    KB_DEGRADED_CONF_PENALTY=0.15,
)


class TestAnalyzeConfidence:
    """直接测试静态方法 _analyze_confidence（v2）。"""

    def test_empty_hits(self):
        r = SearchEngine._analyze_confidence([], _MOCK_SETTINGS)
        assert r["confidence"] == "none"
        assert r["suggestion"] == "transfer_human"
        assert r["ambiguous"] is False
        assert r["ambiguous_reason"] is None
        assert r["confidence_score"] == 0.0

    def test_high_confidence_single_hit(self):
        hits = [{"score": 0.85}]
        r = SearchEngine._analyze_confidence(hits, _MOCK_SETTINGS)
        assert r["confidence"] == "high"
        assert r["suggestion"] == "direct_answer"
        assert r["ambiguous"] is False
        assert r["ambiguous_reason"] is None

    def test_high_confidence_clear_gap(self):
        hits = [{"score": 0.90}, {"score": 0.60}]
        r = SearchEngine._analyze_confidence(hits, _MOCK_SETTINGS)
        assert r["confidence"] == "high"
        assert r["suggestion"] == "direct_answer"
        assert r["ambiguous"] is False

    def test_high_score_but_ambiguous_same_kb(self):
        """gap < AMBIGUOUS_GAP 且同 kb → confidence=ambiguous, reason=small_gap。"""
        hits = [{"score": 0.80, "kb_id": "kb_a"}, {"score": 0.78, "kb_id": "kb_a"}]
        r = SearchEngine._analyze_confidence(hits, _MOCK_SETTINGS)
        assert r["confidence"] == "ambiguous"
        assert r["suggestion"] == "disambiguate"
        assert r["ambiguous"] is True
        assert r["ambiguous_reason"] == "small_gap"

    def test_ambiguous_cross_kb_tie(self):
        """gap < AMBIGUOUS_GAP 且跨 kb → confidence=ambiguous, reason=cross_kb_tie。"""
        hits = [{"score": 0.80, "kb_id": "kb_a"}, {"score": 0.76, "kb_id": "kb_b"}]
        r = SearchEngine._analyze_confidence(hits, _MOCK_SETTINGS)
        assert r["confidence"] == "ambiguous"
        assert r["ambiguous"] is True
        assert r["ambiguous_reason"] == "cross_kb_tie"

    def test_medium_confidence(self):
        hits = [{"score": 0.60}, {"score": 0.30}]
        r = SearchEngine._analyze_confidence(hits, _MOCK_SETTINGS)
        assert r["confidence"] == "medium"
        assert r["suggestion"] == "show_candidates"

    def test_low_confidence(self):
        hits = [{"score": 0.40}, {"score": 0.10}]
        r = SearchEngine._analyze_confidence(hits, _MOCK_SETTINGS)
        assert r["confidence"] == "low"
        assert r["suggestion"] == "fallback_faq"

    def test_none_below_low(self):
        """score < KB_CONFIDENCE_LOW → confidence=none（新档）。"""
        hits = [{"score": 0.20}]
        r = SearchEngine._analyze_confidence(hits, _MOCK_SETTINGS)
        assert r["confidence"] == "none"
        assert r["suggestion"] == "transfer_human"

    def test_degraded_penalty_demotes_high_to_medium(self):
        """degraded=True 扣 0.15 → 0.85 - 0.15 = 0.70 < 0.72(HIGH) → medium。"""
        hits = [{"score": 0.85}]
        r = SearchEngine._analyze_confidence(hits, _MOCK_SETTINGS, degraded=True)
        assert r["confidence"] == "medium"
        assert r["confidence_score"] == 0.70

    def test_degraded_penalty_demotes_medium_to_low(self):
        """degraded=True 且 top1=0.60 → 0.60-0.15=0.45 < 0.55(MEDIUM) → low。"""
        hits = [{"score": 0.60}]
        r = SearchEngine._analyze_confidence(hits, _MOCK_SETTINGS, degraded=True)
        assert r["confidence"] == "low"

    def test_rerank_score_preferred(self):
        hits = [{"score": 0.40, "rerank_score": 0.90}, {"score": 0.35, "rerank_score": 0.50}]
        r = SearchEngine._analyze_confidence(hits, _MOCK_SETTINGS)
        assert r["confidence"] == "high"
        assert r["confidence_score"] == 0.90

    def test_boundary_exactly_high(self):
        hits = [{"score": 0.72}]
        r = SearchEngine._analyze_confidence(hits, _MOCK_SETTINGS)
        assert r["confidence"] == "high"

    def test_boundary_exactly_medium(self):
        hits = [{"score": 0.55}]
        r = SearchEngine._analyze_confidence(hits, _MOCK_SETTINGS)
        assert r["confidence"] == "medium"

    def test_boundary_exactly_low(self):
        hits = [{"score": 0.35}]
        r = SearchEngine._analyze_confidence(hits, _MOCK_SETTINGS)
        assert r["confidence"] == "low"

    def test_boundary_below_low_is_none(self):
        hits = [{"score": 0.34}]
        r = SearchEngine._analyze_confidence(hits, _MOCK_SETTINGS)
        assert r["confidence"] == "none"


# ═══════════════════════════════════════════════════════════
#  2. SearchResponse schema 新字段
# ═══════════════════════════════════════════════════════════

from backend.knowledge.schemas import SearchResponse


class TestSearchResponseSchema:
    def test_default_fields(self):
        resp = SearchResponse(query="test")
        assert resp.confidence == "none"
        assert resp.confidence_score == 0.0
        assert resp.ambiguous is False
        assert resp.ambiguous_reason is None
        assert resp.suggestion == "transfer_human"
        assert resp.reranked is False

    def test_populate_confidence(self):
        resp = SearchResponse(
            query="test", confidence="high",
            confidence_score=0.88, ambiguous=False,
            suggestion="direct_answer", reranked=True,
        )
        assert resp.confidence == "high"
        assert resp.confidence_score == 0.88
        assert resp.reranked is True

    def test_serialize(self):
        resp = SearchResponse(query="q", confidence="low", suggestion="fallback_faq")
        d = resp.model_dump()
        assert "confidence" in d
        assert "suggestion" in d
        assert "reranked" in d


# ═══════════════════════════════════════════════════════════
#  3. _rerank 方法（无模型时 fallback）
# ═══════════════════════════════════════════════════════════

class TestRerankFallback:
    def test_rerank_without_model_returns_original(self):
        engine = object.__new__(SearchEngine)
        engine._reranker = None
        engine._reranker_loaded = True

        hits = [{"content": "a", "score": 0.8}, {"content": "b", "score": 0.6}]
        result = engine._rerank("query", hits, top_n=5)
        assert result == hits

    def test_rerank_empty_hits(self):
        engine = object.__new__(SearchEngine)
        engine._reranker = None
        engine._reranker_loaded = True

        result = engine._rerank("query", [], top_n=5)
        assert result == []


# ═══════════════════════════════════════════════════════════
#  4. RRF 融合回归
# ═══════════════════════════════════════════════════════════

class TestRRFMerge:
    def test_basic_merge(self):
        a = [{"chunk_id": "c1", "score": 0.9}, {"chunk_id": "c2", "score": 0.7}]
        b = [{"chunk_id": "c2", "score": 0.8}, {"chunk_id": "c3", "score": 0.6}]
        result = SearchEngine._rrf_merge(a, b, top_k=3)
        assert len(result) == 3
        ids = [r["chunk_id"] for r in result]
        assert "c2" in ids

    def test_merge_deduplication(self):
        a = [{"chunk_id": "c1", "score": 0.9}]
        b = [{"chunk_id": "c1", "score": 0.8}]
        result = SearchEngine._rrf_merge(a, b, top_k=5)
        assert len(result) == 1
        assert result[0]["search_mode"] == "hybrid"

    def test_same_kb_bonus_applied(self):
        """§2.2 B：top_k 候选全同 kb_id → score * 1.1。"""
        a = [{"chunk_id": "c1", "kb_id": "kb_a", "score": 0.9}]
        b = [{"chunk_id": "c2", "kb_id": "kb_a", "score": 0.8}]
        result = SearchEngine._rrf_merge(a, b, top_k=2)
        assert len(result) == 2
        assert result[0]["rrf_score"] == pytest.approx(0.0164, abs=1e-3)
        assert result[0]["score"] == pytest.approx(0.99, abs=1e-3)

    def test_cross_kb_no_bonus(self):
        """§2.2 B：top_k 跨 kb_id → 不加 bonus（保持原相关性分数）。"""
        a = [{"chunk_id": "c1", "kb_id": "kb_a", "score": 0.9}]
        b = [{"chunk_id": "c2", "kb_id": "kb_b", "score": 0.8}]
        result = SearchEngine._rrf_merge(a, b, top_k=2)
        assert len(result) == 2
        assert result[0]["rrf_score"] == pytest.approx(0.0164, abs=1e-3)
        assert result[0]["score"] == pytest.approx(0.9, abs=1e-3)


# ═══════════════════════════════════════════════════════════
#  5. Query term overlap guard
# ═══════════════════════════════════════════════════════════

class TestQueryTermOverlap:
    def test_out_of_scope_stock_code_has_no_overlap(self):
        hits = [
            {
                "title": "数据安全与隐私保护政策",
                "content": "平台采用 AES-256 加密保护用户手机号、地址和订单信息。",
            }
        ]
        assert SearchEngine._has_query_term_overlap("我们公司的股票代码是多少", hits) is False

    def test_refund_question_keeps_overlap(self):
        hits = [
            {
                "title": "退款政策完整说明",
                "content": "微信支付和支付宝审核通过后 1-3 个工作日到账。",
            }
        ]
        assert SearchEngine._has_query_term_overlap("退款多久能到账", hits) is True


# ═══════════════════════════════════════════════════════════
#  6. chunk_engine: FAQ 快速路径 + 列表检测
# ═══════════════════════════════════════════════════════════

from backend.knowledge.chunk_engine import chunk_text, _detect_list, _estimate_tokens


class TestChunkFAQFastPath:
    def test_short_faq_not_split(self):
        text = "用户可在购买后7天内申请全额退款，请联系客服处理。"
        chunks = chunk_text(text, strategy="recursive", max_tokens=512)
        assert len(chunks) == 1
        assert chunks[0].content == text

    def test_short_qa_pair_not_split(self):
        text = "Q: 怎么退款？\nA: 用户可在购买后7天内申请全额退款。"
        chunks = chunk_text(text, strategy="recursive", max_tokens=512)
        assert len(chunks) == 1

    def test_long_text_still_splits(self):
        text = "这是一段很长的文本。" * 500
        chunks = chunk_text(text, strategy="recursive", max_tokens=128)
        assert len(chunks) > 1


class TestDetectList:
    def test_unordered_list(self):
        text = "- 苹果\n- 香蕉\n- 橙子"
        assert _detect_list(text) is True

    def test_ordered_list(self):
        text = "1. 第一步\n2. 第二步\n3. 第三步"
        assert _detect_list(text) is True

    def test_chinese_ordered_list(self):
        text = "1、退款\n2、退货\n3、换货"
        assert _detect_list(text) is True

    def test_bullet_list(self):
        text = "• 功能A\n• 功能B\n• 功能C"
        assert _detect_list(text) is True

    def test_non_list(self):
        text = "这是普通文本。\n没有列表格式。"
        assert _detect_list(text) is False

    def test_single_line_not_list(self):
        text = "- 只有一行"
        assert _detect_list(text) is False

    def test_list_chunk_preserved(self):
        text = "标题\n\n- 项目A\n- 项目B\n- 项目C"
        chunks = chunk_text(text, strategy="recursive", max_tokens=512)
        has_list = any(c.chunk_type == "list" for c in chunks)
        assert has_list or len(chunks) == 1


class _Row:
    def __init__(self, mapping):
        self._mapping = mapping


class _StubResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _StubSession:
    def __init__(self, rows, raise_on_execute=False):
        self._rows = rows
        self._raise = raise_on_execute

    def execute(self, *args, **kwargs):
        if self._raise:
            raise RuntimeError("simulated db error")
        return _StubResult(self._rows)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def _patch_session_local(monkeypatch, rows, raise_on_execute=False):
    import backend.database as database_mod

    def _factory():
        return _StubSession(rows, raise_on_execute=raise_on_execute)

    monkeypatch.setattr(database_mod, "SessionLocal", _factory, raising=True)


def _make_engine():
    engine = object.__new__(SearchEngine)
    engine._embedding = None
    engine._store = None
    engine._bm25_cache = {}
    engine._reranker = None
    engine._reranker_loaded = True
    return engine


class TestLoadChunksFromMySQL:
    def test_basic_rows_mapped(self, monkeypatch):
        rows = [
            _Row({
                "chunk_id": "c1", "chromadb_id": "doc1__0",
                "document_id": "doc1", "kb_id": "kb_a",
                "content": "退款政策：1-3 个工作日到账",
                "heading_path": "退款 / 时效", "chunk_type": "paragraph",
                "title": "退款政策完整说明",
            }),
            _Row({
                "chunk_id": "c2", "chromadb_id": "doc1__1",
                "document_id": "doc1", "kb_id": "kb_a",
                "content": "支持微信和支付宝原路退回",
                "heading_path": "退款 / 渠道", "chunk_type": "paragraph",
                "title": "退款政策完整说明",
            }),
        ]
        _patch_session_local(monkeypatch, rows)
        docs, metas, ids = SearchEngine._load_chunks_from_mysql("kb_a")
        assert docs == [
            "退款政策：1-3 个工作日到账",
            "支持微信和支付宝原路退回",
        ]
        assert ids == ["doc1__0", "doc1__1"]
        assert metas[0]["title"] == "退款政策完整说明"
        assert metas[0]["kb_id"] == "kb_a"
        assert metas[0]["heading_path"] == "退款 / 时效"

    def test_empty_content_filtered(self, monkeypatch):
        rows = [
            _Row({
                "chunk_id": "c1", "chromadb_id": "doc1__0",
                "document_id": "doc1", "kb_id": "kb_a",
                "content": "", "heading_path": "", "chunk_type": "paragraph",
                "title": "空内容",
            }),
            _Row({
                "chunk_id": "c2", "chromadb_id": "doc1__1",
                "document_id": "doc1", "kb_id": "kb_a",
                "content": "有效内容", "heading_path": "", "chunk_type": "paragraph",
                "title": "正常",
            }),
        ]
        _patch_session_local(monkeypatch, rows)
        docs, _metas, ids = SearchEngine._load_chunks_from_mysql("kb_a")
        assert docs == ["有效内容"]
        assert ids == ["doc1__1"]

    def test_db_error_returns_empty(self, monkeypatch):
        _patch_session_local(monkeypatch, [], raise_on_execute=True)
        assert SearchEngine._load_chunks_from_mysql("kb_a") == ([], [], [])

    def test_chromadb_id_missing_falls_back_to_chunk_id(self, monkeypatch):
        rows = [
            _Row({
                "chunk_id": "c1", "chromadb_id": None,
                "document_id": "doc1", "kb_id": "kb_a",
                "content": "无 chromadb_id 的 chunk", "heading_path": "",
                "chunk_type": "paragraph", "title": "legacy",
            }),
        ]
        _patch_session_local(monkeypatch, rows)
        _docs, _metas, ids = SearchEngine._load_chunks_from_mysql("kb_a")
        assert ids == ["c1"]


class TestGetBM25Index:
    """§2.1 Layer 3：MySQL 优先 / Chroma fallback / cache 命中。"""

    def test_mysql_first_no_chroma_call(self, monkeypatch):
        pytest.importorskip("jieba")
        pytest.importorskip("rank_bm25")
        rows = [
            _Row({
                "chunk_id": "c1", "chromadb_id": "doc1__0",
                "document_id": "doc1", "kb_id": "kb_a",
                "content": "退款政策内容", "heading_path": "",
                "chunk_type": "paragraph", "title": "退款",
            }),
        ]
        _patch_session_local(monkeypatch, rows)

        engine = _make_engine()
        store_called = {"hit": False}

        def _no_store():
            store_called["hit"] = True
            raise AssertionError("Chroma fallback should not be triggered when MySQL has data")

        engine._get_store = _no_store  # type: ignore

        from backend.config import settings
        monkeypatch.setattr(settings, "KB_BM25_CACHE_SIZE", 5, raising=False)

        idx = engine._get_bm25_index("kb_a", fallback_collection="kb_enterprise_faq")
        assert idx is not None
        bm25, docs, metas, ids = idx
        assert ids == ["doc1__0"]
        assert docs == ["退款政策内容"]
        assert store_called["hit"] is False
        # 二次调用走 cache 不再查 MySQL
        idx2 = engine._get_bm25_index("kb_a", fallback_collection="kb_enterprise_faq")
        assert idx2 is idx

    def test_chroma_fallback_when_mysql_empty(self, monkeypatch):
        pytest.importorskip("jieba")
        pytest.importorskip("rank_bm25")
        _patch_session_local(monkeypatch, [])

        class _StubCol:
            def count(self):
                return 1

            def get(self, include=None):
                return {
                    "ids": ["legacy_id_1"],
                    "documents": ["legacy 内容来自 chroma"],
                    "metadatas": [{"document_id": "d1", "title": "Legacy"}],
                }

        class _StubStore:
            def get_collection(self, name):
                return _StubCol()

        engine = _make_engine()
        engine._get_store = lambda: _StubStore()  # type: ignore

        from backend.config import settings
        monkeypatch.setattr(settings, "KB_BM25_CACHE_SIZE", 5, raising=False)

        idx = engine._get_bm25_index("kb_legacy", fallback_collection="kb_legacy_col")
        assert idx is not None
        _bm25, docs, _metas, ids = idx
        assert ids == ["legacy_id_1"]
        assert docs == ["legacy 内容来自 chroma"]

    def test_returns_none_when_both_sources_empty(self, monkeypatch):
        _patch_session_local(monkeypatch, [])
        engine = _make_engine()
        engine._get_store = lambda: None  # type: ignore

        from backend.config import settings
        monkeypatch.setattr(settings, "KB_BM25_CACHE_SIZE", 5, raising=False)

        assert engine._get_bm25_index("kb_x", fallback_collection=None) is None
        assert engine._get_bm25_index("kb_x", fallback_collection="not_exist") is None

    def test_empty_kb_id_returns_none(self):
        engine = _make_engine()
        assert engine._get_bm25_index("", fallback_collection=None) is None
        assert engine._get_bm25_index(None, fallback_collection=None) is None  # type: ignore[arg-type]


class TestInvalidateBM25Cache:
    def test_invalidate_specific_kb(self):
        engine = _make_engine()
        engine._bm25_cache = {"kb_a": "idx_a", "kb_b": "idx_b"}
        engine.invalidate_bm25_cache("kb_a")
        assert "kb_a" not in engine._bm25_cache
        assert engine._bm25_cache["kb_b"] == "idx_b"

    def test_invalidate_all_when_none(self):
        engine = _make_engine()
        engine._bm25_cache = {"kb_a": "idx_a", "kb_b": "idx_b"}
        engine.invalidate_bm25_cache(None)
        assert engine._bm25_cache == {}

    def test_invalidate_unknown_kb_is_noop(self):
        engine = _make_engine()
        engine._bm25_cache = {"kb_a": "idx_a"}
        engine.invalidate_bm25_cache("kb_not_exist")
        assert engine._bm25_cache == {"kb_a": "idx_a"}
