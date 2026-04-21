# -*- coding: utf-8 -*-
"""backend/governance/eval_center/runners/skill_runner.py — Copilot Skill 执行器

通过 BaseCopilotSkill.execute() 调用真实 Skill，
收集所有 CopilotEvent 并提取最终文本输出和 artifact 数据。
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from loguru import logger

from backend.copilot.base_skill import BaseCopilotSkill, SkillContext
from backend.copilot.events import EventType
from backend.copilot.registry import SkillRegistry
from backend.governance.eval_center.runners.base_runner import BaseRunner, RunnerResult


class SkillRunner(BaseRunner):
    """Copilot Skill 评测执行器

    Parameters:
        skill_name:     Skill 名称（从 SkillRegistry 查找）
        skill_instance: 直接传入 Skill 实例（优先于 skill_name）
        prompt_override: 如有，替换 Skill 的默认 system_prompt（用于 prompt 进化）
    """

    runner_type = "copilot_skill"

    def __init__(
        self,
        skill_name: str = "",
        skill_instance: Optional[BaseCopilotSkill] = None,
        prompt_override: Optional[str] = None,
    ):
        self.skill_name = skill_name
        self.skill_instance = skill_instance
        self.prompt_override = prompt_override

    def _get_skill(self) -> Optional[BaseCopilotSkill]:
        if self.skill_instance is not None:
            return self.skill_instance
        registry = SkillRegistry.instance()
        return registry.get(self.skill_name)

    async def execute(self, input_json: Dict[str, Any], **kwargs) -> RunnerResult:
        skill = self._get_skill()
        if skill is None:
            return RunnerResult(
                error=f"Skill '{self.skill_name}' 未找到",
                metadata={"skill_name": self.skill_name},
            )

        question = input_json.get("question", "")
        if not question:
            return RunnerResult(
                error="input_json 缺少 'question' 字段",
                metadata={"skill_name": self.skill_name},
            )

        context = SkillContext(
            user_id="eval_system",
            user_role="admin",
            mode="ops",
            thread_id=str(uuid.uuid4()),
            tool_args=input_json.get("tool_args", {}),
            system_prompt=self.prompt_override or "",
            source="api",
        )

        events: List[Dict[str, Any]] = []
        text_parts: List[str] = []
        artifact_data: Dict[str, Any] = {}
        tool_results: List[Dict[str, Any]] = []
        tokens_used = 0

        try:
            async for event in skill.execute(question, context):
                ev = event.to_dict() if hasattr(event, "to_dict") else {"type": str(event.type), "data": event.data}
                events.append(ev)

                etype = event.type if hasattr(event, "type") else ""

                if etype == EventType.TEXT_DELTA:
                    text_parts.append(event.data.get("delta", "") if isinstance(event.data, dict) else str(event.data))
                elif etype == EventType.TOOL_RESULT:
                    data = event.data if isinstance(event.data, dict) else {}
                    tool_results.append(data)
                elif etype == EventType.ARTIFACT_START:
                    data = event.data if isinstance(event.data, dict) else {}
                    artifact_data = data
                elif etype == EventType.RUN_END:
                    data = event.data if isinstance(event.data, dict) else {}
                    tokens_used = data.get("tokens_used", 0)

        except Exception as exc:
            logger.error(f"[SkillRunner] {self.skill_name}: {type(exc).__name__}: {exc}")
            return RunnerResult(
                error=f"Skill 执行异常: {type(exc).__name__}: {exc}",
                actual_output={"events": events, "text": "".join(text_parts)},
                tokens_used=tokens_used,
                metadata={"skill_name": self.skill_name},
            )

        final_text = "".join(text_parts)

        # 构建 actual_output：基础结构 + 将 tool_results/artifact 数据提升到顶层
        # 方便 Grader 直接检查业务字段
        actual = {
            "text": final_text,
            "events": events,
            "tool_results": tool_results,
            "artifact": artifact_data,
        }
        # 提升 artifact 数据到顶层（如 summary、data 等）
        if isinstance(artifact_data, dict):
            for k, v in artifact_data.items():
                if k not in actual:
                    actual[k] = v
        # 提升首个 tool_result 数据到顶层
        if tool_results and isinstance(tool_results[0], dict):
            for k, v in tool_results[0].items():
                if k not in actual:
                    actual[k] = v

        logger.debug(f"[SkillRunner] {self.skill_name}: 执行成功, {len(events)} 事件, {len(final_text)} 字符")
        return RunnerResult(
            actual_output=actual,
            tokens_used=tokens_used,
            metadata={"skill_name": self.skill_name, "event_count": len(events)},
        )
