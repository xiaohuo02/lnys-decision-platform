# -*- coding: utf-8 -*-
"""本地端到端检索测试 — 使用 ollama bge-large-zh-v1.5 + 临时 ChromaDB。

用法:
    cd nyshdsjpt
    .venv\\Scripts\\python.exe backend\\tests\\test_e2e_search_local.py

不依赖 MySQL / Docker，直接验证：
  1. ollama embedding → ChromaDB 写入
  2. SearchEngine.search() 全链路
  3. 返回值包含 confidence / suggestion / reranked 等新字段
"""
import sys
import json
import tempfile
import shutil
from pathlib import Path
from typing import List
from unittest.mock import patch, MagicMock

# 让 import backend.* 能正常工作
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import requests
import chromadb

# ═══════════════════════════════════════════════════════════
#  1. Ollama Embedding 适配器
# ═══════════════════════════════════════════════════════════

OLLAMA_BASE = "http://127.0.0.1:11434"
OLLAMA_MODEL = "quentinz/bge-large-zh-v1.5:f16"


def ollama_embed(texts: List[str]) -> List[List[float]]:
    """调用 ollama embeddings API 批量编码。"""
    vectors = []
    for t in texts:
        resp = requests.post(
            f"{OLLAMA_BASE}/api/embeddings",
            json={"model": OLLAMA_MODEL, "prompt": t},
            timeout=30,
        )
        resp.raise_for_status()
        vectors.append(resp.json()["embedding"])
    return vectors


# ═══════════════════════════════════════════════════════════
#  2. 准备测试数据
# ═══════════════════════════════════════════════════════════

FAQ_DATA = [
    {"id": "c1", "title": "退款政策", "content": "用户可在购买后7天内申请全额退款，请联系客服处理。"},
    {"id": "c2", "title": "配送时效", "content": "标准配送3-5个工作日，加急配送1-2个工作日到达。"},
    {"id": "c3", "title": "退货流程", "content": "退货需在签收15日内发起，商品需保持原包装，联系客服获取退货地址。"},
    {"id": "c4", "title": "会员权益", "content": "VIP会员享受9折优惠、免费配送、专属客服等权益。"},
    {"id": "c5", "title": "发票开具", "content": "订单完成后可在个人中心申请电子发票，支持增值税普通发票。"},
    {"id": "c6", "title": "退款到账时间", "content": "退款审核通过后，原路退回，银行卡3-5个工作日到账，支付宝即时到账。"},
]


