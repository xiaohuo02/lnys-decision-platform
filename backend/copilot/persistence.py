# -*- coding: utf-8 -*-
"""backend/copilot/persistence.py — 对话持久化 + 历史查询（AsyncSession + ORM）

全量对话持久化到 MySQL，通过 AsyncSession 实现真异步，不阻塞事件循环。
使用 ORM Model（models/copilot.py）替代原始 SQL。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.copilot import (
    CopilotThread, CopilotMessage, CopilotActionLog,
)


def _thread_to_dict(t: CopilotThread) -> Dict[str, Any]:
    return {
        "id": t.id,
        "title": t.title,
        "mode": t.mode,
        "status": t.status,
        "summary": t.summary,
        "page_origin": t.page_origin,
        "tags": t.tags or [],
        "pinned": bool(t.pinned),
        "created_at": str(t.created_at) if t.created_at else None,
        "updated_at": str(t.updated_at) if t.updated_at else None,
    }


def _msg_to_dict(m: CopilotMessage) -> Dict[str, Any]:
    return {
        "id": m.id,
        "role": m.role,
        "content": m.content,
        "intent": m.intent,
        "skills_used": m.skills_used or [],
        "confidence": m.confidence,
        "thinking": m.thinking,
        "artifacts": m.artifacts or [],
        "tool_calls": m.tool_calls or [],
        "suggestions": m.suggestions or [],
        "actions_taken": m.actions_taken or [],
        "feedback": m.feedback,
        "feedback_text": m.feedback_text,
        "elapsed_ms": m.elapsed_ms,
        "token_usage": m.token_usage,
        "source": m.source,
        "created_at": str(m.created_at) if m.created_at else None,
    }


class CopilotPersistence:
    """对话持久化管理器（AsyncSession 版本）"""

    def __init__(self, db: Optional[AsyncSession] = None):
        self._db = db

    # ── Thread 管理 ──

    async def get_or_create_thread(
        self,
        thread_id: str,
        user_id: str,
        mode: str,
        page_origin: Optional[str] = None,
    ) -> Dict[str, Any]:
        if self._db is None:
            return {"id": thread_id, "user_id": user_id, "mode": mode}

        try:
            result = await self._db.execute(
                select(CopilotThread).where(CopilotThread.id == thread_id)
            )
            thread = result.scalar_one_or_none()

            if thread:
                return {"id": thread.id, "title": thread.title, "status": thread.status}

            thread = CopilotThread(
                id=thread_id, user_id=user_id, mode=mode,
                page_origin=page_origin, status="active",
            )
            self._db.add(thread)
            await self._db.commit()
            return {"id": thread_id, "user_id": user_id, "mode": mode, "title": None}
        except Exception as e:
            await self._db.rollback()
            logger.warning(f"[persistence] get_or_create_thread 失败: {e}")
            return {"id": thread_id, "user_id": user_id, "mode": mode}

    async def update_thread_title(self, thread_id: str, title: str) -> None:
        if self._db is None:
            return
        try:
            await self._db.execute(
                update(CopilotThread)
                .where(CopilotThread.id == thread_id, CopilotThread.title.is_(None))
                .values(title=title[:256])
            )
            await self._db.commit()
        except Exception as e:
            await self._db.rollback()
            logger.warning(f"[persistence] update_thread_title 失败: {e}")

    async def update_thread_summary(self, thread_id: str, summary: str) -> None:
        if self._db is None:
            return
        try:
            await self._db.execute(
                update(CopilotThread)
                .where(CopilotThread.id == thread_id)
                .values(summary=summary)
            )
            await self._db.commit()
        except Exception as e:
            await self._db.rollback()
            logger.warning(f"[persistence] update_thread_summary 失败: {e}")

    # ── Message 写入 ──

    async def save_message(
        self,
        thread_id: str,
        role: str,
        content: str,
        intent: Optional[str] = None,
        skills_used: Optional[List[str]] = None,
        confidence: Optional[float] = None,
        thinking: Optional[str] = None,
        artifacts: Optional[list] = None,
        tool_calls: Optional[list] = None,
        suggestions: Optional[list] = None,
        actions_taken: Optional[list] = None,
        elapsed_ms: Optional[int] = None,
        token_usage: Optional[Dict] = None,
        source: str = "web",
    ) -> Optional[int]:
        if self._db is None:
            return None
        try:
            msg = CopilotMessage(
                thread_id=thread_id,
                role=role,
                content=content,
                intent=intent,
                skills_used=skills_used,
                confidence=confidence,
                thinking=thinking,
                artifacts=artifacts,
                tool_calls=tool_calls,
                suggestions=suggestions,
                actions_taken=actions_taken,
                elapsed_ms=elapsed_ms,
                token_usage=token_usage,
                source=source,
            )
            self._db.add(msg)
            await self._db.commit()
            await self._db.refresh(msg)
            return msg.id
        except Exception as e:
            await self._db.rollback()
            logger.warning(f"[persistence] save_message 失败: {e}")
            return None

    # ── Action 审计日志 ──

    async def log_action(
        self,
        thread_id: str,
        message_id: int,
        user_id: str,
        action_type: str,
        target: str,
        payload: Optional[Dict] = None,
        status: str = "pending",
    ) -> Optional[int]:
        if self._db is None:
            return None
        try:
            action = CopilotActionLog(
                thread_id=thread_id, message_id=message_id, user_id=user_id,
                action_type=action_type, target=target,
                payload=payload, status=status,
            )
            self._db.add(action)
            await self._db.commit()
            await self._db.refresh(action)
            return action.id
        except Exception as e:
            await self._db.rollback()
            logger.warning(f"[persistence] log_action 失败: {e}")
            return None

    async def update_action_status(
        self, action_id: int, status: str, result: Optional[Dict] = None
    ) -> None:
        if self._db is None:
            return
        try:
            values: Dict[str, Any] = {"status": status}
            if result is not None:
                values["result"] = result
            values["executed_at"] = func.now()

            await self._db.execute(
                update(CopilotActionLog)
                .where(CopilotActionLog.id == action_id)
                .values(**values)
            )
            await self._db.commit()
        except Exception as e:
            await self._db.rollback()
            logger.warning(f"[persistence] update_action_status 失败: {e}")

    # ── 历史查询 ──

    async def list_threads(
        self,
        user_id: str,
        mode: Optional[str] = None,
        page_origin: Optional[str] = None,
        status: str = "active",
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        if self._db is None:
            return []
        try:
            stmt = (
                select(CopilotThread)
                .where(
                    CopilotThread.user_id == user_id,
                    CopilotThread.status == status,
                )
            )
            if mode:
                stmt = stmt.where(CopilotThread.mode == mode)
            if page_origin:
                stmt = stmt.where(CopilotThread.page_origin == page_origin)

            stmt = (
                stmt
                .order_by(CopilotThread.pinned.desc(), CopilotThread.updated_at.desc())
                .limit(limit)
                .offset(offset)
            )

            result = await self._db.execute(stmt)
            return [_thread_to_dict(t) for t in result.scalars().all()]
        except Exception as e:
            logger.warning(f"[persistence] list_threads 失败: {e}")
            return []

    async def get_thread_messages(
        self, thread_id: str, limit: int = 100, offset: int = 0
    ) -> List[Dict[str, Any]]:
        if self._db is None:
            return []
        try:
            stmt = (
                select(CopilotMessage)
                .where(CopilotMessage.thread_id == thread_id)
                .order_by(CopilotMessage.created_at.asc())
                .limit(limit)
                .offset(offset)
            )
            result = await self._db.execute(stmt)
            return [_msg_to_dict(m) for m in result.scalars().all()]
        except Exception as e:
            logger.warning(f"[persistence] get_thread_messages 失败: {e}")
            return []

    async def set_feedback(
        self, message_id: int, feedback: int, feedback_text: Optional[str] = None
    ) -> None:
        if self._db is None:
            return
        try:
            await self._db.execute(
                update(CopilotMessage)
                .where(CopilotMessage.id == message_id)
                .values(feedback=feedback, feedback_text=feedback_text)
            )
            await self._db.commit()
        except Exception as e:
            await self._db.rollback()
            logger.warning(f"[persistence] set_feedback 失败: {e}")

    async def pin_thread(self, thread_id: str, pinned: bool = True) -> None:
        if self._db is None:
            return
        try:
            await self._db.execute(
                update(CopilotThread)
                .where(CopilotThread.id == thread_id)
                .values(pinned=pinned)
            )
            await self._db.commit()
        except Exception as e:
            await self._db.rollback()
            logger.warning(f"[persistence] pin_thread 失败: {e}")
