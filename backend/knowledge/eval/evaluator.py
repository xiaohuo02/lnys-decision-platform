# -*- coding: utf-8 -*-
"""backend/knowledge/eval/evaluator.py — 检索质量评估器

自动化评估指标：
  - Top1 命中率：top1 结果的标题在 expected_doc_titles 中
  - Top3 命中率：top3 中任一标题命中
  - MRR (Mean Reciprocal Rank)：首次命中的排名倒数的均值
  - 无结果率：返回 0 条命中的比例
  - 错误命中率：top1 标题不在 expected 且 expected 非空的比例
  - 关键词覆盖率：top1 content 中包含 expected_keywords 的比例

用法:
    from backend.knowledge.eval.evaluator import SearchEvaluator
    ev = SearchEvaluator(search_fn=my_search)
    report = ev.run("backend/knowledge/eval/test_set.json")
    ev.print_report(report)
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from loguru import logger


class SearchEvaluator:
    """检索质量评估器。

    Args:
        search_fn: 签名 (query, top_k) -> dict，返回 SearchEngine.search() 格式。
    """

    def __init__(self, search_fn: Callable[..., Dict[str, Any]]):
        self._search = search_fn

    def run(
        self,
        test_set_path: str | Path,
        top_k: int = 5,
        default_min_score: float = 0.3,
        default_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """执行评估，返回报告字典。

        case 中可携带可选字段（按需覆盖 search_fn 默认值）：
          - kb_ids: 限定检索的知识库 ID 列表
          - min_score: 该用例的 min_score 阈值
          - mode: 该用例的 search_mode（hybrid/vector/keyword）
        """
        test_set_path = Path(test_set_path)
        with open(test_set_path, "r", encoding="utf-8") as f:
            cases = json.load(f)

        results = []
        t0 = time.time()

        for case in cases:
            qid = case["id"]
            query = case["query"]
            expected_titles = [t.lower() for t in case.get("expected_doc_titles", [])]
            expected_kw = case.get("expected_keywords", [])
            expect_no_hit = case.get("expect_no_hit", False)

            search_kwargs: Dict[str, Any] = {"query": query, "top_k": top_k}
            if case.get("kb_ids"):
                search_kwargs["kb_ids"] = case["kb_ids"]
            if "min_score" in case:
                search_kwargs["min_score"] = case["min_score"]
            elif default_min_score is not None:
                search_kwargs["min_score"] = default_min_score
            if case.get("mode"):
                search_kwargs["mode"] = case["mode"]
            elif default_mode:
                search_kwargs["mode"] = default_mode

            try:
                resp = self._search(**search_kwargs)
            except Exception as e:
                logger.warning(f"[Eval] search failed for {qid}: {e}")
                results.append({
                    "id": qid, "query": query, "error": str(e),
                    "hits": [], "expected_titles": expected_titles,
                })
                continue

            hits = resp.get("hits", [])

            # 计算每条命中是否匹配
            hit_titles = [h.get("title", "").lower() for h in hits]
            hit_contents = [h.get("content", "") for h in hits]

            # 首次命中排名 (1-indexed, 0=未命中)
            first_hit_rank = 0
            for rank, title in enumerate(hit_titles, 1):
                if title in expected_titles:
                    first_hit_rank = rank
                    break

            # 关键词覆盖
            kw_hit = 0
            if expected_kw and hits:
                top1_content = hit_contents[0] if hit_contents else ""
                kw_hit = sum(1 for kw in expected_kw if kw.lower() in top1_content.lower())

            results.append({
                "id": qid,
                "query": query,
                "category": case.get("category", ""),
                "expected_titles": expected_titles,
                "expected_kw": expected_kw,
                "expect_no_hit": expect_no_hit,
                "hit_titles": hit_titles[:top_k],
                "hit_scores": [h.get("score", 0) for h in hits[:top_k]],
                "first_hit_rank": first_hit_rank,
                "kw_total": len(expected_kw),
                "kw_hit": kw_hit,
                "total_hits": len(hits),
                "confidence": resp.get("confidence", "none"),
                "confidence_score": resp.get("confidence_score", 0),
                "suggestion": resp.get("suggestion", ""),
                "search_mode": resp.get("search_mode", ""),
                "elapsed_ms": resp.get("elapsed_ms", 0),
            })

        elapsed_total = round(time.time() - t0, 2)
        return self._compute_metrics(results, elapsed_total)

    @staticmethod
    def _compute_metrics(results: List[Dict], elapsed_total: float) -> Dict[str, Any]:
        """从单条评估结果中计算聚合指标。"""
        n = len(results)
        if n == 0:
            return {"error": "empty test set"}

        # 区分"应有命中"和"应无命中"
        expected_hit_cases = [r for r in results if not r.get("expect_no_hit")]
        no_hit_cases = [r for r in results if r.get("expect_no_hit")]
        ne = len(expected_hit_cases)

        # Top1 命中
        top1_hits = sum(
            1 for r in expected_hit_cases
            if r["first_hit_rank"] == 1
        )

        # Top3 命中
        top3_hits = sum(
            1 for r in expected_hit_cases
            if 1 <= r["first_hit_rank"] <= 3
        )

        # MRR
        mrr_sum = sum(
            (1.0 / r["first_hit_rank"]) if r["first_hit_rank"] > 0 else 0
            for r in expected_hit_cases
        )

        # 无结果率
        no_result = sum(1 for r in expected_hit_cases if r["total_hits"] == 0)

        # 错误命中率 (top1 不在 expected 中)
        wrong_hit = sum(
            1 for r in expected_hit_cases
            if r["total_hits"] > 0 and r["first_hit_rank"] == 0
        )

        # "应无命中"的正确拒绝率
        correct_reject = sum(
            1 for r in no_hit_cases
            if r.get("confidence") in ("none", "low")
        )

        # 关键词覆盖
        kw_total = sum(r["kw_total"] for r in expected_hit_cases)
        kw_hit_total = sum(r["kw_hit"] for r in expected_hit_cases)

        # 置信度分布
        conf_dist = {}
        for r in results:
            c = r.get("confidence", "unknown")
            conf_dist[c] = conf_dist.get(c, 0) + 1

        report = {
            "total_queries": n,
            "expected_hit_queries": ne,
            "expected_no_hit_queries": len(no_hit_cases),
            "metrics": {
                "top1_accuracy": round(top1_hits / ne, 4) if ne else 0,
                "top3_accuracy": round(top3_hits / ne, 4) if ne else 0,
                "mrr": round(mrr_sum / ne, 4) if ne else 0,
                "no_result_rate": round(no_result / ne, 4) if ne else 0,
                "wrong_hit_rate": round(wrong_hit / ne, 4) if ne else 0,
                "keyword_coverage": round(kw_hit_total / kw_total, 4) if kw_total else 0,
                "correct_reject_rate": round(correct_reject / len(no_hit_cases), 4) if no_hit_cases else None,
            },
            "confidence_distribution": conf_dist,
            "elapsed_total_s": elapsed_total,
            "avg_latency_ms": round(
                sum(r.get("elapsed_ms", 0) for r in results) / n, 1
            ) if n else 0,
            "details": results,
        }
        return report

    @staticmethod
    def print_report(report: Dict[str, Any]):
        """打印可读的评估报告。"""
        m = report.get("metrics", {})
        print("\n" + "=" * 60)
        print("  检索质量评估报告")
        print("=" * 60)
        print(f"  总查询数:     {report['total_queries']}")
        print(f"  应命中查询:   {report['expected_hit_queries']}")
        print(f"  应无命中查询: {report['expected_no_hit_queries']}")
        print(f"  总耗时:       {report['elapsed_total_s']}s")
        print(f"  平均延迟:     {report['avg_latency_ms']}ms")
        print()
        print("  ── 核心指标 ──────────────────────────")
        print(f"  Top1 命中率:   {m.get('top1_accuracy', 0):.1%}")
        print(f"  Top3 命中率:   {m.get('top3_accuracy', 0):.1%}")
        print(f"  MRR:           {m.get('mrr', 0):.4f}")
        print(f"  无结果率:      {m.get('no_result_rate', 0):.1%}")
        print(f"  错误命中率:    {m.get('wrong_hit_rate', 0):.1%}")
        print(f"  关键词覆盖率:  {m.get('keyword_coverage', 0):.1%}")
        if m.get("correct_reject_rate") is not None:
            print(f"  正确拒绝率:    {m['correct_reject_rate']:.1%}")
        print()
        print(f"  置信度分布:    {report.get('confidence_distribution', {})}")
        print()

        # 输出失败明细
        details = report.get("details", [])
        failures = [d for d in details if not d.get("expect_no_hit") and d["first_hit_rank"] != 1]
        if failures:
            print("  ── 未 Top1 命中 ────────────────────────")
            for d in failures:
                t1 = d["hit_titles"][0] if d["hit_titles"] else "(空)"
                print(f"  [{d['id']}] 「{d['query']}」 → top1: {t1}, "
                      f"期望: {d['expected_titles']}, rank={d['first_hit_rank']}")
        else:
            print("  所有应命中查询均 Top1 命中 ✓")

        print("=" * 60)
