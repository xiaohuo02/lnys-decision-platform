# -*- coding: utf-8 -*-
"""backend/services/association_mining_service.py

AssociationMiningService — 关联分析与商品推荐服务

╔══════════════════════════════════════════════════════════════════╗
║  Agent 契约                                                       ║
╠══════════════════════════════════════════════════════════════════╣
║  输入   : AssociationRequest（SKU 列表、topN、min_lift）          ║
║  输出   : AssociationResult（推荐规则、Top 关联组合 + ref）        ║
║  可调用 : models/results/ops/association_rules.csv 读取           ║
║  禁止   : 重新挖掘规则（计算密集）、直接写 DB、调用 LLM            ║
║  降级   : 无规则文件时返回空推荐，data_ready=False                 ║
║  HITL   : 不需要                                                   ║
║  依赖   : models/results/ops/association_rules.csv               ║
║  Trace  : step_name="association_mining"                         ║
║           output_summary=rule_count + top_lift                   ║
╚══════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

import pandas as pd
from loguru import logger
from pydantic import BaseModel, Field

from backend.config import settings
from backend.schemas.artifact import ArtifactRef, ArtifactType


_RULES_CSV = settings.MODELS_ROOT / "results" / "ops" / "association_rules.csv"


class AssociationRequest(BaseModel):
    run_id:       Optional[str] = None
    sku_codes:    Optional[List[str]] = None   # 查询这些 SKU 的关联推荐
    top_n:        int   = 10
    min_lift:     float = 1.2
    min_confidence: float = 0.3


class AssociationRule(BaseModel):
    antecedents:  str
    consequents:  str
    support:      float
    confidence:   float
    lift:         float


class AssociationResult(BaseModel):
    run_id:       Optional[str]
    data_ready:   bool
    degraded:     bool = False

    total_rules:  int = 0
    top_rules:    List[AssociationRule] = Field(default_factory=list)

    artifact:     Optional[ArtifactRef] = None
    error_message: Optional[str] = None
    mined_at:     datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AssociationMiningService:

    def _load_rules(self) -> Optional[pd.DataFrame]:
        if not _RULES_CSV.exists():
            return None
        try:
            df = pd.read_csv(_RULES_CSV)
            return df
        except Exception as e:
            logger.warning(f"[AssociationService] rules 加载失败: {e}")
            return None

    def query(self, request: AssociationRequest) -> AssociationResult:
        df = self._load_rules()
        if df is None or df.empty:
            return AssociationResult(
                run_id=request.run_id,
                data_ready=False,
                error_message="association_rules.csv 不存在或为空",
            )

        # 过滤质量门槛
        df = df[
            (df.get("lift", df.get("Lift", pd.Series([1.0] * len(df)))) >= request.min_lift) &
            (df.get("confidence", df.get("Confidence", pd.Series([1.0] * len(df)))) >= request.min_confidence)
        ]

        # SKU 过滤
        if request.sku_codes:
            pattern = "|".join(request.sku_codes)
            ant_col = "antecedents" if "antecedents" in df.columns else df.columns[0]
            df = df[df[ant_col].str.contains(pattern, na=False)]

        lift_col       = "lift"       if "lift"       in df.columns else "Lift"
        conf_col       = "confidence" if "confidence" in df.columns else "Confidence"
        supp_col       = "support"    if "support"    in df.columns else "Support"
        ant_col        = "antecedents" if "antecedents" in df.columns else df.columns[0]
        cons_col       = "consequents" if "consequents" in df.columns else df.columns[1]

        top = df.nlargest(request.top_n, lift_col)
        rules = [
            AssociationRule(
                antecedents=str(row[ant_col]),
                consequents=str(row[cons_col]),
                support=round(float(row.get(supp_col, 0)), 4),
                confidence=round(float(row.get(conf_col, 0)), 4),
                lift=round(float(row.get(lift_col, 0)), 4),
            )
            for _, row in top.iterrows()
        ]

        result = AssociationResult(
            run_id=request.run_id,
            data_ready=True,
            total_rules=len(df),
            top_rules=rules,
            artifact=ArtifactRef(
                artifact_type=ArtifactType.ASSOCIATION,
                summary=f"关联规则: 共 {len(df)} 条, Top lift={rules[0].lift if rules else 0}",
            ),
        )
        logger.info(
            f"[AssociationService] total_rules={len(df)} returned={len(rules)}"
        )
        return result


association_mining_service = AssociationMiningService()
