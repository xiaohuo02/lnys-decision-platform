# -*- coding: utf-8 -*-
"""backend/agents/forecast_agent.py — 销售预测 Agent"""
import pickle
from typing import Any
import torch

from backend.agents.base_agent import BaseAgent
from backend.config import settings


class ForecastAgent(BaseAgent):
    """加载 SARIMA / HW-ETS / GRU / XGBoost / Stacking，提供多模型集成预测"""

    def __init__(self, redis):
        super().__init__("forecast", redis)
        self.sarima   = pickle.load(open(settings.ART_FORECAST / "sarima.pkl",          "rb"))
        self.prophet  = pickle.load(open(settings.ART_FORECAST / "prophet.pkl",         "rb"))
        self.xgb      = pickle.load(open(settings.ART_FORECAST / "sales_xgb.pkl",       "rb"))
        self.stacking = pickle.load(open(settings.ART_FORECAST / "stacking_weights.pkl","rb"))
        self.lgbm_hyb = pickle.load(open(settings.ART_FORECAST / "lgbm_hybrid.pkl",     "rb"))
        # GRU 模型（PyTorch）
        # self.gru_model = torch.load(settings.ART_FORECAST / "lstm.pt", map_location="cpu")

    async def perceive(self, input_data: Any) -> dict:
        return {"input": input_data, "memory": await self.memory_read()}

    async def reason(self, context: dict) -> dict:
        return {"strategy": "stacking_ensemble"}

    async def act(self, plan: dict) -> dict:
        # TODO: 调用 Stacking 集成预测
        return {}

    async def reflect(self, result: dict) -> dict:
        mape = result.get("mape", 999)
        if mape > 15:
            await self.publish_event("agent:inventory_adj", {"trigger": "forecast_updated"})
        return result

    async def output(self, result: dict) -> dict:
        await self.memory_write("latest_forecast", result)
        return result
