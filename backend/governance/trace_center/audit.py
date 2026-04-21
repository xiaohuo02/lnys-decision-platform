# -*- coding: utf-8 -*-
"""backend/governance/trace_center/audit.py

审计日志写入工具
- write_audit_log：写入 audit_logs 表
- 所有 Prompt/Policy 发布、Review 审批、Release 回滚、高风险修改均需调用
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

import sqlalchemy
from loguru import logger
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession


def write_audit_log(
    db:          Session,
    operator:    str,
    action:      str,
    target_type: str,
    target_id:   str,
    before:      Optional[Dict[str, Any]] = None,
    after:       Optional[Dict[str, Any]] = None,
    ip_address:  Optional[str] = None,
    user_agent:  Optional[str] = None,
) -> None:
    """向 audit_logs 写入一条审计记录（失败不阻塞主流程）"""
    sql = """
        INSERT INTO audit_logs
            (operator, action, target_type, target_id,
             before_json, after_json, ip_address, user_agent)
        VALUES
            (:operator, :action, :target_type, :target_id,
             :before_json, :after_json, :ip_address, :user_agent)
    """
    try:
        db.execute(
            sqlalchemy.text(sql),
            {
                "operator":    operator,
                "action":      action,
                "target_type": target_type,
                "target_id":   str(target_id),
                "before_json": json.dumps(before, ensure_ascii=False, default=str) if before else None,
                "after_json":  json.dumps(after,  ensure_ascii=False, default=str) if after  else None,
                "ip_address":  ip_address,
                "user_agent":  user_agent,
            },
        )
        db.commit()
    except Exception as e:
        logger.warning(f"[audit] write_audit_log failed (non-fatal): {e}")


async def async_write_audit_log(
    db:          AsyncSession,
    operator:    str,
    action:      str,
    target_type: str,
    target_id:   str,
    before:      Optional[Dict[str, Any]] = None,
    after:       Optional[Dict[str, Any]] = None,
    ip_address:  Optional[str] = None,
    user_agent:  Optional[str] = None,
) -> None:
    """异步版本：向 audit_logs 写入一条审计记录（失败不阻塞主流程）"""
    sql = """
        INSERT INTO audit_logs
            (operator, action, target_type, target_id,
             before_json, after_json, ip_address, user_agent)
        VALUES
            (:operator, :action, :target_type, :target_id,
             :before_json, :after_json, :ip_address, :user_agent)
    """
    try:
        await db.execute(
            sqlalchemy.text(sql),
            {
                "operator":    operator,
                "action":      action,
                "target_type": target_type,
                "target_id":   str(target_id),
                "before_json": json.dumps(before, ensure_ascii=False, default=str) if before else None,
                "after_json":  json.dumps(after,  ensure_ascii=False, default=str) if after  else None,
                "ip_address":  ip_address,
                "user_agent":  user_agent,
            },
        )
        await db.commit()
    except Exception as e:
        logger.warning(f"[audit] async_write_audit_log failed (non-fatal): {e}")
