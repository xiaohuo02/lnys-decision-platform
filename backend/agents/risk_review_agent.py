# -*- coding: utf-8 -*-
"""backend/agents/risk_review_agent.py

RiskReviewAgent — 高风险交易审核 Agent

╔══════════════════════════════════════════════════════════════════╗
║  Agent 契约 (必须在实现前确认)                                     ║
╠══════════════════════════════════════════════════════════════════╣
║  1. 输入                                                          ║
║     RiskReviewInput:                                             ║
║       fraud_result: FraudScoringResult  欺诈评分结果              ║
║       run_id / thread_id                                         ║
║                                                                  ║
║  2. 允许调用的 service / tool                                     ║
║     - FraudScoringService（已在 workflow 中完成，读结果即可）      ║
║     - hitl_center.create_review_case()                           ║
║     - hitl_center.get_review_decision()                          ║
║     - audit_center.write_audit_log()                             ║
║     - LangGraph interrupt() 触发 HITL 等待                       ║
║                                                                  ║
║  3. 输出 schema                                                   ║
║     RiskReviewOutput:                                            ║
║       case_id: str  审核案例 ID                                   ║
║       status: str  pending / approved / rejected / edited        ║
║       decision: Optional[ReviewAction]                           ║
║       hitl_triggered: bool                                       ║
║       summary: str                                               ║
║                                                                  ║
║  4. 不能做的事                                                    ║
║     - 自动执行冻结订单/退款（必须经过审批）                        ║
║     - 自动修改 risk_status（必须审批后由 action ledger 执行）      ║
║     - 输出未脱敏的客户个人信息                                     ║
║                                                                  ║
║  5. 失败降级                                                      ║
║     - HITL 超时 → 标记 status=expired，不自动放行或拒绝           ║
║     - DB 写入失败 → 记录日志，不中断主流程                        ║
║                                                                  ║
║  6. 是否进入 HITL                                                 ║
║     是。final_score >= 0.7 时强制触发 LangGraph interrupt()       ║
║                                                                  ║
║  7. 依赖的 artifact                                               ║
║     fraud_score artifact（来自 FraudScoringService）              ║
║                                                                  ║
║  8. 写入 trace 的关键字段                                         ║
║     agent_name="RiskReviewAgent"                                 ║
║     step_type=AGENT_CALL (or HITL if interrupt triggered)        ║
║     input_summary=high_risk_count + hitl_count                   ║
║     output_summary=case_id + status                              ║
║     artifact_ids=[review_case.case_id]                           ║
╚══════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import sqlalchemy
from loguru import logger
from pydantic import BaseModel, Field

from backend.schemas.review import (
    ReviewCaseCreate, ReviewCase, ReviewActionCreate, ReviewAction,
    ReviewType, ReviewStatus, ReviewPriority, ReviewActionType,
)
from backend.services.fraud_scoring_service import FraudScoringResult, SingleFraudScore


# ── 输入/输出 schema ──────────────────────────────────────────────

class RiskReviewInput(BaseModel):
    run_id:          Optional[str] = None
    thread_id:       Optional[str] = None
    fraud_result:    Optional[Dict[str, Any]] = None   # FraudScoringResult dict
    transaction_ids: List[str] = Field(default_factory=list)


class RiskReviewOutput(BaseModel):
    run_id:          Optional[str]
    case_ids:        List[str] = Field(default_factory=list)
    hitl_triggered:  bool = False
    total_high_risk: int  = 0
    pending_count:   int  = 0
    summary:         str  = ""
    error_message:   Optional[str] = None


# ── HITL Center 辅助函数 ──────────────────────────────────────────

def create_review_case_in_db(
    db,
    run_id: str,
    transaction_id: str,
    fraud_score: float,
    risk_level:  str,
    thread_id:   Optional[str] = None,
) -> str:
    """向 review_cases 表写入一条 HITL 审核案例，返回 case_id。
    thread_id 存入 context_json，供 admin/reviews.py 恢复 LangGraph workflow 使用。
    """
    case_id = str(uuid.uuid4())
    try:
        db.execute(
            sqlalchemy.text("""
                INSERT INTO review_cases
                    (case_id, run_id, review_type, priority, status,
                     subject, context_json, created_by)
                VALUES
                    (:case_id, :run_id, :review_type, :priority, :status,
                     :subject, :context_json, :created_by)
            """),
            {
                "case_id":      case_id,
                "run_id":       run_id,
                "review_type":  ReviewType.FRAUD_HITL,
                "priority":     ReviewPriority.HIGH if fraud_score >= 0.85 else ReviewPriority.MEDIUM,
                "status":       ReviewStatus.PENDING,
                "subject":      f"高风险交易审核: {transaction_id}, 风险分={fraud_score:.4f}",
                "context_json": json.dumps({
                    "transaction_id": transaction_id,
                    "fraud_score":    fraud_score,
                    "risk_level":     risk_level,
                    "thread_id":      thread_id,
                }),
                "created_by":   "RiskReviewAgent",
            },
        )
        db.commit()
    except Exception as e:
        logger.warning(f"[RiskReviewAgent] create_review_case failed (non-fatal): {e}")
    return case_id


def record_review_action_in_db(
    db,
    case_id:      str,
    action_type:  str,
    decision_by:  str,
    note:         Optional[str] = None,
    override:     Optional[dict] = None,
) -> str:
    """向 review_actions 表写入一条审批动作，更新 case 状态"""
    action_id = str(uuid.uuid4())
    try:
        # 写入动作
        db.execute(
            sqlalchemy.text("""
                INSERT INTO review_actions
                    (action_id, case_id, action_type, decision_by,
                     decision_note, override_payload)
                VALUES
                    (:action_id, :case_id, :action_type, :decision_by,
                     :decision_note, :override_payload)
            """),
            {
                "action_id":        action_id,
                "case_id":          case_id,
                "action_type":      action_type,
                "decision_by":      decision_by,
                "decision_note":    note,
                "override_payload": json.dumps(override) if override else None,
            },
        )
        # 更新 case 状态
        status_map = {
            ReviewActionType.APPROVE:  ReviewStatus.APPROVED,
            ReviewActionType.EDIT:     ReviewStatus.EDITED,
            ReviewActionType.REJECT:   ReviewStatus.REJECTED,
        }
        new_status = status_map.get(action_type)
        if new_status:
            db.execute(
                sqlalchemy.text(
                    "UPDATE review_cases SET status=:status, updated_at=NOW() WHERE case_id=:case_id"
                ),
                {"status": new_status, "case_id": case_id},
            )
        db.commit()
    except Exception as e:
        logger.warning(f"[RiskReviewAgent] record_review_action failed (non-fatal): {e}")
    return action_id


# ── Agent 实现 ────────────────────────────────────────────────────

class RiskReviewAgent:
    """
    读取 FraudScoringResult，对 hitl_required=True 的交易创建审核案例。
    在 LangGraph workflow 中，高风险交易需配合 interrupt() 使用。
    支持 LLM (qwen3.5-plus) 生成风险审核摘要。
    """

    # ── 异步 LLM 风险摘要 ─────────────────────────────────────

    async def areview(
        self,
        inp: RiskReviewInput,
        db=None,
    ) -> RiskReviewOutput:
        """
        异步审核：先调 prepare_review 创建案例，再调 LLM 生成风险摘要。
        LLM 失败时降级到模板摘要。
        """
        output = self.prepare_review(inp, db=db)

        # 如果有高风险交易，用 LLM 生成摘要
        if output.hitl_triggered and inp.fraud_result:
            llm_summary = await self._llm_risk_summary(inp.fraud_result)
            if llm_summary:
                output.summary = llm_summary

        return output

    async def _llm_risk_summary(self, fraud_result: Dict[str, Any]) -> Optional[str]:
        """用 qwen3.5-plus 生成风险审核摘要"""
        try:
            from langchain_openai import ChatOpenAI

            api_key   = os.getenv("LLM_API_KEY", "")
            base_url  = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
            model     = os.getenv("LLM_MODEL_NAME", "qwen3.5-plus-2026-02-15")

            if not api_key:
                logger.warning("[RiskReviewAgent] LLM_API_KEY 未设置，跳过 LLM 摘要")
                return None

            scores = fraud_result.get("scores", [])
            hitl_scores = [s for s in scores if s.get("hitl_required")]

            # 构造摘要输入
            score_lines = []
            for s in hitl_scores[:10]:  # 最多 10 笔
                tid    = s.get("transaction_id", "N/A")
                fscore = s.get("final_score", 0)
                rlevel = s.get("risk_level", "未知")
                reason = s.get("risk_reason", "")
                score_lines.append(f"- 交易 {tid}: 风险分={fscore:.4f}, 等级={rlevel}, 原因={reason}")

            prompt = (
                "你是一个金融风控审核助手。根据以下高风险交易评分结果，"
                "生成一段简明的中文审核摘要（100-200字），包括:\n"
                "1. 高风险交易数量和总体风险水平\n"
                "2. 主要风险特征和模式\n"
                "3. 给审核人员的建议\n\n"
                f"高风险交易评分:\n" + "\n".join(score_lines)
            )

            extra_kw = {}
            if "qwen" in model.lower():
                extra_kw["model_kwargs"] = {"extra_body": {"enable_thinking": True}}
            llm = ChatOpenAI(
                api_key=api_key,
                base_url=base_url,
                model=model,
                max_tokens=1500,
                temperature=0.3,
                timeout=45,
                **extra_kw,
            )
            resp = await llm.ainvoke(prompt)
            content = resp.content.strip() if resp.content else ""

            if len(content) >= 20:
                logger.info(
                    f"[RiskReviewAgent] LLM summary generated: "
                    f"{len(content)}c, model={model}"
                )
                return content

            return None
        except Exception as e:
            logger.warning(f"[RiskReviewAgent] LLM summary failed (fallback): {e}")
            return None

    def prepare_review(
        self,
        inp: RiskReviewInput,
        db=None,
    ) -> RiskReviewOutput:
        """
        准备 HITL 审核：为所有 hitl_required=True 的交易创建 review_case。
        db 可选；无 DB 时仍返回 case_id（仅内存，不持久化）。
        """
        if not inp.fraud_result:
            return RiskReviewOutput(
                run_id=inp.run_id,
                summary="无欺诈评分结果，跳过 HITL",
            )

        scores: List[Dict] = inp.fraud_result.get("scores", [])
        hitl_cases = [s for s in scores if s.get("hitl_required")]

        case_ids = []
        for score in hitl_cases:
            tid     = score.get("transaction_id") or str(uuid.uuid4())
            fscore  = float(score.get("final_score", 0))
            rlevel  = score.get("risk_level", "高风险")

            if db:
                case_id = create_review_case_in_db(
                    db, str(inp.run_id or ""), tid, fscore, rlevel,
                    thread_id=inp.thread_id,
                )
            else:
                case_id = str(uuid.uuid4())
                logger.info(
                    f"[RiskReviewAgent] no DB, generated case_id={case_id} "
                    f"tid={tid} score={fscore}"
                )
            case_ids.append(case_id)

        hitl_triggered = len(case_ids) > 0
        summary = (
            f"HITL 已触发：{len(case_ids)} 笔高风险交易等待人工审核"
            if hitl_triggered
            else "无高风险交易需要人工审核"
        )

        logger.info(
            f"[RiskReviewAgent] run_id={inp.run_id} "
            f"hitl={hitl_triggered} cases={len(case_ids)}"
        )

        return RiskReviewOutput(
            run_id=inp.run_id,
            case_ids=case_ids,
            hitl_triggered=hitl_triggered,
            total_high_risk=len([s for s in scores if s.get("risk_level") == "高风险"]),
            pending_count=len(case_ids),
            summary=summary,
        )


risk_review_agent = RiskReviewAgent()
