# -*- coding: utf-8 -*-
"""backend/repositories/analysis_results_repo.py — Agent 分析结果持久化"""
import json
from typing import Optional
from sqlalchemy.orm import Session
from loguru import logger

from backend.models.business import AnalysisResult


class AnalysisResultsRepo:
    def __init__(self, db: Session):
        self.db = db

    def save(self, module: str, result: dict) -> bool:
        """持久化分析结果。每次写入一条新记录，get_latest() 通过 generated_at DESC 取最新。"""
        try:
            record = AnalysisResult(
                module=module,
                result_json=json.dumps(result, ensure_ascii=False),
            )
            self.db.add(record)
            self.db.commit()
            return True
        except Exception as e:
            self.db.rollback()
            logger.warning(f"[repo:analysis_results] save({module}) failed: {e}")
            return False

    def get_latest(self, module: str) -> Optional[dict]:
        try:
            record = (
                self.db.query(AnalysisResult)
                .filter(AnalysisResult.module == module)
                .order_by(AnalysisResult.generated_at.desc())
                .first()
            )
            return json.loads(record.result_json) if record else None
        except Exception as e:
            logger.warning(f"[repo:analysis_results] get_latest({module}) failed: {e}")
            return None
