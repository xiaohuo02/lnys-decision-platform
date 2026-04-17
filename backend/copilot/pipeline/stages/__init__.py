# -*- coding: utf-8 -*-
"""backend/copilot/pipeline/stages — 9 个 Stage 的具体实现 (R6-1)

Stage 执行顺序（对应 engine.run 原逻辑）:
  1. InputGuardStage    — run_start + 空问题检查 + InputGuard + 安全 telemetry
  2. ContextStage       — ContextManager.build + 保存用户消息到 Redis
  3. TokenGovernorStage — context_monitor.evaluate/compact 自动压缩
  4. MemoryRecallStage  — memory_recall 事件 + 遥测
  5. RouterStage        — 权限过滤 + LLM 路由 + 关键词回退
  6. DedupStage         — 重复调用检测（命中时标记 from_cache）
  7. SkillExecStage     — 执行 skill（或 general_chat） + LLM 综合回答
  8. OutputPIIStage     — 输出 PII 扫描
  9. PersistStage       — (finalize) run_end + RUN_COMPLETED 遥测 + 异步写 runs 表

用法:
    from backend.copilot.pipeline import Pipeline
    from backend.copilot.pipeline.stages import build_default_stages, build_finalize_stages

    pipeline = Pipeline(
        stages=build_default_stages(engine),
        finalize_stages=build_finalize_stages(engine),
    )
"""
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from backend.copilot.engine import CopilotEngine
    from backend.copilot.pipeline.base_stage import BaseStage


def build_default_stages(engine: "CopilotEngine") -> "List[BaseStage]":
    """构造默认的主 Stage 序列（按 1-8 的顺序）。"""
    from backend.copilot.pipeline.stages.input_guard import InputGuardStage
    from backend.copilot.pipeline.stages.context import ContextStage
    from backend.copilot.pipeline.stages.token_governor import TokenGovernorStage
    from backend.copilot.pipeline.stages.memory_recall import MemoryRecallStage
    from backend.copilot.pipeline.stages.router import RouterStage
    from backend.copilot.pipeline.stages.dedup import DedupStage
    from backend.copilot.pipeline.stages.skill_exec import SkillExecStage
    from backend.copilot.pipeline.stages.output_pii import OutputPIIStage

    return [
        InputGuardStage(engine),
        ContextStage(engine),
        TokenGovernorStage(engine),
        MemoryRecallStage(engine),
        RouterStage(engine),
        DedupStage(engine),
        SkillExecStage(engine),
        OutputPIIStage(engine),
    ]


def build_finalize_stages(engine: "CopilotEngine") -> "List[BaseStage]":
    """构造 finalize Stage 序列（无视 should_stop 总会执行）。"""
    from backend.copilot.pipeline.stages.persist import PersistStage
    return [PersistStage(engine)]
