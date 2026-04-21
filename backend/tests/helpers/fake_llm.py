# -*- coding: utf-8 -*-
"""backend/tests/helpers/fake_llm.py — Fake LLM 工具

提供 Mock OpenAI 客户端，用于测试 CopilotEngine 和 SupervisorAgent。
支持 Function Calling 模拟和流式响应模拟。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock


@dataclass
class FakeChoice:
    message: Any = None
    delta: Any = None
    finish_reason: str = "stop"


@dataclass
class FakeToolCall:
    id: str = "call_fake_001"
    type: str = "function"
    function: Any = None


@dataclass
class FakeFunction:
    name: str = ""
    arguments: str = ""


@dataclass
class FakeMessage:
    content: Optional[str] = None
    tool_calls: Optional[List[FakeToolCall]] = None
    role: str = "assistant"


@dataclass
class FakeUsage:
    total_tokens: int = 100
    prompt_tokens: int = 80
    completion_tokens: int = 20


@dataclass
class FakeChatCompletion:
    choices: List[FakeChoice] = field(default_factory=list)
    usage: Optional[FakeUsage] = None


@dataclass
class FakeDelta:
    content: Optional[str] = None
    role: Optional[str] = None


@dataclass
class FakeStreamChunk:
    choices: List[FakeChoice] = field(default_factory=list)


def make_tool_call_response(skill_name: str, args: Dict[str, Any] = None) -> FakeChatCompletion:
    """构造一个 Function Calling 响应，模拟 LLM 选择了某个 Skill"""
    return FakeChatCompletion(
        choices=[FakeChoice(
            message=FakeMessage(
                tool_calls=[FakeToolCall(
                    function=FakeFunction(
                        name=skill_name,
                        arguments=json.dumps(args or {}),
                    )
                )]
            )
        )],
        usage=FakeUsage(),
    )


def make_text_response(text: str) -> FakeChatCompletion:
    """构造一个纯文本响应（不选择任何 tool）"""
    return FakeChatCompletion(
        choices=[FakeChoice(
            message=FakeMessage(content=text)
        )],
        usage=FakeUsage(),
    )


async def make_stream_response(texts: List[str]) -> AsyncIterator:
    """构造流式响应（用于 _general_chat 和 _synthesize_answer）"""
    for text in texts:
        yield FakeStreamChunk(
            choices=[FakeChoice(delta=FakeDelta(content=text))]
        )


class FakeOpenAIClient:
    """替换 openai.AsyncOpenAI，支持 chat.completions.create"""

    def __init__(
        self,
        tool_call_response: Optional[FakeChatCompletion] = None,
        stream_texts: Optional[List[str]] = None,
        raise_on_call: Optional[Exception] = None,
    ):
        self._tool_call_response = tool_call_response
        self._stream_texts = stream_texts or ["这是一个测试回答。"]
        self._raise_on_call = raise_on_call
        self.chat = MagicMock()
        self.chat.completions = MagicMock()
        self.chat.completions.create = AsyncMock(side_effect=self._create)

    async def _create(self, **kwargs):
        if self._raise_on_call:
            raise self._raise_on_call

        if kwargs.get("stream"):
            return make_stream_response(self._stream_texts)

        if self._tool_call_response:
            return self._tool_call_response

        return make_text_response("这是默认的AI回答。")


def patch_openai_client(monkeypatch, client: FakeOpenAIClient):
    """Monkeypatch openai.AsyncOpenAI 为 FakeOpenAIClient"""
    def fake_init(*args, **kwargs):
        return client

    monkeypatch.setattr("openai.AsyncOpenAI", fake_init)
