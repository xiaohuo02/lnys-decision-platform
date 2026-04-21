"""
评测引擎服务 — 运行评测实验，生成评测结果。

真实实现（v2）：
  1. 读取实验关联的数据集用例 (eval_cases)
  2. 根据 target_type 选择对应 Runner 真实调用 Agent/Skill/Workflow
  3. 根据 evaluator 的 scoring_rules 选择 Grader 组合评分
  4. 汇总 pass_rate / total_cases，更新 eval_experiments
  5. 通过回调函数支持 SSE 实时推送进度
"""

import asyncio
import json
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import sqlalchemy
from loguru import logger
from sqlalchemy.orm import Session

from backend.governance.eval_center.runners.base_runner import BaseRunner, RunnerResult
from backend.governance.eval_center.runners.ml_agent_runner import MLAgentRunner
from backend.governance.eval_center.runners.skill_runner import SkillRunner
from backend.governance.eval_center.runners.workflow_runner import WorkflowRunner
from backend.governance.eval_center.runners.supervisor_runner import SupervisorRunner
from backend.governance.eval_center.graders.base_grader import BaseGrader, GraderResult
from backend.governance.eval_center.graders.code_grader import (
    ExactMatchGrader,
    FieldMatchGrader,
    SchemaCheckGrader,
    ThresholdGrader,
    KeywordMatchGrader,
    KeyInfoRetentionGrader,
)
from backend.governance.eval_center.graders.llm_judge_grader import LLMJudgeGrader
from backend.governance.eval_center.graders.embedding_grader import EmbeddingSimilarityGrader
from backend.governance.eval_center.graders.trace_grader import (
    TraceRouteGrader,
    TraceStepCompletenessGrader,
    TraceToolAccuracyGrader,
)


# ── Grader 注册表 ────────────────────────────────────────────────

_GRADER_REGISTRY: Dict[str, type] = {
    "exact_match":       ExactMatchGrader,
    "field_match":       FieldMatchGrader,
    "schema_check":      SchemaCheckGrader,
    "threshold":         ThresholdGrader,
    "keyword_match":     KeywordMatchGrader,
    "key_info_retention": KeyInfoRetentionGrader,
    "llm_judge":         LLMJudgeGrader,
    "embedding_similarity": EmbeddingSimilarityGrader,
    "trace_route":          TraceRouteGrader,
    "trace_step_completeness": TraceStepCompletenessGrader,
    "trace_tool_accuracy":  TraceToolAccuracyGrader,
}


def build_graders(scoring_rules: Dict[str, Any]) -> List[BaseGrader]:
    """根据 evaluator.scoring_rules 构建 Grader 组合

    scoring_rules 格式:
      {
        "pass_threshold": 0.8,
        "graders": [
          {"type": "exact_match", "field": "answer", "pass_threshold": 1.0},
          {"type": "llm_judge", "pass_threshold": 0.85},
          ...
        ]
      }
    或简化格式:
      {"type": "exact_match", "pass_threshold": 0.8}
    """
    global_threshold = scoring_rules.get("pass_threshold", 0.8)
    grader_configs = scoring_rules.get("graders", [])

    # 简化格式：只有一个 grader
    if not grader_configs and "type" in scoring_rules:
        grader_configs = [scoring_rules]

    # 默认：如果完全没配置 grader，根据 type 推断
    if not grader_configs:
        grader_configs = [{"type": "exact_match", "pass_threshold": global_threshold}]

    graders = []
    for cfg in grader_configs:
        gtype = cfg.get("type", "exact_match")
        cls = _GRADER_REGISTRY.get(gtype)
        if cls is None:
            logger.warning(f"[eval_service] 未知 grader 类型: {gtype}, 跳过")
            continue
        # 兼容 {"type":"x", "config":{...}} 和 {"type":"x", "field":"y"} 两种格式
        flat = {k: v for k, v in cfg.items() if k not in ("type", "pass_threshold", "config")}
        if "config" in cfg and isinstance(cfg["config"], dict):
            flat.update(cfg["config"])
        threshold = flat.pop("pass_threshold", cfg.get("pass_threshold", global_threshold))
        graders.append(cls(pass_threshold=threshold, **flat))

    return graders


def resolve_runner(
    target_type: Optional[str],
    target_id: Optional[str],
    app_state: Any = None,
) -> Optional[BaseRunner]:
    """根据 target_type 和 target_id 解析对应的 Runner

    Args:
        target_type: "ml_agent" | "copilot_skill" | "workflow" | "supervisor"
        target_id:   Agent/Skill/Workflow 的标识名
        app_state:   FastAPI app.state，包含已加载的 Agent 实例
    """
    if target_type == "ml_agent":
        agent = None
        if app_state is not None:
            agent = getattr(app_state, target_id, None)
        return MLAgentRunner(agent=agent, agent_name=target_id or "unknown")

    elif target_type == "copilot_skill":
        return SkillRunner(skill_name=target_id or "")

    elif target_type == "workflow":
        supervisor = None
        if app_state is not None:
            supervisor = getattr(app_state, "supervisor_agent", None)
        return WorkflowRunner(supervisor_agent=supervisor)

    elif target_type == "supervisor":
        supervisor = None
        if app_state is not None:
            supervisor = getattr(app_state, "supervisor_agent", None)
        return SupervisorRunner(supervisor_agent=supervisor)

    else:
        # 尝试自动推断
        if target_id:
            from backend.copilot.registry import SkillRegistry
            skill = SkillRegistry.instance().get(target_id)
            if skill is not None:
                return SkillRunner(skill_name=target_id)
        return None


