# -*- coding: utf-8 -*-
"""backend/models/evaluation.py — 评测体系 ORM Model

对应 init.sql 中 eval_datasets / eval_cases / evaluators /
eval_experiments / eval_results / eval_online_samples。
"""
from sqlalchemy import (
    Column, String, Text, Integer, BigInteger, Boolean,
    Numeric, JSON, Enum as SAEnum, Index, ForeignKey, func,
)
from sqlalchemy.dialects.mysql import DATETIME as MySQLDateTime
from sqlalchemy.orm import relationship

from backend.database import Base


class EvalDataset(Base):
    __tablename__ = "eval_datasets"

    dataset_id = Column(String(36), primary_key=True, comment="UUID")
    name = Column(String(100), nullable=False)
    description = Column(Text, default=None)
    task_type = Column(String(50), nullable=False, comment="routing/qa/risk_scoring/...")
    item_count = Column(Integer, default=0)
    created_by = Column(String(100), nullable=False)
    created_at = Column(MySQLDateTime(fsp=3), nullable=False, server_default=func.now())

    cases = relationship("EvalCase", back_populates="dataset", cascade="all, delete-orphan")


class EvalCase(Base):
    __tablename__ = "eval_cases"

    case_id = Column(String(36), primary_key=True, comment="UUID")
    dataset_id = Column(String(36), ForeignKey("eval_datasets.dataset_id", ondelete="CASCADE"), nullable=False)
    input_json = Column(JSON, nullable=False)
    expected_json = Column(JSON, nullable=False)
    tags = Column(JSON, default=None)
    created_at = Column(MySQLDateTime(fsp=3), nullable=False, server_default=func.now())

    dataset = relationship("EvalDataset", back_populates="cases")


class Evaluator(Base):
    __tablename__ = "evaluators"

    evaluator_id = Column(String(36), primary_key=True, comment="UUID")
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text, default=None)
    task_type = Column(String(50), nullable=False)
    scoring_rules = Column(JSON, nullable=False)
    version = Column(Integer, default=1)
    created_by = Column(String(100), nullable=False)
    created_at = Column(MySQLDateTime(fsp=3), nullable=False, server_default=func.now())


class EvalExperiment(Base):
    __tablename__ = "eval_experiments"

    experiment_id = Column(String(36), primary_key=True, comment="UUID")
    name = Column(String(100), nullable=False)
    dataset_id = Column(String(36), ForeignKey("eval_datasets.dataset_id"), nullable=False)
    evaluator_id = Column(String(36), ForeignKey("evaluators.evaluator_id"), nullable=False)
    target_type = Column(String(50), default=None, comment="prompt/workflow/agent")
    target_id = Column(String(36), default=None)
    target_version = Column(String(50), default=None)
    status = Column(
        SAEnum("pending", "running", "completed", "failed", name="eval_status_enum"),
        nullable=False, default="pending",
    )
    total_cases = Column(Integer, default=0)
    pass_rate = Column(Numeric(5, 4), default=None, comment="通过率 0~1")
    created_by = Column(String(100), nullable=False)
    created_at = Column(MySQLDateTime(fsp=3), nullable=False, server_default=func.now())
    ended_at = Column(MySQLDateTime(fsp=3), default=None)

    results = relationship("EvalResult", back_populates="experiment", cascade="all, delete-orphan")


class EvalResult(Base):
    __tablename__ = "eval_results"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    experiment_id = Column(String(36), ForeignKey("eval_experiments.experiment_id", ondelete="CASCADE"), nullable=False)
    case_id = Column(String(36), nullable=False)
    actual_json = Column(JSON, nullable=False)
    score = Column(Numeric(5, 4), default=None)
    passed = Column(Boolean, default=None)
    detail_json = Column(JSON, default=None)
    created_at = Column(MySQLDateTime(fsp=3), nullable=False, server_default=func.now())

    experiment = relationship("EvalExperiment", back_populates="results")


class EvalOnlineSample(Base):
    __tablename__ = "eval_online_samples"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    import_batch = Column(String(64), nullable=False, comment="导入批次标识")
    source_run_id = Column(String(36), default=None)
    input_json = Column(JSON, nullable=False)
    label_json = Column(JSON, default=None)
    source_note = Column(Text, default=None)
    imported_at = Column(MySQLDateTime(fsp=3), nullable=False, server_default=func.now())
