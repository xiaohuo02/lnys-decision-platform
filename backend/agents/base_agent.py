# -*- coding: utf-8 -*-
"""backend/agents/base_agent.py — ReAct 认知循环抽象基类"""
from abc import ABC, abstractmethod
from typing import Any
import json
import redis.asyncio as aioredis


class BaseAgent(ABC):
    """所有专业 Agent 的抽象基类（感知→推理→行动→反思→输出）"""

    def __init__(self, name: str, redis: aioredis.Redis):
        self.name = name
        self.redis = redis
        self._memory_key = f"memory:{name}"

    # ── 认知循环接口 ───────────────────────────────────────────────
    @abstractmethod
    async def perceive(self, input_data: Any) -> dict:
        """感知：读取输入数据 + 从共享记忆层获取历史结果"""

    @abstractmethod
    async def reason(self, context: dict) -> dict:
        """推理：判断数据质量 → 选择分析策略 → 确定工具调用顺序"""

    @abstractmethod
    async def act(self, plan: dict) -> dict:
        """行动：调用 ML 工具，执行分析"""

    @abstractmethod
    async def reflect(self, result: dict) -> dict:
        """反思：评估结果质量，必要时触发重分析"""

    @abstractmethod
    async def output(self, result: dict) -> dict:
        """输出：格式化结果，写入共享记忆层"""

    async def run(self, input_data: Any) -> dict:
        """完整 ReAct 认知循环"""
        context = await self.perceive(input_data)
        plan    = await self.reason(context)
        result  = await self.act(plan)
        result  = await self.reflect(result)
        return  await self.output(result)

    # ── 共享记忆层读写 ─────────────────────────────────────────────
    async def memory_read(self) -> dict:
        raw = await self.redis.hgetall(self._memory_key)
        return {k: json.loads(v) for k, v in raw.items()}

    async def memory_write(self, key: str, value: Any) -> None:
        await self.redis.hset(self._memory_key, key, json.dumps(value, ensure_ascii=False))

    async def publish_event(self, channel: str, message: dict) -> None:
        await self.redis.publish(channel, json.dumps(message, ensure_ascii=False))
