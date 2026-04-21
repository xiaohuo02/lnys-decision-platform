# -*- coding: utf-8 -*-
"""backend/services/customer_intelligence_service.py

CustomerIntelligenceService — 客户洞察服务

╔══════════════════════════════════════════════════════════════════╗
║  Agent 契约                                                       ║
╠══════════════════════════════════════════════════════════════════╣
║  输入   : CustomerIntelRequest（分析类型、客户筛选、topN）          ║
║  输出   : CustomerIntelResult（RFM 分布、流失风险、CLV 摘要 + ref）║
║  可调用 : 读取 models/results/customer/*.csv + models/artifacts  ║
║            pandas 计算、pickle 模型推理                            ║
║  禁止   : 重新训练模型、直接写 DB、对外 HTTP 请求                   ║
║  降级   : 无法加载模型时跳过该分析项，标记 degraded=True            ║
║  HITL   : 不需要                                                   ║
║  依赖   : models/results/customer/rfm_result.csv                  ║
║           models/results/customer/clustering_result.csv          ║
║           models/results/customer/clv_result.csv                 ║
║           models/artifacts/customer/churn_xgb.pkl（可选）         ║
║  Trace  : step_type=SERVICE_CALL, step_name="customer_intel"     ║
║           output_summary=高价值/流失预警客户数 + 整体分群摘要       ║
╚══════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from loguru import logger
from pydantic import BaseModel, Field

from backend.config import settings
from backend.schemas.artifact import ArtifactRef, ArtifactType


# ── 路径 ──────────────────────────────────────────────────────────
_RESULTS  = settings.MODELS_ROOT / "results"  / "customer"
_ARTIFACTS= settings.ART_CUSTOMER


# ── 请求 / 响应 schema ────────────────────────────────────────────

class AnalysisType(str):
    pass

ANALYSIS_RFM         = "rfm"
ANALYSIS_CHURN       = "churn"
ANALYSIS_CLV         = "clv"
ANALYSIS_CLUSTER     = "cluster"
ANALYSIS_ALL         = "all"


class CustomerIntelRequest(BaseModel):
    analysis_types: List[str] = Field(
        default_factory=lambda: [ANALYSIS_RFM, ANALYSIS_CHURN, ANALYSIS_CLV]
    )
    top_n:         int = 10          # 返回 Top N 流失风险/高价值客户
    run_id:        Optional[str] = None
    segment_filter: Optional[str] = None  # 可选：仅分析某个客户分群


class SegmentDistribution(BaseModel):
    segment:     str
    count:       int
    percentage:  float


class TopCustomer(BaseModel):
    customer_id: str
    score:       float
    segment:     Optional[str] = None
    extra:       Dict[str, Any] = Field(default_factory=dict)


class CustomerIntelResult(BaseModel):
    """CustomerIntelligenceService 的标准输出"""
    run_id:            Optional[str]
    analysis_types:    List[str]
    data_ready:        bool
    degraded:          bool = False

    # RFM
    rfm_segment_distribution: List[SegmentDistribution] = Field(default_factory=list)
    rfm_total_customers:       int = 0

    # 流失预警
    churn_top_risk:            List[TopCustomer] = Field(default_factory=list)
    churn_high_risk_count:     int = 0
    churn_high_risk_ratio:     float = 0.0

    # CLV
    clv_top_customers:         List[TopCustomer] = Field(default_factory=list)
    clv_avg_90d:               float = 0.0
    clv_median_90d:            float = 0.0

    # 分群
    cluster_count:             int = 0
    cluster_distribution:      List[SegmentDistribution] = Field(default_factory=list)

    artifact:          Optional[ArtifactRef] = None
    error_message:     Optional[str] = None
    analyzed_at:       datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── 服务实现 ──────────────────────────────────────────────────────

class CustomerIntelligenceService:
    """
    读取 ml/ 目录下 pre-computed 结果文件，
    封装成结构化输出供 workflow / InsightComposerAgent 调用。
    """

    def analyze(self, request: CustomerIntelRequest) -> CustomerIntelResult:
        errors:  List[str] = []
        result   = CustomerIntelResult(
            run_id=request.run_id,
            analysis_types=request.analysis_types,
            data_ready=False,
        )
        types = set(request.analysis_types)
        if ANALYSIS_ALL in types:
            types = {ANALYSIS_RFM, ANALYSIS_CHURN, ANALYSIS_CLV, ANALYSIS_CLUSTER}

        any_success = False

        # RFM 是基础数据（客户总数、分群分布），始终加载
        ok, err = self._load_rfm(result, request, types)
        if ok: any_success = True
        if err: errors.append(err)

        if ANALYSIS_CHURN in types:
            ok, err = self._load_churn(result, request)
            if ok: any_success = True
            if err: errors.append(err)

        if ANALYSIS_CLV in types:
            ok, err = self._load_clv(result, request)
            if ok: any_success = True
            if err: errors.append(err)

        result.data_ready = any_success
        result.degraded   = bool(errors) and any_success

        if any_success:
            result.artifact = ArtifactRef(
                artifact_type=ArtifactType.CUSTOMER_INSIGHT,
                run_id=None,
                summary=(
                    f"客户洞察: {result.rfm_total_customers} 名客户, "
                    f"流失高风险 {result.churn_high_risk_count} 人 "
                    f"({result.churn_high_risk_ratio:.1%}), "
                    f"平均 CLV(90d)={result.clv_avg_90d:.1f}"
                ),
            )
        if errors and not any_success:
            result.error_message = "; ".join(errors)

        logger.info(
            f"[CustomerIntelService] types={list(types)} "
            f"rfm_total={result.rfm_total_customers} "
            f"churn_high_risk={result.churn_high_risk_count} "
            f"data_ready={result.data_ready} degraded={result.degraded}"
        )
        return result

    # ── RFM + Cluster ─────────────────────────────────────────────

    def _load_rfm(
        self,
        result: CustomerIntelResult,
        request: CustomerIntelRequest,
        types: set,
    ) -> tuple[bool, Optional[str]]:
        try:
            rfm_path = _RESULTS / "rfm_result.csv"
            cluster_path = _RESULTS / "clustering_result.csv"

            src = cluster_path if cluster_path.exists() else rfm_path
            if not src.exists():
                return False, f"RFM 结果文件不存在: {rfm_path.name}"

            df = pd.read_csv(src, low_memory=False)

            if request.segment_filter and "segment" in df.columns:
                filt = request.segment_filter
                mask = df["segment"].str.contains(filt, na=False)
                if mask.any():
                    df = df[mask]
                else:
                    logger.warning(
                        f"[CustomerIntelService] segment_filter='{filt}' "
                        f"未匹配任何客户，回退到全量数据"
                    )

            result.rfm_total_customers = len(df)

            if "segment" in df.columns:
                seg_cnt = df["segment"].value_counts()
                total   = len(df)
                result.rfm_segment_distribution = [
                    SegmentDistribution(
                        segment=seg,
                        count=int(cnt),
                        percentage=round(cnt / total, 4),
                    )
                    for seg, cnt in seg_cnt.items()
                ]

            if ANALYSIS_CLUSTER in types and "cluster" in df.columns:
                cl_cnt = df["cluster"].value_counts()
                result.cluster_count = int(df["cluster"].nunique())
                result.cluster_distribution = [
                    SegmentDistribution(
                        segment=f"cluster_{cl}",
                        count=int(cnt),
                        percentage=round(cnt / len(df), 4),
                    )
                    for cl, cnt in cl_cnt.items()
                ]

            return True, None
        except Exception as e:
            logger.warning(f"[CustomerIntelService] RFM 加载失败: {e}")
            return False, f"RFM: {e}"

    # ── 流失预警 ──────────────────────────────────────────────────

    def _load_churn(
        self,
        result: CustomerIntelResult,
        request: CustomerIntelRequest,
    ) -> tuple[bool, Optional[str]]:
        try:
            path = _RESULTS / "churn_result.csv"
            if not path.exists():
                # 无预计算结果时尝试用模型文件推断（简化版）
                return self._infer_churn_from_model(result, request)

            df = pd.read_csv(path)
            if "pred_proba" not in df.columns:
                return False, "churn_result.csv 缺少 pred_proba 列"

            high_risk = df[df["pred_proba"] >= 0.7]
            result.churn_high_risk_count = len(high_risk)
            result.churn_high_risk_ratio = round(len(high_risk) / max(len(df), 1), 4)

            top_n = df.nlargest(request.top_n, "pred_proba")
            result.churn_top_risk = [
                TopCustomer(
                    customer_id=str(row.get("customer_id", f"cust_{i}")),
                    score=round(float(row["pred_proba"]), 4),
                )
                for i, (_, row) in enumerate(top_n.iterrows())
            ]
            return True, None
        except Exception as e:
            logger.warning(f"[CustomerIntelService] churn 加载失败: {e}")
            return False, f"churn: {e}"

    def _infer_churn_from_model(
        self, result: CustomerIntelResult, request: CustomerIntelRequest
    ) -> tuple[bool, Optional[str]]:
        """当无预计算结果时，尝试加载模型进行有限推断"""
        model_path = _ARTIFACTS / "churn_xgb.pkl"
        if not model_path.exists():
            return False, "churn_xgb.pkl 不存在，无法进行流失预测"
        # 无完整特征数据，降级跳过推断
        return False, "churn: 无预计算结果且无输入特征，跳过"

    # ── CLV ───────────────────────────────────────────────────────

    def _load_clv(
        self,
        result: CustomerIntelResult,
        request: CustomerIntelRequest,
    ) -> tuple[bool, Optional[str]]:
        try:
            path = _RESULTS / "clv_result.csv"
            if not path.exists():
                return False, f"clv_result.csv 不存在: {path}"

            df = pd.read_csv(path)
            if "clv_90d" not in df.columns:
                return False, "clv_result.csv 缺少 clv_90d 列"

            df = df[df["clv_90d"] > 0]
            result.clv_avg_90d    = round(float(df["clv_90d"].mean()), 2)
            result.clv_median_90d = round(float(df["clv_90d"].median()), 2)

            top_n = df.nlargest(request.top_n, "clv_90d")
            result.clv_top_customers = [
                TopCustomer(
                    customer_id=str(row.get("customer_id", f"cust_{i}")),
                    score=round(float(row["clv_90d"]), 2),
                    extra={
                        "pred_purchases_90d": round(float(row.get("pred_purchases_90d", 0)), 2),
                    },
                )
                for i, (_, row) in enumerate(top_n.iterrows())
            ]
            return True, None
        except Exception as e:
            logger.warning(f"[CustomerIntelService] CLV 加载失败: {e}")
            return False, f"clv: {e}"


# ── 单例 ──────────────────────────────────────────────────────────
customer_intelligence_service = CustomerIntelligenceService()
