# -*- coding: utf-8 -*-
"""backend/agents/association_agent.py — 关联分析 Agent"""
import pandas as pd
from typing import Any

from backend.agents.base_agent import BaseAgent
from backend.config import settings


class AssociationAgent(BaseAgent):
    """加载 FP-Growth 关联规则，提供商品推荐"""

    def __init__(self, redis):
        super().__init__("association", redis)
        rules_path = settings.MODELS_ROOT / "results" / "ops" / "association_rules.csv"
        self.rules_df = pd.read_csv(rules_path) if rules_path.exists() else pd.DataFrame()

    async def perceive(self, input_data: Any) -> dict:
        return {"input": input_data}

    async def reason(self, context: dict) -> dict:
        return {"strategy": "fp_growth_lookup"}

    async def act(self, plan: dict) -> dict:
        return {}

    async def reflect(self, result: dict) -> dict:
        return result

    async def output(self, result: dict) -> dict:
        await self.memory_write("latest_rules", {"rule_count": len(self.rules_df)})
        return result

    def recommend(self, sku_code: str, top_n: int = 5) -> list:
        if self.rules_df.empty:
            return []
        mask = self.rules_df["antecedents"].str.contains(sku_code, na=False)
        top = self.rules_df[mask].nlargest(top_n, "lift")
        return top[["consequents", "confidence", "lift"]].to_dict("records")
