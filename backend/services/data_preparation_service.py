# -*- coding: utf-8 -*-
"""backend/services/data_preparation_service.py

DataPreparationService — 数据准备与质量检验服务

╔══════════════════════════════════════════════════════════════════╗
║  Agent 契约                                                       ║
╠══════════════════════════════════════════════════════════════════╣
║  输入   : DataPrepRequest（数据源枚举、日期范围、目标分析模块）      ║
║  输出   : DataPrepResult（质量报告 + 融合数据摘要 + artifact ref） ║
║  可调用 : 文件系统 CSV 读取、pandas 数据处理                        ║
║  禁止   : 直接写 DB、调用 ML 模型推理、对外 HTTP 请求               ║
║  降级   : data_ready=False + 详细 error_message，不抛异常中断流程  ║
║  HITL   : 不需要                                                   ║
║  依赖   : data/processed/{orders,customers,fraud,reviews}.csv     ║
║           data/generated/{inventory,dialogues,faq}.csv           ║
║  Trace  : step_type=SERVICE_CALL, step_name="data_preparation"   ║
║           input_summary=数据源列表                                 ║
║           output_summary=row_count + missing_ratio + data_ready  ║
╚══════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import os
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any

import pandas as pd
import numpy as np
from loguru import logger
from pydantic import BaseModel, Field

from backend.config import settings
from backend.schemas.artifact import ArtifactRef, ArtifactType


# ── 数据根目录 ────────────────────────────────────────────────────
_DATA_ROOT = settings.MODELS_ROOT.parent / "data"
_PROC_DIR  = _DATA_ROOT / "processed"
_GEN_DIR   = _DATA_ROOT / "generated"


class DataSource(str, Enum):
    ORDERS      = "orders"
    CUSTOMERS   = "customers"
    FRAUD       = "fraud"
    REVIEWS     = "reviews"
    INVENTORY   = "inventory"
    DIALOGUES   = "dialogues"
    FAQ         = "faq"
    STORES      = "stores"


_SOURCE_FILE_MAP: Dict[DataSource, Path] = {
    DataSource.ORDERS:    _PROC_DIR / "orders_cn.csv",
    DataSource.CUSTOMERS: _PROC_DIR / "customers_cn.csv",
    DataSource.FRAUD:     _PROC_DIR / "fraud_cn.csv",
    DataSource.REVIEWS:   _PROC_DIR / "reviews_cn.csv",
    DataSource.STORES:    _PROC_DIR / "stores_offline.csv",
    DataSource.INVENTORY: _GEN_DIR  / "inventory.csv",
    DataSource.DIALOGUES: _GEN_DIR  / "dialogues.csv",
    DataSource.FAQ:       _GEN_DIR  / "faq.csv",
}


# ── 请求 / 响应 schema ────────────────────────────────────────────

class DataPrepRequest(BaseModel):
    sources:      List[DataSource] = Field(
        default_factory=lambda: [DataSource.ORDERS, DataSource.CUSTOMERS]
    )
    date_from:    Optional[date] = None
    date_to:      Optional[date] = None
    nrows:        Optional[int] = None       # 限制读取行数（开发/测试用）
    run_id:       Optional[str] = None
    analysis_module: str = "business_overview"  # 调用方说明用途


class ColumnQuality(BaseModel):
    col:           str
    dtype:         str
    missing_count: int
    missing_ratio: float


class SourceQuality(BaseModel):
    source:          DataSource
    file_path:       str
    exists:          bool
    row_count:       int = 0
    col_count:       int = 0
    missing_ratio:   float = 0.0
    duplicate_rows:  int = 0
    columns:         List[ColumnQuality] = Field(default_factory=list)
    error:           Optional[str] = None


class DataPrepResult(BaseModel):
    """DataPreparationService 的标准输出"""
    request_id:      Optional[str]
    analysis_module: str
    sources:         List[DataSource]
    data_ready:      bool
    degraded:        bool = False       # 部分数据源缺失但仍可继续
    quality:         List[SourceQuality]
    overall_row_count:    int = 0
    overall_missing_ratio: float = 0.0
    date_range_applied:  bool = False
    artifact:        Optional[ArtifactRef] = None
    error_message:   Optional[str] = None
    prepared_at:     datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── 服务实现 ──────────────────────────────────────────────────────

class DataPreparationService:
    """
    数据准备与质量检验服务。
    Agent / Workflow 直接实例化并调用 prepare()，不通过 HTTP。
    internal router 仅用于联调触发。
    """

    def prepare(self, request: DataPrepRequest) -> DataPrepResult:
        """
        同步执行数据准备（IO 密集，但当前数据规模下足够快）。
        大规模数据集时可改为 run_in_executor。
        """
        quality_list: List[SourceQuality] = []
        all_errors:   List[str]           = []
        total_rows    = 0
        total_missing_ratios: List[float] = []

        for src in request.sources:
            sq = self._check_source(src, request)
            quality_list.append(sq)
            if sq.exists and not sq.error:
                total_rows += sq.row_count
                total_missing_ratios.append(sq.missing_ratio)
            else:
                all_errors.append(f"{src}: {sq.error or 'file not found'}")

        # 判断整体可用性
        available_sources = [q for q in quality_list if q.exists and not q.error]
        data_ready  = len(available_sources) > 0
        degraded    = len(available_sources) < len(request.sources)

        overall_missing = (
            float(np.mean(total_missing_ratios)) if total_missing_ratios else 0.0
        )

        # 构造 artifact ref（当前阶段仅轻量引用，不写文件）
        artifact = ArtifactRef(
            artifact_type=ArtifactType.DATA_QUALITY,
            run_id=None,
            summary=(
                f"数据准备完成: {len(available_sources)}/{len(request.sources)} 数据源就绪，"
                f"总行数={total_rows:,}，平均缺失率={overall_missing:.1%}"
            ),
        ) if data_ready else None

        result = DataPrepResult(
            request_id=request.run_id,
            analysis_module=request.analysis_module,
            sources=request.sources,
            data_ready=data_ready,
            degraded=degraded,
            quality=quality_list,
            overall_row_count=total_rows,
            overall_missing_ratio=overall_missing,
            date_range_applied=bool(request.date_from or request.date_to),
            artifact=artifact,
            error_message="; ".join(all_errors) if all_errors and not data_ready else None,
        )

        logger.info(
            f"[DataPreparationService] module={request.analysis_module} "
            f"sources={[s.value for s in request.sources]} "
            f"data_ready={data_ready} degraded={degraded} "
            f"rows={total_rows} missing={overall_missing:.2%}"
        )
        return result

    # ── 内部工具方法 ─────────────────────────────────────────────

    def _check_source(
        self, src: DataSource, request: DataPrepRequest
    ) -> SourceQuality:
        path = _SOURCE_FILE_MAP.get(src)
        if path is None:
            return SourceQuality(source=src, file_path="", exists=False, error="未知数据源")

        if not path.exists():
            return SourceQuality(
                source=src, file_path=str(path),
                exists=False, error=f"文件不存在: {path.name}"
            )

        try:
            df = pd.read_csv(
                path,
                nrows=request.nrows,
                low_memory=False,
                parse_dates=self._date_cols(src),
            )

            # 日期过滤（orders / reviews 支持）
            df = self._apply_date_filter(df, src, request)

            # 质量指标
            missing_per_col = df.isnull().mean()
            overall_missing = float(missing_per_col.mean())
            dup_rows        = int(df.duplicated().sum())

            col_quality = [
                ColumnQuality(
                    col=col,
                    dtype=str(df[col].dtype),
                    missing_count=int(df[col].isnull().sum()),
                    missing_ratio=float(df[col].isnull().mean()),
                )
                for col in df.columns
                if df[col].isnull().any()   # 只报告有缺失的列，节省输出
            ]

            return SourceQuality(
                source=src,
                file_path=str(path),
                exists=True,
                row_count=len(df),
                col_count=len(df.columns),
                missing_ratio=overall_missing,
                duplicate_rows=dup_rows,
                columns=col_quality,
            )

        except Exception as e:
            logger.warning(f"[DataPreparationService] 读取 {src} 失败: {e}")
            return SourceQuality(
                source=src, file_path=str(path),
                exists=True, error=str(e)
            )

    @staticmethod
    def _date_cols(src: DataSource) -> Optional[List[str]]:
        _map = {
            DataSource.ORDERS:   ["order_date"],
            DataSource.REVIEWS:  ["review_date"],
        }
        return _map.get(src)

    @staticmethod
    def _apply_date_filter(
        df: pd.DataFrame, src: DataSource, request: DataPrepRequest
    ) -> pd.DataFrame:
        date_col_map = {
            DataSource.ORDERS:  "order_date",
            DataSource.REVIEWS: "review_date",
        }
        col = date_col_map.get(src)
        if col and col in df.columns:
            if request.date_from:
                df = df[df[col] >= pd.Timestamp(request.date_from)]
            if request.date_to:
                df = df[df[col] <= pd.Timestamp(request.date_to)]
        return df


# ── 单例（供 workflow/agent 直接导入）────────────────────────────
data_preparation_service = DataPreparationService()
