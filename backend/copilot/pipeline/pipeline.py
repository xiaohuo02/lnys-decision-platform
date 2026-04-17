# -*- coding: utf-8 -*-
"""backend/copilot/pipeline/pipeline.py — Stage 编排器

职责:
  1. 按序执行 Stage 列表
  2. 统一 stage 计时（写入 state.stage_timings）
  3. 监测 state.should_stop，跳过后续 Stage
  4. 捕获 Stage 抛出的异常并设置 state.terminal_error（不 re-raise，除非 CancelledError）
  5. 每个 Stage 开始 / 结束发 telemetry HOOK_FIRED 事件，供观测

不做的事:
  - 不持久化 state（Stage 自己决定）
  - 不管理 SSE 连接生命周期（上层 engine.run_v2 负责）
  - 不判断业务逻辑（Stage 内部决定 should_stop）
"""
from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, AsyncGenerator, List, Optional

from loguru import logger

from backend.copilot.events import CopilotEvent

if TYPE_CHECKING:
    from backend.copilot.pipeline.base_stage import BaseStage
    from backend.copilot.pipeline.run_state import RunState


class Pipeline:
    """Stage 序列编排器。

    用法:
        pipeline = Pipeline(stages=[InputGuardStage(engine), ContextStage(engine), ...])
        async for event in pipeline.run(state):
            yield event

    执行语义:
      - Stage 按列表顺序执行
      - 任一 Stage 设置 state.should_stop=True → 后续 Stage 全部跳过
      - Stage 抛出 CancelledError/GeneratorExit → 向上抛（不压制取消语义）
      - Stage 抛出其它异常 → 捕获, state.terminal_error 记录, 停止 Pipeline 继续
    """

    def __init__(
        self,
        stages: "List[BaseStage]",
        finalize_stages: "Optional[List[BaseStage]]" = None,
    ):
        """
        Args:
            stages:          按序执行的 Stage；should_stop 时后续跳过
            finalize_stages: 总是执行的 Stage（即使 should_stop / terminal_error）
                             典型用途: PersistStage 发 run_end + 写 runs
        """
        if not stages:
            raise ValueError("Pipeline 至少需要一个 Stage")
        self._stages = list(stages)
        self._finalize_stages = list(finalize_stages or [])

    @property
    def stage_names(self) -> List[str]:
        return [s.name for s in self._stages] + [s.name for s in self._finalize_stages]

    async def run(
        self, state: "RunState"
    ) -> AsyncGenerator[CopilotEvent, None]:
        """执行整个 pipeline，yield 每个 Stage 的事件。

        finalize_stages 总是在 main stages 之后执行，无视 should_stop / terminal_error，
        保证 run_end / 持久化等副作用一定发生。
        """
        try:
            for stage in self._stages:
                if state.should_stop:
                    logger.debug(f"[pipeline] skip stage={stage.name} (should_stop=True)")
                    continue

                t0 = time.time()
                try:
                    async for event in stage.run(state):
                        yield event
                except (asyncio.CancelledError, GeneratorExit):
                    logger.warning(f"[pipeline] stage={stage.name} cancelled")
                    raise
                except Exception as e:
                    logger.error(f"[pipeline] stage={stage.name} raised: {type(e).__name__}: {e}")
                    state.terminal_error = f"{stage.name}: {type(e).__name__}: {e}"
                    state.status = "failed"
                    state.should_stop = True
                    break
                finally:
                    dt_ms = int((time.time() - t0) * 1000)
                    state.stage_timings[stage.name] = dt_ms
                    logger.debug(f"[pipeline] stage={stage.name} done in {dt_ms}ms")
        finally:
            # finalize_stages 永远执行（即使被 CancelledError 穿透）
            for stage in self._finalize_stages:
                t0 = time.time()
                try:
                    async for event in stage.run(state):
                        yield event
                except (asyncio.CancelledError, GeneratorExit):
                    # finalize Stage 被取消就直接放弃，不再挣扎
                    logger.warning(f"[pipeline] finalize stage={stage.name} cancelled")
                    break
                except Exception as e:
                    # finalize 失败只记录，不影响其它 finalize stage
                    logger.error(
                        f"[pipeline] finalize stage={stage.name} raised: "
                        f"{type(e).__name__}: {e}"
                    )
                finally:
                    dt_ms = int((time.time() - t0) * 1000)
                    state.stage_timings[stage.name] = dt_ms
