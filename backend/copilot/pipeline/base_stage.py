# -*- coding: utf-8 -*-
"""backend/copilot/pipeline/base_stage.py — Stage 基类

每个 Stage 是独立 AsyncGenerator:
    async def run(state) -> AsyncGenerator[CopilotEvent, None]:
        yield some_event(...)
        state.xxx = ...

Stage 通过设置 state.should_stop = True 可以让 Pipeline 跳过后续 Stage。

约定:
  - Stage 不应直接 return 异常；异常应被 Pipeline 捕获并标记 terminal_error
  - Stage 内部的 try/except 只用于"此 Stage 失败但可降级"的场景
  - Stage 不应依赖全局状态，只读 state，写 state
"""
from __future__ import annotations

from typing import TYPE_CHECKING, AsyncGenerator

from backend.copilot.events import CopilotEvent

if TYPE_CHECKING:
    from backend.copilot.engine import CopilotEngine
    from backend.copilot.pipeline.run_state import RunState


class BaseStage:
    """Pipeline 中单个阶段的基类。

    子类要求:
      - 覆盖 `name` 属性（用于日志 / 计时 key）
      - 覆盖 `run(state)` 方法，返回 AsyncGenerator[CopilotEvent]

    构造:
      Stage 接收 CopilotEngine 引用，以便调用 engine 的公共方法和 helper
      （如 _route_to_skill / _general_chat / _synthesize_answer）。
      这是 MVP 选择；后续随 R6-3 可以把这些 helper 移到独立模块。
    """

    name: str = "base"

    def __init__(self, engine: "CopilotEngine"):
        self._engine = engine

    async def run(
        self, state: "RunState"
    ) -> AsyncGenerator[CopilotEvent, None]:
        """执行 Stage 逻辑，yield 0..N 个事件。允许修改 state。"""
        raise NotImplementedError(f"{self.__class__.__name__}.run must be overridden")
        # 不可达，但让类型检查器识别为 AsyncGenerator
        if False:
            yield  # type: ignore[unreachable]
