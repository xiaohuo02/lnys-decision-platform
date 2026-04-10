# -*- coding: utf-8 -*-
"""backend/agents/inventory_agent.py — 库存优化 Agent（ABC-XYZ + EOQ + 安全库存）"""
from typing import Any
import numpy as np

from backend.agents.base_agent import BaseAgent


class InventoryAgent(BaseAgent):
    """无独立 ML 模型，通过运筹学公式实时计算 EOQ 和动态安全库存"""

    Z_95 = 1.65

    def __init__(self, redis):
        super().__init__("inventory", redis)

    async def perceive(self, input_data: Any) -> dict:
        return {"input": input_data, "memory": await self.memory_read()}

    async def reason(self, context: dict) -> dict:
        return {"strategy": "eoq_safety_stock"}

    async def act(self, plan: dict) -> dict:
        return {}

    async def reflect(self, result: dict) -> dict:
        alerts = result.get("urgent_alerts", [])
        if alerts:
            await self.publish_event("agent:forecast_run", {"trigger": "inventory_low"})
        return result

    async def output(self, result: dict) -> dict:
        await self.memory_write("latest_inventory", result)
        return result

    @staticmethod
    def calc_eoq(demand_per_day: float, ordering_cost: float, holding_cost_per_unit: float) -> float:
        D = demand_per_day * 365
        return float(np.sqrt(2 * D * ordering_cost / holding_cost_per_unit))

    @staticmethod
    def calc_safety_stock(sigma_demand: float, lead_time_days: float) -> float:
        return float(InventoryAgent.Z_95 * sigma_demand * np.sqrt(lead_time_days))
