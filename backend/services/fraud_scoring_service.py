# -*- coding: utf-8 -*-
"""backend/services/fraud_scoring_service.py

FraudScoringService — 欺诈风险评分服务

╔══════════════════════════════════════════════════════════════════╗
║  Agent 契约                                                       ║
╠══════════════════════════════════════════════════════════════════╣
║  输入   : FraudScoringRequest（交易特征 dict、可选 transaction_id）║
║  输出   : FraudScoringResult（final_score, risk_level,           ║
║            hitl_required, 各路评分, 降级标志）                    ║
║  可调用 : pickle 模型推理（IsoForest + LGB），models/artifacts    ║
║  禁止   : 自动执行订单冻结/退款，直接改 DB risk_status             ║
║  降级   : 任一模型失败时退化为可用分，三路均失败时返回 unknown       ║
║  HITL   : hitl_required=True 时由 RiskReviewAgent 触发 interrupt ║
║  依赖   : models/artifacts/fraud/iso_forest.pkl                  ║
║           models/artifacts/fraud/fraud_lgb.pkl                   ║
║           models/artifacts/fraud/ae_scaler.pkl                   ║
║  Trace  : step_type=SERVICE_CALL, step_name="fraud_scoring"      ║
║           output_summary=final_score + risk_level + hitl_required║
╚══════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from loguru import logger
from pydantic import BaseModel, Field

from backend.config import settings
from backend.schemas.artifact import ArtifactRef, ArtifactType


_ART_FRAUD = settings.ART_FRAUD

# 三路融合权重（与原 FraudAgent 一致）
_WEIGHTS = {"rule": 0.2, "iso": 0.4, "lgb": 0.4}

# 风险阈值
_HIGH_RISK_THRESHOLD   = 0.7
_MEDIUM_RISK_THRESHOLD = 0.4

# 规则引擎阈值（简单版本）
_RULE_AMOUNT_HIGH     = 5000.0   # 单笔金额 > 5000 视为规则触发
_RULE_HOUR_SUSPICIOUS = (0, 5)   # 0~5 点交易触发规则


class FraudScoringRequest(BaseModel):
    transaction_id: Optional[str] = None
    features:       Dict[str, Any] = Field(default_factory=dict)
    run_id:         Optional[str] = None
    # 批量模式：多笔交易
    batch:          Optional[List[Dict[str, Any]]] = None


class SingleFraudScore(BaseModel):
    transaction_id: Optional[str]
    rule_score:     float = 0.0
    iso_score:      float = 0.0
    lgb_score:      float = 0.0
    final_score:    float
    risk_level:     str          # 低风险 / 中风险 / 高风险 / unknown
    hitl_required:  bool
    degraded:       bool = False
    model_flags:    Dict[str, bool] = Field(default_factory=dict)


class FraudScoringResult(BaseModel):
    """FraudScoringService 标准输出"""
    run_id:          Optional[str]
    data_ready:      bool
    degraded:        bool = False

    scores:          List[SingleFraudScore] = Field(default_factory=list)
    high_risk_count: int = 0
    hitl_count:      int = 0      # 需要进入 HITL 的条数

    artifact:        Optional[ArtifactRef] = None
    error_message:   Optional[str] = None
    scored_at:       datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FraudScoringService:
    """
    三路融合风险评分：规则引擎 + IsolationForest + LightGBM
    任意一路失败时自动降级使用可用路。
    """

    def __init__(self):
        self._iso_model  = None
        self._lgb_model  = None
        self._ae_scaler  = None
        self._models_loaded = False

    def _lazy_load(self) -> None:
        """懒加载模型（首次调用时加载，避免启动延迟）"""
        if self._models_loaded:
            return
        try:
            p = _ART_FRAUD / "iso_forest.pkl"
            if p.exists():
                self._iso_model = pickle.load(open(p, "rb"))
                logger.info("[FraudScoringService] iso_forest.pkl 已加载")
        except Exception as e:
            logger.warning(f"[FraudScoringService] iso_forest.pkl 加载失败: {e}")

        try:
            p = _ART_FRAUD / "fraud_lgb.pkl"
            if p.exists():
                self._lgb_model = pickle.load(open(p, "rb"))
                logger.info("[FraudScoringService] fraud_lgb.pkl 已加载")
        except Exception as e:
            logger.warning(f"[FraudScoringService] fraud_lgb.pkl 加载失败: {e}")

        try:
            p = _ART_FRAUD / "ae_scaler.pkl"
            if p.exists():
                self._ae_scaler = pickle.load(open(p, "rb"))
        except Exception as e:
            logger.warning(f"[FraudScoringService] ae_scaler.pkl 加载失败: {e}")

        self._models_loaded = True

    def score(self, request: FraudScoringRequest) -> FraudScoringResult:
        self._lazy_load()

        items = request.batch or [{"transaction_id": request.transaction_id, **request.features}]
        scores:   List[SingleFraudScore] = []
        any_ok    = False

        for item in items:
            tid = item.get("transaction_id") or item.get("order_id")
            features = {k: v for k, v in item.items() if k not in ("transaction_id", "order_id")}
            s = self._score_one(str(tid) if tid else None, features)
            scores.append(s)
            any_ok = True

        high_risk  = [s for s in scores if s.risk_level == "高风险"]
        hitl_items = [s for s in scores if s.hitl_required]
        degraded   = any(s.degraded for s in scores)

        artifact = ArtifactRef(
            artifact_type=ArtifactType.FRAUD_SCORE,
            summary=(
                f"欺诈评分: {len(scores)} 笔, "
                f"高风险 {len(high_risk)} 笔, "
                f"待人工审核 {len(hitl_items)} 笔"
            ),
        ) if any_ok else None

        result = FraudScoringResult(
            run_id=request.run_id,
            data_ready=any_ok,
            degraded=degraded,
            scores=scores,
            high_risk_count=len(high_risk),
            hitl_count=len(hitl_items),
            artifact=artifact,
        )
        logger.info(
            f"[FraudScoringService] total={len(scores)} "
            f"high_risk={len(high_risk)} hitl={len(hitl_items)} "
            f"degraded={degraded}"
        )
        return result

    def _score_one(
        self, transaction_id: Optional[str], features: Dict[str, Any]
    ) -> SingleFraudScore:
        rule_score = self._rule_score(features)
        iso_score  = self._iso_score(features)
        lgb_score  = self._lgb_score(features)

        # 统计有效分路数
        available_scores: List[tuple[str, float, float]] = []
        model_flags = {}

        if rule_score is not None:
            available_scores.append(("rule", rule_score, _WEIGHTS["rule"]))
            model_flags["rule"] = True
        else:
            model_flags["rule"] = False

        if iso_score is not None:
            available_scores.append(("iso", iso_score, _WEIGHTS["iso"]))
            model_flags["iso"] = True
        else:
            model_flags["iso"] = False

        if lgb_score is not None:
            available_scores.append(("lgb", lgb_score, _WEIGHTS["lgb"]))
            model_flags["lgb"] = True
        else:
            model_flags["lgb"] = False

        degraded = len(available_scores) < 3

        if not available_scores:
            return SingleFraudScore(
                transaction_id=transaction_id,
                final_score=0.0,
                risk_level="unknown",
                hitl_required=True,
                degraded=True,
                model_flags=model_flags,
            )

        # 重新归一化权重
        total_w = sum(w for _, _, w in available_scores)
        final_score = sum(s * w / total_w for _, s, w in available_scores)
        final_score = round(float(np.clip(final_score, 0.0, 1.0)), 4)

        if final_score >= _HIGH_RISK_THRESHOLD:
            risk_level    = "高风险"
            hitl_required = True
        elif final_score >= _MEDIUM_RISK_THRESHOLD:
            risk_level    = "中风险"
            hitl_required = False
        else:
            risk_level    = "低风险"
            hitl_required = False

        return SingleFraudScore(
            transaction_id=transaction_id,
            rule_score=round(rule_score or 0.0, 4),
            iso_score=round(iso_score  or 0.0, 4),
            lgb_score=round(lgb_score  or 0.0, 4),
            final_score=final_score,
            risk_level=risk_level,
            hitl_required=hitl_required,
            degraded=degraded,
            model_flags=model_flags,
        )

    # ── 各路评分 ──────────────────────────────────────────────────

    def _rule_score(self, features: Dict[str, Any]) -> Optional[float]:
        """简单规则引擎：金额 + 时段"""
        try:
            score = 0.0
            amount = float(features.get("amount_cny", features.get("total_amount", 0)))
            hour   = int(features.get("hour_of_day", 12))
            if amount > _RULE_AMOUNT_HIGH:
                score += 0.4
            if _RULE_HOUR_SUSPICIOUS[0] <= hour <= _RULE_HOUR_SUSPICIOUS[1]:
                score += 0.3
            return float(np.clip(score, 0.0, 1.0))
        except Exception as e:
            logger.debug(f"[FraudScoringService] rule_score error: {e}")
            return None

    def _iso_score(self, features: Dict[str, Any]) -> Optional[float]:
        if self._iso_model is None:
            return None
        try:
            n = getattr(self._iso_model, "n_features_in_", 29)
            X = self._build_feature_array(features, n)
            raw = float(-self._iso_model.score_samples(X)[0])
            # score_samples 返回负异常分，越大越异常；映射到 [0,1]
            return float(np.clip(raw, 0.0, 1.0))
        except Exception as e:
            logger.debug(f"[FraudScoringService] iso_score error: {e}")
            return None

    def _lgb_score(self, features: Dict[str, Any]) -> Optional[float]:
        if self._lgb_model is None:
            return None
        try:
            n = getattr(self._lgb_model, "n_features_in_", 30)
            X = self._build_feature_array(features, n)
            prob = float(self._lgb_model.predict_proba(X)[0, 1])
            return float(np.clip(prob, 0.0, 1.0))
        except Exception as e:
            logger.debug(f"[FraudScoringService] lgb_score error: {e}")
            return None

    @staticmethod
    def _build_feature_array(features: Dict[str, Any], n_features: int = 32):
        """
        从 features dict 构建 numpy 数组。
        候选列顺序: V1..V28, amount_cny, hour_of_day, V29, V30
        根据模型实际 n_features_in_ 动态截取前 N 列以对齐训练时的特征数。
        """
        import pandas as pd
        v_cols   = [f"V{i}" for i in range(1, 29)]       # V1..V28 = 28 cols
        num_cols = v_cols + ["amount_cny", "hour_of_day"] # + 2 = 30
        num_cols += [f"V{i}" for i in range(29, 31)]      # + V29, V30 = 32
        num_cols = num_cols[:n_features]
        row      = {col: features.get(col, 0.0) for col in num_cols}
        return pd.DataFrame([row])[num_cols].values


fraud_scoring_service = FraudScoringService()
