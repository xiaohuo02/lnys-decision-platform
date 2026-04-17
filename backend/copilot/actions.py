# -*- coding: utf-8 -*-
"""backend/copilot/actions.py — 可执行 Action 系统

Human-in-the-Loop 原则：所有 Action 需用户确认后执行。
支持风险分级、审批流、审计日志。
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from loguru import logger

from backend.copilot.agent_logger import ActionAuditLogger
from backend.copilot.permissions import (
    PermissionChecker, ActionRisk, ACTION_RISK_LEVELS,
)
from backend.copilot.persistence import CopilotPersistence


class ActionStatus(str, Enum):
    PENDING         = "pending"
    APPROVED        = "approved"
    EXECUTED        = "executed"
    FAILED          = "failed"
    REJECTED        = "rejected"
    PENDING_APPROVAL = "pending_approval"


class ActionExecutor:
    """Action 执行器 — 统一处理所有 Copilot 可执行操作"""

    def __init__(self, db=None, feishu_bridge=None):
        self._db = db
        self._feishu = feishu_bridge
        self._persistence = CopilotPersistence(db=db)
        self._handlers: Dict[str, Any] = {}
        self._register_builtin_handlers()

    def _register_builtin_handlers(self):
        """注册内置 Action 处理器"""
        self._handlers["feishu_notify"] = self._handle_feishu_notify
        self._handlers["feishu_card"] = self._handle_feishu_card
        self._handlers["export_report"] = self._handle_export_report

    async def execute(
        self,
        action_type: str,
        user_id: str,
        user_role: str,
        target: str,
        payload: Optional[Dict[str, Any]] = None,
        thread_id: Optional[str] = None,
        message_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """执行 Action（用户确认后调用）"""
        ActionAuditLogger.log_request(action_type, user_id, target, payload)

        # 1. 权限校验
        if not PermissionChecker.can_execute_action(user_role, action_type):
            ActionAuditLogger.log_rejected(action_type, user_id, "权限不足")
            return {"status": "rejected", "reason": "权限不足"}

        # 2. 风险等级校验
        if PermissionChecker.needs_approval(user_role, action_type):
            risk = PermissionChecker.get_action_risk(action_type)
            # MEDIUM 走"二次确认"，HIGH 走"管理员审批"；DB 状态沿用 pending_approval
            if risk == ActionRisk.MEDIUM:
                message = "该操作为中风险，请二次确认后再执行"
            else:
                message = "该操作为高风险，需要管理员审批"
            # 记录待审批/待确认
            if thread_id and message_id:
                await self._persistence.log_action(
                    thread_id=thread_id, message_id=message_id,
                    user_id=user_id, action_type=action_type,
                    target=target, payload=payload,
                    status="pending_approval",
                )
            ActionAuditLogger.log_request(action_type, user_id, "pending_approval")
            return {
                "status": "pending_approval",
                "risk": risk.value,
                "message": message,
            }

        # 3. 记录审计日志
        action_log_id = None
        if thread_id and message_id:
            action_log_id = await self._persistence.log_action(
                thread_id=thread_id, message_id=message_id,
                user_id=user_id, action_type=action_type,
                target=target, payload=payload,
                status="approved",
            )

        # 4. 执行
        handler = self._handlers.get(action_type)
        if handler is None:
            error = f"未知的 Action 类型: {action_type}"
            ActionAuditLogger.log_failed(action_type, user_id, target, error)
            return {"status": "failed", "error": error}

        try:
            ActionAuditLogger.log_approved(action_type, user_id, target)
            result = await handler(target=target, payload=payload or {}, user_id=user_id)

            # 更新审计日志
            if action_log_id:
                await self._persistence.update_action_status(
                    action_log_id, "executed", result
                )
            ActionAuditLogger.log_executed(action_type, user_id, target, result)
            return {"status": "executed", "result": result}

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            if action_log_id:
                await self._persistence.update_action_status(
                    action_log_id, "failed", {"error": error_msg}
                )
            ActionAuditLogger.log_failed(action_type, user_id, target, error_msg)
            return {"status": "failed", "error": error_msg}

    # ── 内置 Action 处理器 ──

    async def _handle_feishu_notify(
        self, target: str, payload: Dict[str, Any], user_id: str
    ) -> Dict[str, Any]:
        """发送飞书文本消息"""
        if self._feishu is None:
            logger.warning("[ActionExecutor] FeishuBridge 未初始化，跳过发送")
            return {"sent": False, "reason": "飞书未配置"}

        message = payload.get("message", "")
        chat_id = payload.get("chat_id") or target

        try:
            sent = await self._feishu.send_text_async(chat_id, message)
            if not sent:
                raise RuntimeError("飞书发送失败（超时或 API 错误）")
            return {"sent": True, "chat_id": chat_id}
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"飞书发送失败: {e}")

    async def _handle_feishu_card(
        self, target: str, payload: Dict[str, Any], user_id: str
    ) -> Dict[str, Any]:
        """发送飞书交互式卡片"""
        if self._feishu is None:
            return {"sent": False, "reason": "飞书未配置"}

        chat_id = payload.get("chat_id") or target
        title = payload.get("title", "")
        content = payload.get("content", "")
        severity = payload.get("severity", "info")

        try:
            sent = await self._feishu.send_alert_card_async(
                chat_id, title, content, severity
            )
            if not sent:
                raise RuntimeError("飞书卡片发送失败（超时或 API 错误）")
            return {"sent": True, "chat_id": chat_id}
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"飞书卡片发送失败: {e}")

    async def _handle_export_report(
        self, target: str, payload: Dict[str, Any], user_id: str
    ) -> Dict[str, Any]:
        """导出报表（预留接口）"""
        logger.info(f"[ActionExecutor] export_report target={target} payload={payload}")
        return {"exported": True, "path": f"/reports/{target}"}