def main():
    print("=" * 60)
    print("  本地端到端检索测试（ollama embedding）")
    print("=" * 60)

    # 检查 ollama 是否可用
    print("\n[1/5] 检查 ollama 连通性...")
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        if OLLAMA_MODEL not in models:
            print(f"  ✗ 模型 {OLLAMA_MODEL} 不在 ollama 中，可用: {models}")
            return
        print(f"  ✓ ollama 可用，模型 {OLLAMA_MODEL} 已加载")
    except Exception as e:
        print(f"  ✗ ollama 不可用: {e}")
        return

    # 创建临时 ChromaDB
    print("\n[2/5] 创建临时 ChromaDB + 写入测试数据...")
    tmp_dir = tempfile.mkdtemp(prefix="kb_test_chroma_")
    try:
        client = chromadb.PersistentClient(path=tmp_dir)
        col = client.get_or_create_collection(
            name="test_faq_col",
            metadata={"hnsw:space": "cosine"},
        )

        # 向量化并写入
        texts = [d["content"] for d in FAQ_DATA]
        vectors = ollama_embed(texts)
        dim = len(vectors[0])
        print(f"  ✓ embedding 维度: {dim}, 共 {len(vectors)} 条")

        col.add(
            ids=[d["id"] for d in FAQ_DATA],
            documents=texts,
            embeddings=vectors,
            metadatas=[{"title": d["title"], "document_id": f"doc_{d['id']}"} for d in FAQ_DATA],
        )
        print(f"  ✓ ChromaDB collection 写入完成，count={col.count()}")

        # 构造 mock 的 EmbeddingService 和 VectorStoreManager
        print("\n[3/5] 构造 SearchEngine（mock embedding + store）...")

        mock_emb = MagicMock()
        mock_emb.embed_query = lambda q: ollama_embed([q])[0]
        mock_emb.dim = dim

        mock_store = MagicMock()
        mock_store.get_collection = lambda name: col

        # 创建 SearchEngine 实例（绕过单例）
        from backend.knowledge.search_engine import SearchEngine
        engine = object.__new__(SearchEngine)
        engine._embedding = mock_emb
        engine._store = mock_store
        engine._bm25_cache = {}
        engine._reranker = None
        engine._reranker_loaded = True  # 跳过 reranker 加载

        # Mock _resolve_collections 返回我们的测试 collection
        engine._resolve_collections = lambda kb_ids: [
            {"kb_id": "test_kb", "name": "测试FAQ库", "collection_name": "test_faq_col"}
        ]

        print("  ✓ SearchEngine 构造完成")

        # 执行检索测试
        print("\n[4/5] 执行检索测试...")
        test_queries = [
            ("退款怎么办", "预期：高置信，退款相关内容排前"),
            ("配送需要多久", "预期：高置信，配送相关内容"),
            ("量子物理学", "预期：低置信，无相关内容"),
            ("退货退款", "预期：ambiguous可能为True，退款和退货分数接近"),
        ]

        all_pass = True
        for query, desc in test_queries:
            print(f"\n  查询: 「{query}」 ({desc})")
            result = engine.search(query=query, kb_ids=["test_kb"], top_k=3, min_score=0.1, mode="hybrid")

            print(f"    confidence:    {result.get('confidence', 'N/A')}")
            print(f"    conf_score:    {result.get('confidence_score', 'N/A')}")
            print(f"    ambiguous:     {result.get('ambiguous', 'N/A')}")
            print(f"    suggestion:    {result.get('suggestion', 'N/A')}")
            print(f"    search_mode:   {result.get('search_mode', 'N/A')}")
            print(f"    degraded:      {result.get('degraded', 'N/A')}")
            print(f"    total:         {result.get('total', 0)}")
            print(f"    elapsed_ms:    {result.get('elapsed_ms', 0)}")

            if result.get("hits"):
                for i, h in enumerate(result["hits"][:3]):
                    print(f"    hit#{i+1}: [{h['score']:.3f}] {h['title']} — {h['content'][:40]}...")
            else:
                print("    (no hits)")

            # 基本断言
            if "confidence" not in result:
                print("    ✗ 缺少 confidence 字段!")
                all_pass = False
            if "suggestion" not in result:
                print("    ✗ 缺少 suggestion 字段!")
                all_pass = False
            if result["confidence"] not in ("high", "medium", "low", "none"):
                print(f"    ✗ confidence 值异常: {result['confidence']}")
                all_pass = False

        # 汇总
        print("\n" + "=" * 60)
        print(f"[5/5] 测试结果: {'✓ ALL PASS' if all_pass else '✗ SOME FAILED'}")
        print("=" * 60)

        # 打印完整 JSON 示例（最后一个查询）
        print("\n完整返回示例 JSON:")
        safe_result = {k: v for k, v in result.items() if k != "hits"}
        safe_result["hits_count"] = len(result.get("hits", []))
        if result.get("hits"):
            safe_result["first_hit"] = {
                "title": result["hits"][0].get("title"),
                "score": result["hits"][0].get("score"),
                "content_preview": result["hits"][0].get("content", "")[:50],
            }
        print(json.dumps(safe_result, ensure_ascii=False, indent=2))

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print(f"\n临时目录已清理: {tmp_dir}")


if __name__ == "__main__":
    main()
