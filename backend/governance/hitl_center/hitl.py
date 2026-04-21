# -*- coding: utf-8 -*-
"""backend/governance/hitl_center/hitl.py

HITL Center — 人工干预中心核心模块
- 查询待审核列表
- 查询审核案例详情
- 执行审批动作（approve / edit / reject）
- 与 action ledger 联动（高风险写操作）
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import sqlalchemy
from loguru import logger
from sqlalchemy.orm import Session

from backend.core.exceptions import (
    AppError,
    ConflictError,
    ResourceNotFoundError,
)


_MUTABLE_CASE_STATUSES = ("pending", "in_review")


# ── 写入 ────────────────────────────────────────────────────────

def create_review_case(
    db:          Session,
    run_id:      str,
    review_type: str,
    subject:     str,
    context:     Optional[Dict[str, Any]] = None,
    priority:    str = "high",
    created_by:  str = "system",
) -> str:
    """创建一条 HITL 审核案例，返回 case_id。失败时抛出异常由调用方决定处理策略。"""
    case_id = str(uuid.uuid4())
    db.execute(sqlalchemy.text("""
        INSERT INTO review_cases
            (case_id, run_id, review_type, priority, status, subject, context_json, created_by)
        VALUES
            (:case_id, :run_id, :review_type, :priority, 'pending',
             :subject, :context_json, :created_by)
    """), {
        "case_id":      case_id,
        "run_id":       run_id,
        "review_type":  review_type,
        "priority":     priority,
        "subject":      subject,
        "context_json": json.dumps(context or {}, ensure_ascii=False),
        "created_by":   created_by,
    })
    db.commit()
    logger.info(f"[HITL] created case_id={case_id} type={review_type} run_id={run_id}")
    return case_id


def get_case_by_run_id(
    db:          Session,
    run_id:      str,
    review_type: Optional[str] = None,
) -> Optional[Dict]:
    """通过 run_id（即 thread_id）查找尚未完结的审核案例。"""
    extra = " AND review_type = :review_type" if review_type else ""
    params: Dict[str, Any] = {"run_id": run_id}
    if review_type:
        params["review_type"] = review_type
    row = db.execute(
        sqlalchemy.text(
            f"SELECT case_id, status, context_json FROM review_cases "
            f"WHERE run_id = :run_id{extra} "
            f"AND status IN ('pending', 'in_review') LIMIT 1"
        ),
        params,
    ).fetchone()
    return dict(row._mapping) if row else None


def list_pending_by_type(
    db:          Session,
    review_type: str,
    limit:       int = 100,
) -> List[Dict]:
    """查询指定类型的待审核案例列表，用于业务 API 端（如欺诈审核队列）。"""
    rows = db.execute(
        sqlalchemy.text(
            "SELECT case_id, run_id, status, subject, context_json, created_at "
            "FROM review_cases "
            "WHERE review_type = :review_type AND status IN ('pending', 'in_review') "
            "ORDER BY created_at DESC LIMIT :limit"
        ),
        {"review_type": review_type, "limit": limit},
    ).fetchall()
    return [dict(r._mapping) for r in rows]


# ── 查询 ────────────────────────────────────────────────────────

def list_review_cases(
    db:          Session,
    status:      Optional[str] = None,
    priority:    Optional[str] = None,
    review_type: Optional[str] = None,
    limit:       int = 50,
    offset:      int = 0,
) -> List[Dict]:
    filters = "WHERE 1=1"
    params: Dict[str, Any] = {"limit": limit, "offset": offset}
    if status:
        filters += " AND status = :status"
        params["status"] = status
    if priority:
        filters += " AND priority = :priority"
        params["priority"] = priority
    if review_type:
        filters += " AND review_type = :review_type"
        params["review_type"] = review_type

    rows = db.execute(
        sqlalchemy.text(
            f"SELECT case_id, run_id, review_type, priority, status, "
            f"subject, created_by, assigned_to, created_at, updated_at "
            f"FROM review_cases {filters} "
            f"ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
        ),
        params,
    ).fetchall()
    return [dict(r._mapping) for r in rows]


def get_review_case(db: Session, case_id: str) -> Optional[Dict]:
    row = db.execute(
        sqlalchemy.text(
            "SELECT * FROM review_cases WHERE case_id = :case_id"
        ),
        {"case_id": case_id},
    ).fetchone()
    if row is None:
        return None
    case = dict(row._mapping)

    # 附带审批动作历史
    actions = db.execute(
        sqlalchemy.text(
            "SELECT * FROM review_actions WHERE case_id = :case_id ORDER BY created_at"
        ),
        {"case_id": case_id},
    ).fetchall()
    case["actions"] = [dict(a._mapping) for a in actions]
    return case


# ── 审批动作 ─────────────────────────────────────────────────────

def _check_case_exists(db: Session, case_id: str) -> Dict:
    row = db.execute(
        sqlalchemy.text("SELECT case_id, status FROM review_cases WHERE case_id = :id"),
        {"id": case_id},
    ).fetchone()
    if row is None:
        raise ResourceNotFoundError(f"review case {case_id} 不存在")
    return dict(row._mapping)


def _apply_case_decision(
    db: Session,
    *,
    case_id: str,
    action_type: str,
    next_status: str,
    decision_by: str,
    note: Optional[str],
    failure_message: str,
    action_label: str,
    override_payload: Optional[Dict[str, Any]] = None,
) -> str:
    action_id = str(uuid.uuid4())
    payload = json.dumps(override_payload, ensure_ascii=False) if override_payload is not None else None

    try:
        case = _check_case_exists(db, case_id)
        if case["status"] not in _MUTABLE_CASE_STATUSES:
            raise ConflictError(f"case {case_id} 状态为 {case['status']}，不可{action_label}")

        update_result = db.execute(
            sqlalchemy.text(
                "UPDATE review_cases SET status=:status, updated_at=NOW() "
                "WHERE case_id=:id AND status IN ('pending', 'in_review')"
            ),
            {"id": case_id, "status": next_status},
        )
        if (update_result.rowcount or 0) != 1:
            raise ConflictError(f"case {case_id} 状态已变化，请刷新后重试")

        db.execute(
            sqlalchemy.text(
                """
                INSERT INTO review_actions
                    (action_id, case_id, action_type, decision_by, decision_note, override_payload)
                VALUES
                    (:action_id, :case_id, :action_type, :decision_by, :note, :payload)
                """
            ),
            {
                "action_id": action_id,
                "case_id": case_id,
                "action_type": action_type,
                "decision_by": decision_by,
                "note": note,
                "payload": payload,
            },
        )
        db.commit()
    except (ConflictError, ResourceNotFoundError):
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"[HITL] {action_type} failed: case_id={case_id} {e}")
        raise AppError(500, failure_message)

    logger.info(f"[HITL] {action_type} case_id={case_id} by={decision_by}")
    return action_id


def approve_case(
    db:          Session,
    case_id:     str,
    decision_by: str,
    note:        Optional[str] = None,
) -> str:
    return _apply_case_decision(
        db,
        case_id=case_id,
        action_type="approve",
        next_status="approved",
        decision_by=decision_by,
        note=note,
        failure_message="审批操作失败",
        action_label="审批",
    )


def edit_case(
    db:              Session,
    case_id:         str,
    decision_by:     str,
    override_payload: Dict[str, Any],
    note:             Optional[str] = None,
) -> str:
    action_id = _apply_case_decision(
        db,
        case_id=case_id,
        action_type="edit",
        next_status="edited",
        decision_by=decision_by,
        note=note,
        failure_message="修改操作失败",
        action_label="修改",
        override_payload=override_payload,
    )
    logger.info(f"[HITL] edit payload_keys={list(override_payload)} case_id={case_id}")
    return action_id


def reject_case(
    db:          Session,
    case_id:     str,
    decision_by: str,
    note:        Optional[str] = None,
) -> str:
    return _apply_case_decision(
        db,
        case_id=case_id,
        action_type="reject",
        next_status="rejected",
        decision_by=decision_by,
        note=note,
        failure_message="拒绝操作失败",
        action_label="拒绝",
    )
