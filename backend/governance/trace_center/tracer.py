# -*- coding: utf-8 -*-
"""backend/governance/trace_center/tracer.py

Trace Center 核心记录器
- 每次 workflow / agent 调用时注入 TraceContext
- 通过 record_run / record_step / finish_run 写库
- 设计原则：失败不阻塞业务主流程（降级记录错误日志）
"""
from __future__ import annotations

import uuid
import json
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.schemas.run_state import (
    RunCreate, RunRecord, RunStatus,
    StepRecord, StepType, TokenUsage, GuardrailHit,
)


# ── 数据库写入（同步，使用 SQLAlchemy Session）─────────────────────

def _upsert_run(db: Session, run: RunRecord) -> None:
    """将 RunRecord 写入 MySQL runs 表"""
    sql = """
        INSERT INTO runs
            (run_id, thread_id, request_id, entrypoint,
             workflow_name, workflow_version, status,
             input_summary, output_summary,
             total_tokens, total_cost, error_message,
             triggered_by,
             started_at, ended_at, latency_ms)
        VALUES
            (:run_id, :thread_id, :request_id, :entrypoint,
             :workflow_name, :workflow_version, :status,
             :input_summary, :output_summary,
             :total_tokens, :total_cost, :error_message,
             :triggered_by,
             :started_at, :ended_at, :latency_ms)
        ON DUPLICATE KEY UPDATE
            status         = VALUES(status),
            output_summary = VALUES(output_summary),
            total_tokens   = VALUES(total_tokens),
            total_cost     = VALUES(total_cost),
            error_message  = VALUES(error_message),
            triggered_by   = COALESCE(VALUES(triggered_by), triggered_by),
            ended_at       = VALUES(ended_at),
            latency_ms     = VALUES(latency_ms)
    """
    db.execute(
        text(sql),
        {
            "run_id":           str(run.run_id),
            "thread_id":        run.thread_id,
            "request_id":       run.request_id,
            "entrypoint":       run.entrypoint,
            "workflow_name":    run.workflow_name,
            "workflow_version": run.workflow_version,
            "status":           run.status if isinstance(run.status, str) else run.status.value,
            "input_summary":    run.input_summary,
            "output_summary":   run.output_summary,
            "total_tokens":     run.total_tokens,
            "total_cost":       run.total_cost,
            "error_message":    run.error_message,
            "triggered_by":     run.triggered_by,
            "started_at":       run.started_at,
            "ended_at":         run.ended_at,
            "latency_ms":       run.latency_ms,
        },
    )
    db.commit()


def _insert_step(db: Session, step: StepRecord) -> None:
    """将 StepRecord 写入 MySQL run_steps 表"""
    sql = """
        INSERT INTO run_steps
            (step_id, run_id, parent_step_id, step_type, step_name,
             agent_name, tool_name, model_name,
             prompt_id, prompt_version, policy_version,
             handoff_from, handoff_to,
             status, input_summary, output_summary,
             guardrail_hits_json, token_usage_json,
             cost_amount, retry_count, artifact_ids_json,
             error_message, started_at, ended_at)
        VALUES
            (:step_id, :run_id, :parent_step_id, :step_type, :step_name,
             :agent_name, :tool_name, :model_name,
             :prompt_id, :prompt_version, :policy_version,
             :handoff_from, :handoff_to,
             :status, :input_summary, :output_summary,
             :guardrail_hits_json, :token_usage_json,
             :cost_amount, :retry_count, :artifact_ids_json,
             :error_message, :started_at, :ended_at)
        ON DUPLICATE KEY UPDATE
            status              = VALUES(status),
            output_summary      = VALUES(output_summary),
            guardrail_hits_json = VALUES(guardrail_hits_json),
            token_usage_json    = VALUES(token_usage_json),
            cost_amount         = VALUES(cost_amount),
            retry_count         = VALUES(retry_count),
            artifact_ids_json   = VALUES(artifact_ids_json),
            error_message       = VALUES(error_message),
            ended_at            = VALUES(ended_at)
    """
    db.execute(
        text(sql),
        {
            "step_id":            str(step.step_id),
            "run_id":             str(step.run_id),
            "parent_step_id":     str(step.parent_step_id) if step.parent_step_id else None,
            "step_type":          step.step_type if isinstance(step.step_type, str) else step.step_type.value,
            "step_name":          step.step_name,
            "agent_name":         step.agent_name,
            "tool_name":          step.tool_name,
            "model_name":         step.model_name,
            "prompt_id":          str(step.prompt_id) if step.prompt_id else None,
            "prompt_version":     step.prompt_version,
            "policy_version":     step.policy_version,
            "handoff_from":       step.handoff_from,
            "handoff_to":         step.handoff_to,
            "status":             step.status if isinstance(step.status, str) else step.status.value,
            "input_summary":      step.input_summary,
            "output_summary":     step.output_summary,
            "guardrail_hits_json": json.dumps(
                [h.model_dump() for h in step.guardrail_hits], ensure_ascii=False, default=str
            ) if step.guardrail_hits else None,
            "token_usage_json":   step.token_usage.model_dump_json(),
            "cost_amount":        step.cost_amount,
            "retry_count":        step.retry_count,
            "artifact_ids_json":  json.dumps(step.artifact_ids) if step.artifact_ids else None,
            "error_message":      step.error_message,
            "started_at":         step.started_at,
            "ended_at":           step.ended_at,
        },
    )
    db.commit()


# ── TraceContext：单次 run 的上下文跟踪对象 ────────────────────────

