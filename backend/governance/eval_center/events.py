# -*- coding: utf-8 -*-
"""backend/governance/eval_center/events.py — 评测中心 SSE 事件协议

定义所有评测专用 SSE 事件类型，前端通过 useCopilotStream.js 监听这些事件。
"""
from enum import Enum


class EvalEventType(str, Enum):
    """评测中心 SSE 事件类型"""

    # ── 通用 ────────────────────────────────────────────────────
    EXPERIMENT_START = "eval:experiment_start"     # 实验开始
    EXPERIMENT_COMPLETE = "eval:experiment_complete" # 实验完成
    CASE_START = "eval:case_start"                 # 单条 case 开始
    CASE_EXECUTED = "eval:case_executed"            # case Runner 执行完毕
    CASE_GRADED = "eval:case_graded"               # case 评分完毕

    # ── Karpathy Loop（范式一：ML Agent 爬山法） ─────────────
    LOOP_ITER_START = "eval:loop_iter_start"       # 新一轮实验开始
    LOOP_ITER_END = "eval:loop_iter_end"           # 一轮结束（keep/discard/crash）
    LOOP_METRIC = "eval:loop_metric"               # 指标更新
    LOOP_COMPLETE = "eval:loop_complete"            # 循环结束

    # ── Prompt Evolution（范式二：Skill prompt 自进化） ──────
    SKILL_EXEC_START = "eval:skill_exec_start"     # Skill 开始执行
    SKILL_EXEC_RESULT = "eval:skill_exec_result"   # Skill 执行结果
    GRADER_SCORE = "eval:grader_score"             # 单个 Grader 评分完成
    GRADER_ALL_DONE = "eval:grader_all_done"       # 所有 Grader 评分完成
    PROMPT_THINKING = "eval:prompt_thinking"        # MetapromptAgent 思考中（thinking tokens）
    PROMPT_EVOLVED = "eval:prompt_evolved"          # 新 prompt 生成
    EVOLUTION_START = "eval:evolution_start"        # 进化循环开始
    EVOLUTION_COMPLETE = "eval:evolution_complete"  # 进化循环完成

    # ── Trajectory Memory（范式三：轨迹记忆） ────────────────
    TIP_EXTRACTED = "eval:tip_extracted"            # 新 Tip 提取完成
    TIP_INJECTED = "eval:tip_injected"             # Tip 被注入使用
    MEMORY_CONSOLIDATED = "eval:memory_consolidated" # 记忆合并完成
