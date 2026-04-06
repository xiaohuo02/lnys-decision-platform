# -*- coding: utf-8 -*-
"""backend/dependencies/agents.py — Agent 可选依赖注入

路由层通过 Depends(get_optional_agent("xxx_agent")) 获取 Agent 实例或 None。
None 表示 Agent 尚未就绪，由 Service 层决定降级策略，路由层无感知。
"""
from typing import Any, Optional
from fastapi import Depends, Request


def get_optional_agent(agent_name: str):
    """返回 Agent 实例，若未就绪则返回 None（不抛异常）"""
    def _dep(request: Request) -> Optional[Any]:
        return getattr(request.app.state, agent_name, None)
    return Depends(_dep)


def get_agent_registry(request: Request) -> dict[str, str]:
    """返回完整 Agent 就绪状态字典，供 /health 端点使用"""
    return getattr(request.app.state, "agent_registry", {})