class TraceContext:
    """
    附着在一次 workflow run 上的 trace 上下文。
    用法示例：
        ctx = TraceContext.start(db, RunCreate(...))
        step_id = ctx.begin_step(step_type=StepType.SERVICE_CALL, step_name="fraud_scoring")
        ctx.end_step(step_id, output_summary="high risk", token_usage=TokenUsage(total_tokens=120))
        ctx.finish(output_summary="done", total_tokens=500)
    """

    def __init__(self, run: RunRecord, db: Session):
        self._run   = run
        self._db    = db
        self._steps: Dict[str, StepRecord] = {}
        self._t0    = time.monotonic()
        self._acc_tokens: int   = 0
        self._acc_cost:   float = 0.0

    # ── Run 生命周期 ──────────────────────────────────────────────

    @classmethod
    def start(cls, db: Session, create: RunCreate) -> "TraceContext":
        """创建 run 记录并持久化，返回 TraceContext"""
        run = RunRecord(
            thread_id=create.thread_id,
            request_id=create.request_id,
            entrypoint=create.entrypoint,
            workflow_name=create.workflow_name,
            workflow_version=create.workflow_version,
            status=RunStatus.RUNNING,
            input_summary=create.input_summary,
            triggered_by=create.triggered_by,
        )
        try:
            _upsert_run(db, run)
        except Exception as e:
            logger.warning(f"[trace] run insert failed (non-fatal): {e}")
        return cls(run, db)

    def finish(
        self,
        output_summary: Optional[str] = None,
        total_tokens:   int = 0,
        total_cost:     float = 0.0,
        error_message:  Optional[str] = None,
    ) -> RunRecord:
        """标记 run 结束并更新 DB（token/cost 未显式传入时使用 step 累加值）"""
        elapsed = int((time.monotonic() - self._t0) * 1000)
        self._run.status        = RunStatus.FAILED if error_message else RunStatus.COMPLETED
        self._run.output_summary= output_summary
        self._run.total_tokens  = total_tokens if total_tokens else self._acc_tokens
        self._run.total_cost    = total_cost if total_cost else self._acc_cost
        self._run.error_message = error_message
        self._run.ended_at      = datetime.now(timezone.utc)
        self._run.latency_ms    = elapsed
        try:
            _upsert_run(self._db, self._run)
        except Exception as e:
            logger.warning(f"[trace] run finish failed (non-fatal): {e}")
        return self._run

    def mark_paused(self) -> None:
        """HITL interrupt 时标记 run 为 paused"""
        self._run.status = RunStatus.PAUSED
        try:
            _upsert_run(self._db, self._run)
        except Exception as e:
            logger.warning(f"[trace] run pause failed (non-fatal): {e}")

    # ── Step 生命周期 ─────────────────────────────────────────────

    def begin_step(
        self,
        step_type:    StepType,
        step_name:    str,
        agent_name:   Optional[str] = None,
        tool_name:    Optional[str] = None,
        model_name:   Optional[str] = None,
        prompt_id:    Optional[uuid.UUID] = None,
        prompt_version: Optional[str] = None,
        policy_version: Optional[str] = None,
        handoff_from: Optional[str] = None,
        handoff_to:   Optional[str] = None,
        input_summary: Optional[str] = None,
        parent_step_id: Optional[uuid.UUID] = None,
    ) -> uuid.UUID:
        """开始一个 step，写入 DB，返回 step_id"""
        step = StepRecord(
            run_id=self._run.run_id,
            parent_step_id=parent_step_id,
            step_type=step_type,
            step_name=step_name,
            agent_name=agent_name,
            tool_name=tool_name,
            model_name=model_name,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            policy_version=policy_version,
            handoff_from=handoff_from,
            handoff_to=handoff_to,
            status=RunStatus.RUNNING,
            input_summary=input_summary,
        )
        self._steps[str(step.step_id)] = step
        try:
            _insert_step(self._db, step)
        except Exception as e:
            logger.warning(f"[trace] step insert failed (non-fatal): {e}")
        return step.step_id

    def end_step(
        self,
        step_id:        uuid.UUID,
        output_summary: Optional[str] = None,
        token_usage:    Optional[TokenUsage] = None,
        cost_amount:    float = 0.0,
        guardrail_hits: Optional[List[GuardrailHit]] = None,
        artifact_ids:   Optional[List[str]] = None,
        error_message:  Optional[str] = None,
        retry_count:    int = 0,
    ) -> None:
        """结束一个 step 并更新 DB"""
        step = self._steps.get(str(step_id))
        if step is None:
            logger.warning(f"[trace] end_step called with unknown step_id={step_id}")
            return
        step.status         = RunStatus.FAILED if error_message else RunStatus.COMPLETED
        step.output_summary = output_summary
        step.token_usage    = token_usage or TokenUsage()
        step.cost_amount    = cost_amount
        step.guardrail_hits = guardrail_hits or []
        if token_usage:
            self._acc_tokens += token_usage.total_tokens
        self._acc_cost += cost_amount
        step.artifact_ids   = artifact_ids or []
        step.error_message  = error_message
        step.retry_count    = retry_count
        step.ended_at       = datetime.now(timezone.utc)
        try:
            _insert_step(self._db, step)
        except Exception as e:
            logger.warning(f"[trace] step update failed (non-fatal): {e}")

    # ── 属性 ──────────────────────────────────────────────────────

    @property
    def run_id(self) -> uuid.UUID:
        return self._run.run_id

    @property
    def thread_id(self) -> str:
        return self._run.thread_id

    @property
    def run(self) -> RunRecord:
        return self._run
