# -*- coding: utf-8 -*-
"""backend/agents/customer_agent.py — 客户分析 Agent"""
import pickle
from pathlib import Path
from typing import Any
import pandas as pd

from backend.agents.base_agent import BaseAgent
from backend.config import settings


class CustomerAgent(BaseAgent):
    """加载 churn_xgb / BG-NBD / Gamma-Gamma，提供 RFM/CLV/流失风险分析"""

    def __init__(self, redis):
        super().__init__("customer", redis)
        self.churn_model  = pickle.load(open(settings.ART_CUSTOMER / "churn_xgb.pkl",  "rb"))
        self.bgf_model    = pickle.load(open(settings.ART_CUSTOMER / "bgf.pkl",         "rb"))
        self.gg_model     = pickle.load(open(settings.ART_CUSTOMER / "ggf.pkl",         "rb"))
        self.kmeans_model = pickle.load(open(settings.ART_CUSTOMER / "kmeans.pkl",      "rb"))
        self.rfm_scaler   = pickle.load(open(settings.ART_CUSTOMER / "scaler_rfm.pkl",  "rb"))

    async def perceive(self, input_data: Any) -> dict:
        memory = await self.memory_read()
        return {"input": input_data, "memory": memory}

    async def reason(self, context: dict) -> dict:
        return {"strategy": "rfm_cluster_churn_clv"}

    async def act(self, plan: dict) -> dict:
        # TODO: 根据 plan 调用对应分析方法
        return {}

    async def reflect(self, result: dict) -> dict:
        # 反思：若高风险客户 > 20%，发布预警事件
        high_risk = result.get("high_risk_ratio", 0)
        if high_risk > 0.2:
            await self.publish_event("agent:fraud_check", {"trigger": "churn_high_risk"})
        return result

    async def output(self, result: dict) -> dict:
        await self.memory_write("latest", result)
        return result

    def predict_churn(self, features: dict) -> dict:
        import numpy as np
        X = pd.DataFrame([features])
        prob = self.churn_model.predict_proba(X)[0, 1]
        return {"risk_score": round(float(prob), 4), "risk_level": "高" if prob > 0.7 else ("中" if prob > 0.4 else "低")}
