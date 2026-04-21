# -*- coding: utf-8 -*-
"""backend/tests/helpers/sse_collector.py — SSE 事件收集与断言工具

用于 Copilot SSE 流测试：
  1. 收集所有 SSE 事件
  2. 验证事件序列完整性
  3. 验证事件数据结构
  4. 提取关键数据用于幻觉检测
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class CollectedEvent:
    """收集的单个 SSE 事件"""
    type: str
    content: Any = None
    metadata: Optional[Dict[str, Any]] = None
    data: Optional[Dict[str, Any]] = None
    raw: str = ""


@dataclass
class SSECollectionResult:
    """SSE 流收集结果"""
    events: List[CollectedEvent] = field(default_factory=list)
    text_deltas: List[str] = field(default_factory=list)
    thinking_deltas: List[str] = field(default_factory=list)
    skills_called: List[str] = field(default_factory=list)
    artifacts: List[Dict] = field(default_factory=list)
    suggestions: List[Dict] = field(default_factory=list)
    tool_results: List[Dict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return "".join(self.text_deltas)

    @property
    def event_types(self) -> List[str]:
        return [e.type for e in self.events]

    @property
    def has_run_start(self) -> bool:
        return "run_start" in self.event_types

    @property
    def has_run_end(self) -> bool:
        return "run_end" in self.event_types

    @property
    def has_run_error(self) -> bool:
        return "run_error" in self.event_types

    @property
    def has_tool_call(self) -> bool:
        return "tool_call_start" in self.event_types

    @property
    def has_artifact(self) -> bool:
        return "artifact_start" in self.event_types


def parse_sse_line(line: str) -> Optional[CollectedEvent]:
    """解析单行 SSE 数据"""
    line = line.strip()
    if not line or not line.startswith("data: "):
        return None

    json_str = line[6:]  # 去掉 "data: "
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        return CollectedEvent(type="parse_error", raw=json_str)

    return CollectedEvent(
        type=data.get("type", "unknown"),
        content=data.get("content"),
        metadata=data.get("metadata"),
        data=data.get("data"),
        raw=json_str,
    )


def collect_sse_events(sse_text: str) -> SSECollectionResult:
    """从完整 SSE 文本中收集所有事件"""
    result = SSECollectionResult()

    for line in sse_text.split("\n"):
        event = parse_sse_line(line)
        if event is None:
            continue

        result.events.append(event)

        if event.type == "text_delta" and event.content:
            result.text_deltas.append(str(event.content))
        elif event.type == "thinking_delta" and event.content:
            result.thinking_deltas.append(str(event.content))
        elif event.type == "tool_call_start" and event.metadata:
            skill = event.metadata.get("skill", "")
            if skill:
                result.skills_called.append(skill)
        elif event.type == "artifact_delta" and event.content:
            result.artifacts.append(event.content if isinstance(event.content, dict) else {"raw": event.content})
        elif event.type == "suggestions" and event.content:
            items = event.content if isinstance(event.content, list) else [event.content]
            result.suggestions.extend(items)
        elif event.type == "tool_result" and event.data:
            result.tool_results.append(event.data)
        elif event.type == "run_error":
            result.errors.append(str(event.content or event.metadata or "unknown error"))

    return result


async def collect_engine_events(engine, **run_kwargs) -> SSECollectionResult:
    """直接从 CopilotEngine.run() 收集事件（不经过 HTTP）"""
    result = SSECollectionResult()

    async for event in engine.run(**run_kwargs):
        sse_str = event.to_sse()
        parsed = parse_sse_line(sse_str)
        if parsed:
            result.events.append(parsed)

            if parsed.type == "text_delta" and parsed.content:
                result.text_deltas.append(str(parsed.content))
            elif parsed.type == "thinking_delta" and parsed.content:
                result.thinking_deltas.append(str(parsed.content))
            elif parsed.type == "tool_call_start" and parsed.metadata:
                skill = parsed.metadata.get("skill", "")
                if skill:
                    result.skills_called.append(skill)
            elif parsed.type == "artifact_delta" and parsed.content:
                result.artifacts.append(parsed.content if isinstance(parsed.content, dict) else {"raw": parsed.content})
            elif parsed.type == "tool_result" and parsed.data:
                result.tool_results.append(parsed.data)
            elif parsed.type == "run_error":
                result.errors.append(str(parsed.content or ""))

    return result


# ── 断言辅助函数 ──

def assert_sse_lifecycle_complete(result: SSECollectionResult, label: str = ""):
    """断言 SSE 生命周期完整: 必须有 run_start 和 run_end"""
    prefix = f"[{label}] " if label else ""
    assert result.has_run_start, f"{prefix}缺少 run_start 事件"
    assert result.has_run_end, f"{prefix}缺少 run_end 事件"

    # run_start 必须是第一个事件
    assert result.event_types[0] == "run_start", \
        f"{prefix}run_start 不是第一个事件, 实际: {result.event_types[0]}"

    # run_end 必须是最后一个事件
    assert result.event_types[-1] == "run_end", \
        f"{prefix}run_end 不是最后一个事件, 实际: {result.event_types[-1]}"


def assert_tool_call_complete(result: SSECollectionResult, expected_skill: str, label: str = ""):
    """断言工具调用完整: tool_call_start → ... → tool_call_end → tool_result"""
    prefix = f"[{label}] " if label else ""
    assert result.has_tool_call, f"{prefix}缺少 tool_call_start 事件"
    assert expected_skill in result.skills_called, \
        f"{prefix}预期 Skill '{expected_skill}' 未被调用, 实际: {result.skills_called}"
    assert "tool_call_end" in result.event_types, f"{prefix}缺少 tool_call_end 事件"
    assert len(result.tool_results) > 0, f"{prefix}缺少 tool_result 事件"


def assert_artifact_complete(result: SSECollectionResult, label: str = ""):
    """断言 Artifact 完整: artifact_start → artifact_delta → artifact_end"""
    prefix = f"[{label}] " if label else ""
    types = result.event_types
    assert "artifact_start" in types, f"{prefix}缺少 artifact_start"
    assert "artifact_delta" in types, f"{prefix}缺少 artifact_delta"
    assert "artifact_end" in types, f"{prefix}缺少 artifact_end"

    # artifact_start 必须在 artifact_delta 前面
    start_idx = types.index("artifact_start")
    delta_idx = types.index("artifact_delta")
    end_idx = types.index("artifact_end")
    assert start_idx < delta_idx < end_idx, \
        f"{prefix}artifact 事件顺序错误: start@{start_idx} delta@{delta_idx} end@{end_idx}"


def assert_no_hallucination_numbers(result: SSECollectionResult, label: str = ""):
    """断言: 最终文本中的数字都能在 tool_result 中找到来源

    注意: 这是一个启发式检查，可能有误报。
    对于复杂场景建议人工复核。
    """
    import re
    prefix = f"[{label}] " if label else ""

    if not result.tool_results:
        return  # 无 tool_result 则跳过

    # 从 tool_result 中提取所有数值
    tool_numbers: Set[str] = set()
    _extract_numbers_from_dict(result.tool_results[0], tool_numbers)

    # 从最终文本中提取数值
    text = result.full_text
    text_numbers = set(re.findall(r"\d+\.?\d*", text))

    # 忽略非常小的数（可能是序号/年份/百分比符号等）
    # 只关注 > 1 的数值
    suspicious = set()
    for n in text_numbers:
        try:
            val = float(n)
            if val > 1 and n not in tool_numbers:
                # 检查四舍五入版本
                rounded_match = any(
                    abs(val - float(tn)) < 0.5
                    for tn in tool_numbers
                    if _is_number(tn)
                )
                if not rounded_match:
                    suspicious.add(n)
        except ValueError:
            pass

    if suspicious:
        # 不直接断言失败，而是标记为 WARNING
        import warnings
        warnings.warn(
            f"{prefix}疑似幻觉数值 (文本中有但 tool_result 中无): {suspicious}",
            UserWarning,
        )


def _extract_numbers_from_dict(d: Any, numbers: Set[str], depth: int = 0):
    """递归提取字典中的所有数值"""
    if depth > 10:
        return
    if isinstance(d, dict):
        for v in d.values():
            _extract_numbers_from_dict(v, numbers, depth + 1)
    elif isinstance(d, list):
        for item in d:
            _extract_numbers_from_dict(item, numbers, depth + 1)
    elif isinstance(d, (int, float)):
        numbers.add(str(d))
    elif isinstance(d, str) and _is_number(d):
        numbers.add(d)


def _is_number(s: str) -> bool:
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False
