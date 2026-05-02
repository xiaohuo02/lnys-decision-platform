# -*- coding: utf-8 -*-
"""backend/agents/data_agent.py — 数据感知 Agent"""
from typing import Any
import pandas as pd
import numpy as np

from backend.agents.base_agent import BaseAgent
from backend.config import settings


class DataAgent(BaseAgent):
    """数据质量检查 + OMO融合 + 异常值处理"""

    def __init__(self, redis):
        super().__init__("data", redis)

    async def perceive(self, input_data: Any) -> dict:
        return {"input": input_data, "memory": await self.memory_read()}

    async def reason(self, context: dict) -> dict:
        return {"strategy": "quality_check_merge"}

    async def act(self, plan: dict) -> dict:
        report = self._quality_report()
        return {"quality_report": report}

    async def reflect(self, result: dict) -> dict:
        missing_ratio = result.get("quality_report", {}).get("missing_ratio", 0)
        if missing_ratio > 0.05:
            print(f"[DataAgent] 警告：缺失率 {missing_ratio:.1%} 超过阈值 5%")
        return result

    async def output(self, result: dict) -> dict:
        await self.memory_write("data_quality", result.get("quality_report", {}))
        return result

    def _quality_report(self) -> dict:
        try:
            orders = pd.read_csv(settings.MODELS_ROOT.parent / "data" / "processed" / "orders_cn.csv",
                                 nrows=1000, low_memory=False)
            return {
                "row_count":    len(orders),
                "col_count":    len(orders.columns),
                "missing_ratio": float(orders.isnull().mean().mean()),
                "duplicate_rows": int(orders.duplicated().sum()),
            }
        except Exception as e:
            return {"error": str(e)}
