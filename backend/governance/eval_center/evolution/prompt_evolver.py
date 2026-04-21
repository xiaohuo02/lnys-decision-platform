# -*- coding: utf-8 -*-
"""backend/governance/eval_center/evolution/prompt_evolver.py — Copilot Skill Prompt 自进化引擎

参考 OpenAI Cookbook Self-Evolving Agents：
  1. 用当前 prompt 执行 Skill → 生成输出
  2. 多 Grader 并行评分
  3. 失败 → MetapromptAgent 分析 + 优化 prompt
  4. VersionedPrompt 记录版本历史
  5. 循环直到通过或达到 max_retry
  6. 最终选择最优版本 → 等待人工审批
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Dict, List, Optional

from loguru import logger
from pydantic import BaseModel, Field

from backend.governance.eval_center.runners.skill_runner import SkillRunner
from backend.governance.eval_center.graders.base_grader import BaseGrader, GraderResult
from backend.governance.eval_center.graders.code_grader import SchemaCheckGrader, KeyInfoRetentionGrader
from backend.governance.eval_center.graders.llm_judge_grader import LLMJudgeGrader
from backend.governance.eval_center.graders.embedding_grader import EmbeddingSimilarityGrader
from backend.governance.eval_center.evolution.versioned_prompt import VersionedPrompt
from backend.governance.eval_center.evolution.metaprompt_agent import MetapromptAgent


class CaseEvolutionResult(BaseModel):
    """单条 case 的进化结果"""
    case_id: str
    passed: bool = False
    attempts: int = 0
    final_score: float = 0.0
    grader_scores: Dict[str, float] = Field(default_factory=dict)


class EvolutionResult(BaseModel):
    """完整进化循环结果"""
    skill_name: str
    initial_version: int = 0
    final_version: int = 0
    best_version: int = 0
    best_score: float = 0.0
    case_results: List[CaseEvolutionResult] = Field(default_factory=list)
    total_cases: int = 0
    passed_cases: int = 0
    pass_rate: float = 0.0
    status: str = "pending_approval"


class PromptEvolver:
    """Copilot Skill Prompt 自进化引擎"""

    def __init__(
        self,
        skill_name: str,
        initial_prompt: str,
        golden_cases: List[Dict[str, Any]],
        graders: Optional[List[BaseGrader]] = None,
        max_retry: int = 3,
        lenient_pass_ratio: float = 0.75,
        lenient_avg_threshold: float = 0.85,
        on_progress: Optional[Callable] = None,
    ):
        self.skill_name = skill_name
        self.golden_cases = golden_cases
        self.max_retry = max_retry
        self.lenient_pass_ratio = lenient_pass_ratio
        self.lenient_avg_threshold = lenient_avg_threshold
        self.on_progress = on_progress

        self.versioned_prompt = VersionedPrompt(
            skill_name=skill_name,
            initial_prompt=initial_prompt,
        )

        self.graders = graders or [
            SchemaCheckGrader(pass_threshold=1.0),
            KeyInfoRetentionGrader(pass_threshold=0.8),
            EmbeddingSimilarityGrader(pass_threshold=0.85),
            LLMJudgeGrader(pass_threshold=0.85),
        ]

        self.metaprompt_agent = MetapromptAgent(
            on_thinking=lambda thinking: self._emit(
                "eval:prompt_thinking", {"thinking": thinking, "status": "complete"}
            ),
        )

    def _emit(self, event_type: str, data: dict):
        if self.on_progress:
            try:
                self.on_progress(event_type, data)
            except Exception:
                pass

    async def evolve(self) -> EvolutionResult:
        """运行完整自进化循环"""
        initial_version = self.versioned_prompt.current().version
        case_results: List[CaseEvolutionResult] = []

        self._emit("eval:evolution_start", {
            "skill_name": self.skill_name,
            "total_cases": len(self.golden_cases),
            "initial_version": initial_version,
            "graders": [g.grader_name for g in self.graders],
        })

        for idx, case in enumerate(self.golden_cases):
            input_json = case.get("input_json", case)
            expected_json = case.get("expected_json", {})
            case_id = case.get("case_id", f"case_{idx}")

            if isinstance(input_json, str):
                input_json = json.loads(input_json)
            if isinstance(expected_json, str):
                expected_json = json.loads(expected_json)

            case_passed = False
            final_score = 0.0
            final_grader_scores = {}

            for attempt in range(1, self.max_retry + 1):
                current_prompt = self.versioned_prompt.current().prompt_text

                self._emit("eval:skill_exec_start", {
                    "case_index": idx,
                    "case_id": case_id,
                    "attempt": attempt,
                    "prompt_version": self.versioned_prompt.current().version,
                })

                # 1. 用当前 prompt 执行 Skill
                runner = SkillRunner(
                    skill_name=self.skill_name,
                    prompt_override=current_prompt,
                )
                run_result = await runner.run(input_json)

                self._emit("eval:skill_exec_result", {
                    "case_index": idx,
                    "success": run_result.success,
                    "latency_ms": run_result.latency_ms,
                })

                if not run_result.success:
                    logger.warning(f"[PromptEvolver] {self.skill_name} case {idx} attempt {attempt}: Runner 失败")
                    continue

                # 2. 多 Grader 评分
                grader_tasks = [
                    g.grade(input_json, expected_json, run_result.actual_output, {})
                    for g in self.graders
                ]
                grader_results_raw = await asyncio.gather(*grader_tasks, return_exceptions=True)

                grader_results = []
                for i, gr in enumerate(grader_results_raw):
                    if isinstance(gr, Exception):
                        grader_results.append(GraderResult(
                            grader_name=self.graders[i].grader_name,
                            score=0.0, passed=False,
                            reasoning=f"异常: {gr}",
                        ))
                    else:
                        grader_results.append(gr)

                avg_score = sum(g.score for g in grader_results) / len(grader_results)
                pass_ratio = sum(1 for g in grader_results if g.passed) / len(grader_results)
                lenient_pass = (
                    pass_ratio >= self.lenient_pass_ratio
                    and avg_score >= self.lenient_avg_threshold
                )

                grader_scores_map = {g.grader_name: g.score for g in grader_results}
                final_score = avg_score
                final_grader_scores = grader_scores_map

                for gr in grader_results:
                    self._emit("eval:grader_score", {
                        "case_index": idx,
                        "grader_name": gr.grader_name,
                        "score": gr.score,
                        "passed": gr.passed,
                        "reasoning": gr.reasoning,
                        "thinking": gr.thinking,
                    })

                # 记录版本分数
                self.versioned_prompt.current().avg_score = avg_score
                self.versioned_prompt.current().grader_scores = grader_scores_map

                if lenient_pass:
                    case_passed = True
                    logger.info(
                        f"[PromptEvolver] {self.skill_name} case {idx}: "
                        f"PASS (v{self.versioned_prompt.current().version}, score={avg_score:.3f})"
                    )
                    break

                # 3. 失败 → MetapromptAgent 优化
                if attempt < self.max_retry:
                    feedback = self._collect_feedback(grader_results)

                    self._emit("eval:prompt_thinking", {
                        "case_index": idx,
                        "attempt": attempt,
                        "status": "optimizing",
                    })

                    new_prompt = await self.metaprompt_agent.optimize(
                        original_prompt=current_prompt,
                        question=input_json.get("question", str(input_json)),
                        skill_output=run_result.actual_output.get("text", json.dumps(run_result.actual_output, ensure_ascii=False)),
                        grader_feedback=feedback,
                    )

                    if new_prompt and new_prompt.strip() != current_prompt.strip():
                        entry = self.versioned_prompt.update(
                            new_prompt=new_prompt,
                            avg_score=avg_score,
                            grader_scores=grader_scores_map,
                            metadata={"trigger_case": case_id, "attempt": attempt},
                        )
                        self._emit("eval:prompt_evolved", {
                            "case_index": idx,
                            "new_version": entry.version,
                            "score_before": avg_score,
                        })
                    else:
                        logger.warning(f"[PromptEvolver] MetapromptAgent 返回无效 prompt，跳过")

            case_results.append(CaseEvolutionResult(
                case_id=case_id,
                passed=case_passed,
                attempts=attempt,
                final_score=round(final_score, 4),
                grader_scores=final_grader_scores,
            ))

        # 选择最优版本
        best = self.versioned_prompt.select_best()
        passed_cases = sum(1 for c in case_results if c.passed)

        result = EvolutionResult(
            skill_name=self.skill_name,
            initial_version=initial_version,
            final_version=self.versioned_prompt.current().version,
            best_version=best.version,
            best_score=best.avg_score or 0.0,
            case_results=case_results,
            total_cases=len(case_results),
            passed_cases=passed_cases,
            pass_rate=round(passed_cases / len(case_results), 4) if case_results else 0,
            status="pending_approval",
        )

        self._emit("eval:evolution_complete", {
            "skill_name": self.skill_name,
            "best_version": best.version,
            "best_score": best.avg_score,
            "pass_rate": result.pass_rate,
            "total_versions": self.versioned_prompt.version_count,
        })

        return result

    @staticmethod
    def _collect_feedback(grader_results: List[GraderResult]) -> str:
        """收集失败 Grader 的反馈"""
        lines = []
        for gr in grader_results:
            status = "✓ PASS" if gr.passed else "✗ FAIL"
            lines.append(f"[{gr.grader_name}] {status} (score={gr.score:.3f})")
            if not gr.passed and gr.reasoning:
                lines.append(f"  原因: {gr.reasoning}")
        return "\n".join(lines)

