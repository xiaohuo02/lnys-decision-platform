# -*- coding: utf-8 -*-
"""本地评估运行脚本 — 使用 ollama embedding + 临时 ChromaDB。

用法:
    cd nyshdsjpt
    .venv\\Scripts\\python.exe backend\\knowledge\\eval\\run_eval.py

会自动:
  1. 用 ollama bge-large-zh-v1.5 对 FAQ 语料做 embedding
  2. 写入临时 ChromaDB
  3. 构造 SearchEngine 并执行 test_set.json 中所有查询
  4. 输出 Top1/Top3/MRR 等指标报告
"""
import sys
import json
import tempfile
import shutil
from pathlib import Path
from typing import List
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import requests
import chromadb

# ── 配置 ──────────────────────────────────────
OLLAMA_BASE = "http://127.0.0.1:11434"
OLLAMA_MODEL = "quentinz/bge-large-zh-v1.5:f16"
EVAL_DIR = Path(__file__).parent
TEST_SET_PATH = EVAL_DIR / "test_set.json"

# ── FAQ 语料（与 test_set.json 对应）──────────
FAQ_CORPUS = [
    {"id": "c1", "title": "退款政策", "content": "用户可在购买后7天内申请全额退款，请联系客服处理。"},
    {"id": "c2", "title": "配送时效", "content": "标准配送3-5个工作日，加急配送1-2个工作日到达。"},
    {"id": "c3", "title": "退货流程", "content": "退货需在签收15日内发起，商品需保持原包装，联系客服获取退货地址。"},
    {"id": "c4", "title": "会员权益", "content": "VIP会员享受9折优惠、免费配送、专属客服等权益。"},
    {"id": "c5", "title": "发票开具", "content": "订单完成后可在个人中心申请电子发票，支持增值税普通发票。"},
    {"id": "c6", "title": "退款到账时间", "content": "退款审核通过后，原路退回，银行卡3-5个工作日到账，支付宝即时到账。"},
    {"id": "c7", "title": "退款流程", "content": "申请退款后，客服将在1个工作日内审核，审核通过后退款将原路退回。"},
]


def ollama_embed(texts: List[str]) -> List[List[float]]:
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


def main():
    print("=" * 60)
    print("  检索质量评估 (ollama + ChromaDB)")
    print("=" * 60)

    # 检查 ollama
    print("\n[1/4] 检查 ollama...")
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
        models = [m["name"] for m in r.json().get("models", [])]
        if OLLAMA_MODEL not in models:
            print(f"  ✗ 模型 {OLLAMA_MODEL} 不在 ollama 中")
            return
        print(f"  ✓ 模型就绪")
    except Exception as e:
        print(f"  ✗ ollama 不可用: {e}")
        return

    # 准备 ChromaDB + 索引
    print("\n[2/4] 构建索引...")
    tmp_dir = tempfile.mkdtemp(prefix="kb_eval_")
    try:
        client = chromadb.PersistentClient(path=tmp_dir)
        col = client.get_or_create_collection("eval_faq", metadata={"hnsw:space": "cosine"})

        texts = [d["content"] for d in FAQ_CORPUS]
        vectors = ollama_embed(texts)
        print(f"  ✓ {len(vectors)} 条文档已向量化 (dim={len(vectors[0])})")

        col.add(
            ids=[d["id"] for d in FAQ_CORPUS],
            documents=texts,
            embeddings=vectors,
            metadatas=[{"title": d["title"], "document_id": f"doc_{d['id']}"} for d in FAQ_CORPUS],
        )

        # 构造 SearchEngine
        print("\n[3/4] 构造 SearchEngine...")
        from backend.knowledge.search_engine import SearchEngine

        mock_emb = MagicMock()
        mock_emb.embed_query = lambda q: ollama_embed([q])[0]

        mock_store = MagicMock()
        mock_store.get_collection = lambda name: col

        engine = object.__new__(SearchEngine)
        engine._embedding = mock_emb
        engine._store = mock_store
        engine._bm25_cache = {}
        engine._reranker = None
        engine._reranker_loaded = True
        engine._resolve_collections = lambda kb_ids: [
            {"kb_id": "eval_kb", "name": "评估FAQ库", "collection_name": "eval_faq"}
        ]

        # 执行评估
        print("\n[4/4] 执行评估...")
        from backend.knowledge.eval.evaluator import SearchEvaluator

        def search_fn(query, top_k=5):
            return engine.search(query=query, top_k=top_k, min_score=0.1, mode="hybrid")

        evaluator = SearchEvaluator(search_fn=search_fn)
        report = evaluator.run(TEST_SET_PATH, top_k=5)
        evaluator.print_report(report)

        # 保存 JSON 报告
        report_path = EVAL_DIR / "eval_report.json"
        safe_report = {k: v for k, v in report.items() if k != "details"}
        safe_report["details_count"] = len(report.get("details", []))
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n  完整报告已保存: {report_path}")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
