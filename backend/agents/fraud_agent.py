# -*- coding: utf-8 -*-
"""backend/agents/fraud_agent.py — 欺诈风控 Agent（规则引擎 + IsoForest + LightGBM）

注意：此 Agent 与 backend/services/fraud_scoring_service.py 共享模型与融合策略；
新代码请优先使用 FraudScoringService（有更完整的降级、HITL、批量与 artifact 处理）。
"""
import pickle
from typing import Any, Optional

import numpy as np

from backend.agents.base_agent import BaseAgent
from backend.config import settings


class FraudAgent(BaseAgent):
    """三路融合：规则引擎 + Isolation Forest + LightGBM"""

    # 三路权重（与 services/fraud_scoring_service.py 的 _WEIGHTS 保持一致）
    WEIGHTS = {"rule": 0.2, "iso": 0.4, "lgb": 0.4}

    # 规则阈值
    _RULE_AMOUNT_HIGH = 5000.0          # 单笔金额 > 5000 触发规则
    _RULE_HOUR_SUSPICIOUS = (0, 5)      # 0~5 点交易触发规则
    _HIGH_RISK_THRESHOLD = 0.7
    _MEDIUM_RISK_THRESHOLD = 0.4

    def __init__(self, redis):
        super().__init__("fraud", redis)
        self.iso_forest = pickle.load(open(settings.ART_FRAUD / "iso_forest.pkl", "rb"))
        self.lgb_model  = pickle.load(open(settings.ART_FRAUD / "fraud_lgb.pkl",  "rb"))

    async def perceive(self, input_data: Any) -> dict:
        try:
            memory = await self.memory_read()
        except Exception:
            memory = {}
        return {"input": input_data, "memory": memory}

    async def reason(self, context: dict) -> dict:
        return {"strategy": "rule_iso_lgb_fusion", "input": context.get("input", {})}

    async def act(self, plan: dict) -> dict:
        features = plan.get("input", {})
        if isinstance(features, dict) and any(
            k.startswith("V") or k in ("amount_cny", "hour_of_day") for k in features
        ):
            return self.score(features)
        return {"risk_score": 0.0, "risk_level": "unknown", "reason": "无有效特征"}

    async def reflect(self, result: dict) -> dict:
        if result.get("risk_level") == "高风险":
            try:
                await self.publish_event("agent:sentiment_check", {"trigger": "fraud_alert"})
            except Exception:
                pass
        return result

    async def output(self, result: dict) -> dict:
        try:
            await self.memory_write("latest_fraud", result)
        except Exception:
            pass
        return result

    # ── 各路评分 ──────────────────────────────────────────────────

    def _rule_score(self, features: dict) -> Optional[float]:
        """简单规则引擎：金额 + 时段"""
        try:
            score = 0.0
            amount = float(features.get("amount_cny", features.get("total_amount", 0)))
            hour = int(features.get("hour_of_day", 12))
            if amount > self._RULE_AMOUNT_HIGH:
                score += 0.4
            if self._RULE_HOUR_SUSPICIOUS[0] <= hour <= self._RULE_HOUR_SUSPICIOUS[1]:
                score += 0.3
            return float(np.clip(score, 0.0, 1.0))
        except Exception:
            return None

    def _iso_score(self, features: dict) -> Optional[float]:
        try:
            n = getattr(self.iso_forest, "n_features_in_", 29)
            X = self._build_feature_array(features, n)
            raw = float(-self.iso_forest.score_samples(X)[0])
            return float(np.clip(raw, 0.0, 1.0))
        except Exception:
            return None

    def _lgb_score(self, features: dict) -> Optional[float]:
        try:
            n = getattr(self.lgb_model, "n_features_in_", 30)
            X = self._build_feature_array(features, n)
            prob = float(self.lgb_model.predict_proba(X)[0, 1])
            return float(np.clip(prob, 0.0, 1.0))
        except Exception:
            return None

    @staticmethod
    def _build_feature_array(features: dict, n_features: int):
        """按模型实际 n_features_in_ 动态构建特征数组。

        候选列顺序: V1..V28, amount_cny, hour_of_day, V29, V30
        """
        v_cols = [f"V{i}" for i in range(1, 29)]              # 28
        num_cols = v_cols + ["amount_cny", "hour_of_day"]     # + 2 = 30
        num_cols += [f"V{i}" for i in range(29, 31)]          # + V29, V30 = 32
        num_cols = num_cols[:n_features]
        row = [float(features.get(c, 0.0)) for c in num_cols]
        return np.array([row])

    def score(self, features: dict) -> dict:
        """三路融合风险评分。

        - rule_score / iso_score / lgb_score 任一路失败返回 None，按可用分路重新归一化权重
        - 全部失败时返回 risk_level='unknown'
        """
        rule_score = self._rule_score(features)
        iso_score = self._iso_score(features)
        lgb_score = self._lgb_score(features)

        available: list[tuple[str, float, float]] = []
        if rule_score is not None:
            available.append(("rule", rule_score, self.WEIGHTS["rule"]))
        if iso_score is not None:
            available.append(("iso", iso_score, self.WEIGHTS["iso"]))
        if lgb_score is not None:
            available.append(("lgb", lgb_score, self.WEIGHTS["lgb"]))

        if not available:
            return {"risk_score": 0.0, "risk_level": "unknown", "reason": "所有评分路径失败"}

        # 按可用权重归一化
        total_w = sum(w for _, _, w in available)
        final = sum(s * w / total_w for _, s, w in available)
        final = float(np.clip(final, 0.0, 1.0))

        if final >= self._HIGH_RISK_THRESHOLD:
            level = "高风险"
        elif final >= self._MEDIUM_RISK_THRESHOLD:
            level = "中风险"
        else:
            level = "低风险"

        return {
            "risk_score": round(final, 4),
            "risk_level": level,
            "rule_score": round(rule_score, 4) if rule_score is not None else None,
            "iso_score": round(iso_score, 4) if iso_score is not None else None,
            "lgb_score": round(lgb_score, 4) if lgb_score is not None else None,
            "degraded": len(available) < 3,
        }