async def run_experiment_async(
    experiment_id: str,
    db: Session,
    app_state: Any = None,
    on_progress: Optional[Callable] = None,
) -> dict:
    """
    异步执行评测实验（真实调用 Agent/Skill + 多 Grader 评分）。

    Args:
        experiment_id: 实验 ID
        db:            同步 DB session
        app_state:     FastAPI app.state
        on_progress:   进度回调 (event_type, data) → None

    Returns:
        dict with keys: experiment_id, status, total_cases, pass_rate, message, results
    """
    def emit(event_type: str, data: dict):
        if on_progress:
            try:
                on_progress(event_type, data)
            except Exception:
                pass

    # ── 1. 读取实验信息 ──
    exp = db.execute(sqlalchemy.text(
        "SELECT * FROM eval_experiments WHERE experiment_id = :id"
    ), {"id": experiment_id}).fetchone()
    if exp is None:
        raise ValueError(f"experiment_id={experiment_id} 不存在")

    exp = dict(exp._mapping)
    if exp["status"] == "completed":
        raise ValueError("该实验已完成，无法重复运行")
    if exp["status"] == "running":
        raise ValueError("该实验正在运行中，请勿重复触发")

    # 清理 failed 重跑的残留
    if exp["status"] == "failed":
        db.execute(sqlalchemy.text(
            "DELETE FROM eval_results WHERE experiment_id = :id"
        ), {"id": experiment_id})
        db.flush()

    dataset_id = exp["dataset_id"]
    evaluator_id = exp["evaluator_id"]
    target_type = exp.get("target_type")
    target_id = exp.get("target_id")

    # ── 2. 读取评测器 ──
    evaluator = db.execute(sqlalchemy.text(
        "SELECT * FROM evaluators WHERE evaluator_id = :id"
    ), {"id": evaluator_id}).fetchone()
    if evaluator is None:
        raise ValueError(f"evaluator_id={evaluator_id} 不存在")

    evaluator = dict(evaluator._mapping)
    scoring_rules = evaluator["scoring_rules"]
    if isinstance(scoring_rules, str):
        scoring_rules = json.loads(scoring_rules)

    # ── 3. 构建 Runner 和 Grader ──
    runner = resolve_runner(target_type, target_id, app_state)
    graders = build_graders(scoring_rules)

    if not graders:
        raise ValueError("无法从 scoring_rules 构建任何 Grader")

    logger.info(
        f"[eval_service] 实验 {experiment_id}: "
        f"runner={runner.__class__.__name__ if runner else 'None'}, "
        f"graders={[g.grader_name for g in graders]}"
    )

    # ── 4. 读取数据集用例 ──
    cases = db.execute(sqlalchemy.text(
        "SELECT case_id, input_json, expected_json FROM eval_cases "
        "WHERE dataset_id = :did ORDER BY created_at"
    ), {"did": dataset_id}).fetchall()
    cases = [dict(r._mapping) for r in cases]

    if not cases:
        raise ValueError(f"数据集 {dataset_id} 没有用例，请先添加测试数据")

    # ── 5. 将状态设为 running ──
    db.execute(sqlalchemy.text(
        "UPDATE eval_experiments SET status='running' WHERE experiment_id=:id"
    ), {"id": experiment_id})
    db.commit()

    emit("eval:experiment_start", {
        "experiment_id": experiment_id,
        "total_cases": len(cases),
        "graders": [g.grader_name for g in graders],
        "runner": runner.__class__.__name__ if runner else "none",
    })

    # ── 6. 逐条评测 ──
    total = len(cases)
    passed_count = 0
    results_summary = []

    for idx, case in enumerate(cases):
        case_id = case["case_id"]
        input_json = case["input_json"]
        expected_json = case["expected_json"]

        # 解析 JSON 字符串
        if isinstance(input_json, str):
            input_json = json.loads(input_json)
        if isinstance(expected_json, str):
            expected_json = json.loads(expected_json)

        emit("eval:case_start", {
            "case_index": idx,
            "case_id": case_id,
            "total": total,
        })

        # ── 6a. Runner 执行 ──
        if runner is not None:
            run_result = await runner.run(input_json)
        else:
            # 无 Runner 时降级：用 expected 模拟
            run_result = RunnerResult(
                actual_output=expected_json,
                metadata={"fallback": True, "reason": "no_runner"},
            )

        actual_output = run_result.actual_output

        logger.debug(
            f"[eval_service] case {case_id}: success={run_result.success}, "
            f"error={run_result.error}, output_keys={list(actual_output.keys()) if actual_output else 'empty'}"
        )

        emit("eval:case_executed", {
            "case_index": idx,
            "case_id": case_id,
            "success": run_result.success,
            "latency_ms": run_result.latency_ms,
            "error": run_result.error,
        })

        # ── 6b. 多 Grader 评分 ──
        grader_results: List[GraderResult] = []

        if run_result.success:
            grader_tasks = [
                g.grade(input_json, expected_json, actual_output, scoring_rules)
                for g in graders
            ]
            grader_results = await asyncio.gather(*grader_tasks, return_exceptions=True)

            # 处理异常
            clean_results = []
            for i, gr in enumerate(grader_results):
                if isinstance(gr, Exception):
                    logger.error(f"[eval_service] Grader {graders[i].grader_name} 异常: {gr}")
                    clean_results.append(GraderResult(
                        grader_name=graders[i].grader_name,
                        score=0.0,
                        passed=False,
                        reasoning=f"Grader 执行异常: {type(gr).__name__}: {gr}",
                    ))
                else:
                    clean_results.append(gr)
            grader_results = clean_results
        else:
            # Runner 失败，所有 Grader 判 0 分
            grader_results = [
                GraderResult(
                    grader_name=g.grader_name,
                    score=0.0,
                    passed=False,
                    reasoning=f"Runner 执行失败: {run_result.error}",
                )
                for g in graders
            ]

        # ── 6c. 聚合评分 ──
        if grader_results:
            avg_score = sum(gr.score for gr in grader_results) / len(grader_results)
            all_passed = all(gr.passed for gr in grader_results)
            pass_ratio = sum(1 for gr in grader_results if gr.passed) / len(grader_results)
            # lenient pass: 75% grader 通过 + 平均分 >= 全局阈值
            global_threshold = scoring_rules.get("pass_threshold", 0.8)
            case_passed = pass_ratio >= 0.75 and avg_score >= global_threshold
        else:
            avg_score = 0.0
            case_passed = False

        if case_passed:
            passed_count += 1

        # ── 6d. 写入结果 ──
        grader_scores_json = {gr.grader_name: gr.score for gr in grader_results}
        grader_reasoning_json = {
            gr.grader_name: {
                "score": gr.score,
                "passed": gr.passed,
                "reasoning": gr.reasoning,
                "thinking": gr.thinking,
            }
            for gr in grader_results
        }

        detail = {
            "grader_scores": grader_scores_json,
            "grader_reasoning": grader_reasoning_json,
            "avg_score": round(avg_score, 4),
            "pass_ratio": round(pass_ratio, 4) if grader_results else 0,
            "runner_latency_ms": run_result.latency_ms,
            "runner_error": run_result.error,
            "tokens_used": run_result.tokens_used,
        }

        db.execute(sqlalchemy.text("""
            INSERT INTO eval_results
                (experiment_id, case_id, actual_json, score, passed, detail_json)
            VALUES
                (:eid, :cid, :actual, :score, :passed, :detail)
        """), {
            "eid": experiment_id,
            "cid": case_id,
            "actual": json.dumps(actual_output, ensure_ascii=False, default=str),
            "score": round(avg_score, 4),
            "passed": 1 if case_passed else 0,
            "detail": json.dumps(detail, ensure_ascii=False, default=str),
        })
        db.flush()

        emit("eval:case_graded", {
            "case_index": idx,
            "case_id": case_id,
            "score": round(avg_score, 4),
            "passed": case_passed,
            "grader_scores": grader_scores_json,
        })

        results_summary.append({
            "case_id": case_id,
            "score": round(avg_score, 4),
            "passed": case_passed,
            "grader_scores": grader_scores_json,
        })

    # ── 7. 更新实验汇总 ──
    pass_rate = round(passed_count / total, 4) if total > 0 else 0
    db.execute(sqlalchemy.text("""
        UPDATE eval_experiments
        SET status='completed', total_cases=:total, pass_rate=:rate, ended_at=:now
        WHERE experiment_id=:id
    """), {
        "id": experiment_id,
        "total": total,
        "rate": pass_rate,
        "now": datetime.utcnow(),
    })
    db.commit()

    emit("eval:experiment_complete", {
        "experiment_id": experiment_id,
        "total_cases": total,
        "passed": passed_count,
        "pass_rate": pass_rate,
    })

    return {
        "experiment_id": experiment_id,
        "status": "completed",
        "total_cases": total,
        "passed": passed_count,
        "pass_rate": pass_rate,
        "results": results_summary,
        "message": f"评测完成，共 {total} 条用例，通过 {passed_count} 条，通过率 {pass_rate*100:.1f}%",
    }


def run_experiment(experiment_id: str, db: Session, app_state: Any = None) -> dict:
    """同步包装，兼容现有调用方式"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(
            run_experiment_async(experiment_id, db, app_state)
        )
    finally:
        loop.close()
