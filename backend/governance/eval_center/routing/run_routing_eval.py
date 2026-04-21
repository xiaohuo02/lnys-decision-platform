# -*- coding: utf-8 -*-
"""backend/governance/eval_center/routing/run_routing_eval.py — Supervisor 路由 Eval Runner

独立 CLI runner，对 20 题 routing_cases.json 跑 SupervisorAgent 的路由决策，
输出分级准确率和 failure_category 归因。

用法（从项目根目录）：
    # 纯规则模式（默认，不依赖 LLM）
    python -m backend.governance.eval_center.routing.run_routing_eval

    # 带 LLM 兜底（需要 LLM_API_KEY 等环境变量）
    python -m backend.governance.eval_center.routing.run_routing_eval --with-llm

    # 指定输出目录
    python -m backend.governance.eval_center.routing.run_routing_eval --output-dir reports/

设计对标：
  - forge Pico benchmark 的 4 判定条件 + failure_category 分类
  - forge 08 篇"不同机制用不同指标"——按 level 分层统计
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ── 路径准备：确保从项目根 import ──
_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parents[4]   # backend/governance/eval_center/routing/ → 上 4 级
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ── 常量 ──
DEFAULT_CASES_FILE = _HERE.parent / "routing_cases.json"
DEFAULT_OUTPUT_DIR = _HERE.parent / "reports"


# ── 失败归类 ──
FAILURE_WRONG_ROUTE        = "wrong_route"              # 路由错了
FAILURE_LOW_CONFIDENCE     = "low_confidence"           # 路由对但 conf 低于 min_confidence
FAILURE_ADV_FALSE_POSITIVE = "adversarial_false_positive"  # 对抗样本被规则误判
FAILURE_RUNTIME_ERROR      = "runtime_error"            # 运行时异常


def load_cases(path: Path) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("meta", {}), data.get("cases", [])


def categorize_failure(case: Dict[str, Any], actual_route: str, actual_conf: float) -> Optional[str]:
    """对比 actual vs expected，返回失败分类；None 表示 pass。"""
    expected_route = case["expected_route"]
    min_conf       = float(case["min_confidence"])
    is_adversarial = bool(case.get("is_adversarial", False))

    if actual_route != expected_route:
        if is_adversarial:
            return FAILURE_ADV_FALSE_POSITIVE
        return FAILURE_WRONG_ROUTE

    if actual_conf + 1e-9 < min_conf:
        return FAILURE_LOW_CONFIDENCE

    return None


async def run_single_case(
    agent,
    case: Dict[str, Any],
    use_llm: bool,
    supervisor_input_cls,
) -> Dict[str, Any]:
    """跑单条 case，返回结果 dict。"""
    t0 = time.perf_counter()
    try:
        inp = supervisor_input_cls(
            request_text=case["request_text"],
            request_type=case.get("request_type"),
            run_id=f"eval-{case['id']}",
        )
        if use_llm:
            out = await agent.aroute(inp)
        else:
            out = agent.route(inp)

        actual_route = out.route.value if hasattr(out.route, "value") else str(out.route)
        actual_conf  = float(out.confidence)
        actual_reason = out.reason
        used_llm      = bool(getattr(out, "used_llm", False))
        error         = None
    except Exception as exc:
        actual_route = "error"
        actual_conf  = 0.0
        actual_reason = f"{type(exc).__name__}: {exc}"
        used_llm      = False
        error         = actual_reason

    latency_ms = int((time.perf_counter() - t0) * 1000)
    failure    = FAILURE_RUNTIME_ERROR if error else categorize_failure(case, actual_route, actual_conf)
    passed     = failure is None

    return {
        "id":              case["id"],
        "group":           case["group"],
        "request_text":    case["request_text"],
        "expected_route":  case["expected_route"],
        "expected_level":  case["expected_level"],
        "min_confidence":  case["min_confidence"],
        "is_adversarial":  bool(case.get("is_adversarial", False)),
        "actual_route":    actual_route,
        "actual_confidence": round(actual_conf, 3),
        "actual_reason":   actual_reason,
        "used_llm":        used_llm,
        "latency_ms":      latency_ms,
        "passed":          passed,
        "failure_category": failure,
        "error":           error,
    }


def aggregate(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """按 group 分层统计 + 总体统计。"""
    total = len(results)
    passed = sum(1 for r in results if r["passed"])

    # 按 group 分组
    by_group: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in results:
        by_group[r["group"]].append(r)

    group_stats = {}
    for group, items in by_group.items():
        g_total  = len(items)
        g_passed = sum(1 for r in items if r["passed"])
        group_stats[group] = {
            "total":     g_total,
            "passed":    g_passed,
            "pass_rate": round(g_passed / g_total, 4) if g_total else 0.0,
        }

    # Failure category 分布
    failure_counts: Dict[str, int] = defaultdict(int)
    for r in results:
        if r["failure_category"]:
            failure_counts[r["failure_category"]] += 1

    # Latency
    latencies = [r["latency_ms"] for r in results if r["latency_ms"] > 0]
    avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0.0

    # LLM 使用率（aroute 模式才有意义）
    llm_triggered = sum(1 for r in results if r["used_llm"])

    return {
        "total":            total,
        "passed":           passed,
        "overall_pass_rate": round(passed / total, 4) if total else 0.0,
        "by_group":         group_stats,
        "failure_categories": dict(failure_counts),
        "avg_latency_ms":   avg_latency,
        "llm_triggered_count": llm_triggered,
    }


def render_console_report(meta: Dict[str, Any], results: List[Dict[str, Any]], summary: Dict[str, Any], mode: str) -> None:
    """在控制台打印可读的评测报告。"""
    print("=" * 78)
    print(f"  Supervisor 路由 Eval 报告   mode={mode}")
    print(f"  目标 Agent: {meta.get('target_agent', 'N/A')}")
    print(f"  Case 总数: {summary['total']}")
    print("=" * 78)

    # ── 总体 ──
    pr = summary["overall_pass_rate"] * 100
    print(f"\n[总体]  passed {summary['passed']}/{summary['total']}  pass_rate = {pr:.2f}%")
    print(f"[延时]  avg = {summary['avg_latency_ms']} ms")
    if summary["llm_triggered_count"]:
        print(f"[LLM]   触发次数 = {summary['llm_triggered_count']}")

    # ── 分层 ──
    print(f"\n[分层准确率]")
    order = ["explicit", "rule_strong", "rule_weak", "llm_or_fallback", "adversarial"]
    for group in order:
        if group in summary["by_group"]:
            s = summary["by_group"][group]
            bar = "█" * int(s["pass_rate"] * 20)
            print(f"  {group:20s}  {s['passed']:>2d}/{s['total']:<2d}  {s['pass_rate']*100:>6.2f}%  {bar}")

    # ── 失败分类 ──
    if summary["failure_categories"]:
        print(f"\n[Failure Categories]")
        for cat, cnt in sorted(summary["failure_categories"].items(), key=lambda x: -x[1]):
            print(f"  {cat:30s}  {cnt}")

    # ── 失败详情 ──
    failed = [r for r in results if not r["passed"]]
    if failed:
        print(f"\n[失败详情]  共 {len(failed)} 条")
        for r in failed:
            marker = "⚠️ ADV" if r["is_adversarial"] else "❌    "
            print(f"  {marker}  [{r['id']}] {r['request_text']}")
            print(f"            期望 → {r['expected_route']} (≥{r['min_confidence']})   "
                  f"实际 → {r['actual_route']} (conf={r['actual_confidence']})")
            print(f"            归类: {r['failure_category']}  |  reason: {r['actual_reason'][:80]}")

    print("\n" + "=" * 78)


async def main_async(args):
    cases_path = Path(args.cases_file) if args.cases_file else DEFAULT_CASES_FILE
    if not cases_path.exists():
        print(f"[ERROR] 找不到测试集文件: {cases_path}", file=sys.stderr)
        sys.exit(1)

    meta, cases = load_cases(cases_path)
    print(f"[INFO] 加载 {len(cases)} 条测试集: {cases_path}")

    # 延迟 import，避免在用户仅看 --help 时触发依赖加载
    from backend.agents.supervisor_agent import SupervisorAgent, SupervisorInput

    agent = SupervisorAgent()
    mode = "aroute (rule + LLM)" if args.with_llm else "route (rule only)"
    print(f"[INFO] 运行模式: {mode}")
    print(f"[INFO] 开始执行 ...\n")

    results: List[Dict[str, Any]] = []
    for case in cases:
        r = await run_single_case(agent, case, use_llm=args.with_llm, supervisor_input_cls=SupervisorInput)
        results.append(r)
        status = "✅" if r["passed"] else ("⚠️" if r["is_adversarial"] else "❌")
        print(f"  {status} [{r['id']:>12s}] {r['actual_route']:<20s} conf={r['actual_confidence']:.2f}")

    summary = aggregate(results)
    render_console_report(meta, results, summary, mode)

    # ── 写 JSON 报告 ──
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "with_llm" if args.with_llm else "rule_only"
    report_path = output_dir / f"routing_eval_{suffix}_{timestamp}.json"

    report_payload = {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "mode": mode,
            "cases_file": str(cases_path),
            "target_agent": meta.get("target_agent"),
        },
        "summary": summary,
        "results": results,
    }
    report_path.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[REPORT] 已写入: {report_path}")


def main():
    parser = argparse.ArgumentParser(
        description="SupervisorAgent 路由 Eval Runner（20 题迷你基准）"
    )
    parser.add_argument(
        "--with-llm",
        action="store_true",
        help="启用 LLM 兜底路由（aroute），需要 LLM_API_KEY 环境变量；默认仅跑规则",
    )
    parser.add_argument(
        "--cases-file",
        type=str,
        default=None,
        help=f"自定义测试集路径（默认: {DEFAULT_CASES_FILE.name}）",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help=f"报告输出目录（默认: {DEFAULT_OUTPUT_DIR}）",
    )
    args = parser.parse_args()

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
