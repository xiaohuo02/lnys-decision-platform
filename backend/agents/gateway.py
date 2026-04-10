# -*- coding: utf-8 -*-
"""backend/agents/gateway.py — Agent 调用网关

统一屏蔽三类问题，service 层只管拿结果或 None：
  - Agent 为 None（模型文件缺失，未就绪）→ 直接返回 None
  - Agent 超时（默认 30s）           → 记录警告，返回 None
  - Agent 抛异常或返回非 dict        → 记录错误，返回 None
"""
import asyncio
from typing import Any, Optional
from loguru import logger

DEFAULT_TIMEOUT = 30.0


class AgentGateway:

    @staticmethod
    async def call(
        agent: Any,
        input_data: Any,
        agent_name: str = "unknown",
        timeout: float = DEFAULT_TIMEOUT,
        **kwargs,
    ) -> Optional[dict]:
        if agent is None:
            logger.debug(f"[gateway] {agent_name}: not ready, skipping")
            return None
        try:
            result = await asyncio.wait_for(agent.run(input_data, **kwargs), timeout=timeout)
            if not isinstance(result, dict):
                logger.warning(
                    f"[gateway] {agent_name}: expected dict, got {type(result).__name__}"
                )
                return None
            if not result:
                logger.warning(f"[gateway] {agent_name}: returned empty dict, treating as not ready")
                return None
            logger.debug(f"[gateway] {agent_name}: ok")
            return result
        except asyncio.TimeoutError:
            logger.warning(f"[gateway] {agent_name}: timed out after {timeout}s")
            return None
        except Exception as exc:
            logger.error(f"[gateway] {agent_name}: {type(exc).__name__}: {exc}")
            return None
