# -*- coding: utf-8 -*-
"""backend/copilot/pipeline/run_state.py — 一次 Copilot 运行的状态容器

设计原则:
  - 所有 Stage 共享同一个 RunState 实例，通过字段读写状态
  - 输入字段不可变（在 __post_init__ 后不应改动）
  - 运行时字段按 Stage 执行顺序被填充
  - 终止控制: should_stop / terminal_message 让前置 Stage 能跳过后续
  - 计时: stage_timings 给 telemetry / 前端展示用

RunState 不是 frozen dataclass —— Stage 需要写入字段。
但字段应按语义分段，避免被写乱。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from backend.copilot.base_skill import BaseCopilotSkill, SkillContext


@dataclass
class RunState:
    """单次 Copilot 运行的状态容器。

    按字段语义分段:
      - [输入] 构造后不应再变
      - [运行时] 每个 Stage 按需填充
      - [累计] 跨 Stage 聚合
      - [终止] 控制 Pipeline 是否继续
      - [计时] 供 telemetry / 前端观察
    """

    # ── [输入] 由外部传入，构造后视为不可变 ──
    question: str
    mode: str
    user_id: str
    user_role: str
    thread_id: str
    page_context: Dict[str, Any] = field(default_factory=dict)
    source: str = "web"
    run_id: str = ""

    # ── [运行时] 由 Stage 填充 ──
    context: "Optional[SkillContext]" = None
    available_skills: List[Any] = field(default_factory=list)   # List[BaseCopilotSkill]
    selected_skill: "Optional[BaseCopilotSkill]" = None
    tool_args: Dict[str, Any] = field(default_factory=dict)
    skill_data: Any = None                                       # skill 执行结果
    skill_executed: bool = False                                  # dedup 命中时 False, 真跑时 True
    from_cache: bool = False                                      # dedup 缓存命中

    # ── [累计] ──
    acc_tokens: int = 0
    acc_cost: float = 0.0
    output_parts: List[str] = field(default_factory=list)        # 收集 text_delta 用于 PII 扫描 + runs summary

    # ── [终止] ──
    should_stop: bool = False          # Pipeline 检测到 True 后跳过后续 Stage
    terminal_message: str = ""          # 可选的最终文本（已由前置 Stage yield）
    terminal_error: Optional[str] = None   # 非空则视为失败
    status: str = "running"            # running / completed / failed / cancelled

    # ── [计时] ──
    start_time: float = field(default_factory=time.time)
    stage_timings: Dict[str, int] = field(default_factory=dict)  # stage_name -> ms

    # ── 便捷方法 ──
    def elapsed_ms(self) -> int:
        """运行开始到现在的 elapsed 毫秒数。"""
        return int((time.time() - self.start_time) * 1000)

    def skill_name_or_default(self) -> str:
        """skill 名，无选中时 'general_chat'，错误时 'error'。"""
        if self.terminal_error:
            return "error"
        if self.selected_skill is None:
            return "general_chat"
        return self.selected_skill.name

    def output_text(self) -> str:
        """聚合所有 text_delta 的文本，供持久化使用。"""
        return "".join(self.output_parts)
