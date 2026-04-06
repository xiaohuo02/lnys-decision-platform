# -*- coding: utf-8 -*-
"""backend/repositories/chat_repo.py — 对话消息 CRUD"""
from typing import Optional
from sqlalchemy.orm import Session
from loguru import logger

from backend.models.business import ChatMessage


class ChatRepo:
    def __init__(self, db: Session):
        self.db = db

    def insert_pair(
        self,
        session_id: str,
        user_msg: str,
        bot_reply: str,
        intent: Optional[str] = None,
        confidence: Optional[float] = None,
    ) -> bool:
        try:
            self.db.add(ChatMessage(
                session_id=session_id, role="user",
                content=user_msg, intent=None, confidence=None,
            ))
            self.db.add(ChatMessage(
                session_id=session_id, role="bot",
                content=bot_reply, intent=intent, confidence=confidence,
            ))
            self.db.commit()
            return True
        except Exception as e:
            self.db.rollback()
            logger.warning(f"[repo:chat] insert_pair failed: {e}")
            return False

    def delete_session(self, session_id: str) -> int:
        try:
            count = (
                self.db.query(ChatMessage)
                .filter(ChatMessage.session_id == session_id)
                .delete()
            )
            self.db.commit()
            return count
        except Exception as e:
            self.db.rollback()
            logger.warning(f"[repo:chat] delete_session failed: {e}")
            return 0

    def get_history(self, session_id: str) -> list[dict]:
        try:
            rows = (
                self.db.query(ChatMessage)
                .filter(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.id.asc())
                .all()
            )
            return [
                {
                    "id":         r.id,
                    "role":       r.role,
                    "content":    r.content,
                    "intent":     r.intent,
                    "confidence": float(r.confidence) if r.confidence is not None else None,
                    "created_at": str(r.created_at) if r.created_at else None,
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning(f"[repo:chat] get_history failed: {e}")
            return []
