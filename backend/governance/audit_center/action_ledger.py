# -*- coding: utf-8 -*-
"""backend/governance/audit_center/action_ledger.py

Action Ledger — 高风险操作幂等账本
- 所有高风险写操作（冻结订单、退款、风控状态修改、Prompt/Policy 发布、回滚）
  必须先通过 create_ledger_entry 创建账本记录
- 幂等键确保同一操作不重复执行
- 执行后调用 complete_entry 或 fail_entry 更新状态
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

import sqlalchemy
from loguru import logger
from sqlalchemy.orm import Session


class DuplicateActionError(Exception):
    """幂等键已存在，操作已执行或正在执行"""
    pass


def _make_idempotency_key(
    action_type: str,
    target_type: str,
    target_id:   str,
    suffix:      Optional[str] = None,
) -> str:
    """生成幂等键（可复现，同一操作产生同一 key）"""
    raw = f"{action_type}:{target_type}:{target_id}"
    if suffix:
        raw += f":{suffix}"
    return hashlib.sha256(raw.encode()).hexdigest()[:64]


def create_ledger_entry(
    db:           Session,
    action_type:  str,
    target_type:  str,
    target_id:    str,
    requested_by: str,
    payload:      Optional[Dict[str, Any]] = None,
    idempotency_suffix: Optional[str] = None,
) -> str:
    """
    创建 action ledger 条目。
    如幂等键已存在且状态为 completed/executing，则抛出 DuplicateActionError。
    返回 idempotency_key（供后续 complete/fail 使用）。
    """
    ikey = _make_idempotency_key(
        action_type, target_type, target_id, idempotency_suffix
    )

    # 检查幂等
    existing = db.execute(
        sqlalchemy.text(
            "SELECT status FROM action_ledgers WHERE idempotency_key = :key"
        ),
        {"key": ikey},
    ).fetchone()

    if existing:
        status = existing[0]
        if status in ("completed", "executing"):
            raise DuplicateActionError(
                f"幂等键已存在 (status={status}): key={ikey[:16]}..."
            )
        # 状态为 pending/failed/rejected 时允许重试：更新即可
        db.execute(
            sqlalchemy.text(
                "UPDATE action_ledgers SET status='pending', "
                "requested_by=:requested_by, updated_at=NOW() "
                "WHERE idempotency_key=:key"
            ),
            {"requested_by": requested_by, "key": ikey},
        )
        db.commit()
        logger.info(f"[ActionLedger] retry entry key={ikey[:16]} action={action_type}")
        return ikey

    # 新建条目
    db.execute(
        sqlalchemy.text("""
            INSERT INTO action_ledgers
                (action_type, target_type, target_id, idempotency_key,
                 requested_by, status, payload_json)
            VALUES
                (:action_type, :target_type, :target_id, :ikey,
                 :requested_by, 'pending', :payload_json)
        """),
        {
            "action_type":  action_type,
            "target_type":  target_type,
            "target_id":    str(target_id),
            "ikey":         ikey,
            "requested_by": requested_by,
            "payload_json": json.dumps(payload, ensure_ascii=False) if payload else None,
        },
    )
    db.commit()
    logger.info(f"[ActionLedger] created key={ikey[:16]} action={action_type} target={target_type}/{target_id}")
    return ikey


def complete_entry(
    db:             Session,
    idempotency_key: str,
    approved_by:    Optional[str] = None,
    result_summary: Optional[str] = None,
) -> None:
    db.execute(
        sqlalchemy.text("""
            UPDATE action_ledgers
            SET status='completed', approved_by=:approved_by,
                result_summary=:summary, updated_at=NOW()
            WHERE idempotency_key=:key
        """),
        {"approved_by": approved_by, "summary": result_summary, "key": idempotency_key},
    )
    db.commit()
    logger.info(f"[ActionLedger] completed key={idempotency_key[:16]}")


def fail_entry(
    db:             Session,
    idempotency_key: str,
    result_summary: Optional[str] = None,
) -> None:
    db.execute(
        sqlalchemy.text("""
            UPDATE action_ledgers
            SET status='failed', result_summary=:summary, updated_at=NOW()
            WHERE idempotency_key=:key
        """),
        {"summary": result_summary, "key": idempotency_key},
    )
    db.commit()
    logger.warning(f"[ActionLedger] failed key={idempotency_key[:16]} reason={result_summary}")


def reject_entry(
    db:             Session,
    idempotency_key: str,
    result_summary: Optional[str] = None,
) -> None:
    db.execute(
        sqlalchemy.text("""
            UPDATE action_ledgers
            SET status='rejected', result_summary=:summary, updated_at=NOW()
            WHERE idempotency_key=:key
        """),
        {"summary": result_summary, "key": idempotency_key},
    )
    db.commit()
    logger.info(f"[ActionLedger] rejected key={idempotency_key[:16]}")
