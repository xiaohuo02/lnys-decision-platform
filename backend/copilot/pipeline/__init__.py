# -*- coding: utf-8 -*-
"""backend/copilot/pipeline — CopilotEngine 的 Stage Pipeline (R6-1)

模块结构:
  run_state.py   — RunState dataclass，承载一次运行的全部可变状态
  base_stage.py  — BaseStage ABC + 辅助基类
  pipeline.py    — Pipeline 编排器，串联 Stage 序列，统一事件广播 + stage 计时
  stages/        — 9 个 Stage 具体实现

使用:
    from backend.copilot.pipeline import Pipeline, RunState
    from backend.copilot.pipeline.stages import build_default_stages

    pipeline = Pipeline(stages=build_default_stages(engine))
    async for event in pipeline.run(state):
        yield event
"""
from backend.copilot.pipeline.run_state import RunState
from backend.copilot.pipeline.base_stage import BaseStage
from backend.copilot.pipeline.pipeline import Pipeline

__all__ = ["RunState", "BaseStage", "Pipeline"]
