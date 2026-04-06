# -*- coding: utf-8 -*-
"""backend/repositories/fraud_repo.py — 欺诈记录 CRUD"""
from sqlalchemy import func, case, cast, Date
from sqlalchemy.orm import Session
from loguru import logger

from backend.models.business import FraudRecord


class FraudRepo:
    def __init__(self, db: Session):
        self.db = db

    def insert(
        self,
        transaction_id: str,
        risk_score: float,
        risk_level: str,
        rule_triggered: bool,
    ) -> bool:
        try:
            existing = self.db.query(FraudRecord).filter(
                FraudRecord.transaction_id == transaction_id
            ).first()
            if existing is None:
                self.db.add(FraudRecord(
                    transaction_id=transaction_id,
                    risk_score=risk_score,
                    risk_level=risk_level,
                    rule_triggered=rule_triggered,
                ))
                self.db.commit()
            return True
        except Exception as e:
            self.db.rollback()
            logger.warning(f"[repo:fraud] insert failed: {e}")
            return False

    def today_stats(self) -> dict:
        """今日风控统计（聚合查询保留 ORM 表达式，符合 SQL-first 原则）"""
        try:
            row = self.db.query(
                func.count().label("total"),
                func.sum(case((FraudRecord.risk_level == "高风险", 1), else_=0)).label("high"),
                func.sum(case((FraudRecord.risk_level == "中风险", 1), else_=0)).label("mid"),
            ).filter(
                cast(FraudRecord.detected_at, Date) == func.curdate()
            ).first()
            total = int(row.total or 0)
            high  = int(row.high or 0)
            mid   = int(row.mid or 0)
            return {
                "today_total":     total,
                "today_blocked":   high + mid,
                "block_rate":      round((high + mid) / total, 4) if total else 0.0,
                "high_risk_count": high,
                "mid_risk_count":  mid,
            }
        except Exception as e:
            logger.warning(f"[repo:fraud] today_stats failed: {e}")
            return {}
