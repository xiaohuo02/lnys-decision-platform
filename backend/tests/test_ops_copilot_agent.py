# -*- coding: utf-8 -*-
"""backend/tests/test_ops_copilot_agent.py

OpsCopilotAgent 单元测试。
不依赖真实数据库、router、前端。所有 repo 方法通过 MagicMock 注入。

运行方式（在 nyshdsjpt/ 根目录下）：
    pytest backend/tests/test_ops_copilot_agent.py -v
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from backend.agents.ops_copilot_agent import (
    OpsCopilotAgent,
    OpsCopilotReadRepository,
    _q_fingerprint,
)
from backend.schemas.ops_copilot import OpsCopilotInput, OpsCopilotOutput
from backend.tests.fixtures.ops_copilot_mock_data import (
    MOCK_FAILED_RUNS,
    MOCK_LAST_ROLLBACK,
    MOCK_LOWEST_EXPERIMENT,
    MOCK_PROMPT_VERSIONS,
    MOCK_PUBLISHED_PROMPTS,
    MOCK_RECENT_EXPERIMENTS,
    MOCK_RECENT_RELEASES,
    MOCK_SLOWEST_RUNS,
)


# ── Helper: 构造 mock repo ────────────────────────────────────────

def make_mock_repo(
    slowest_runs=None,
    failed_runs=None,
    recent_experiments=None,
    lowest_experiment=None,
    published_prompts=None,
    prompt_versions=None,
    recent_releases=None,
    last_rollback=None,
) -> MagicMock:
    """构造预设返回值的 mock repo，避免真实 DB 调用。"""
    repo = MagicMock(spec=OpsCopilotReadRepository)
    repo.get_slowest_runs.return_value = slowest_runs if slowest_runs is not None else []
    repo.get_failed_runs.return_value = failed_runs if failed_runs is not None else []
    repo.get_recent_experiments.return_value = recent_experiments if recent_experiments is not None else []
    repo.get_lowest_pass_rate_experiment.return_value = lowest_experiment
    repo.get_recent_published_prompts.return_value = published_prompts if published_prompts is not None else []
    repo.get_prompt_versions.return_value = prompt_versions if prompt_versions is not None else []
    repo.get_recent_releases.return_value = recent_releases if recent_releases is not None else []
    repo.get_last_rollback.return_value = last_rollback
    return repo


MOCK_DB = MagicMock()  # 占位 db，不会被真实调用（repo 已 mock）


# ── 验证输出结构完整性 ────────────────────────────────────────────

def assert_output_schema(out: OpsCopilotOutput) -> None:
    """验证输出包含所有必填字段，类型正确。"""
    assert isinstance(out, OpsCopilotOutput), "返回类型必须是 OpsCopilotOutput"
    assert isinstance(out.intent, str) and out.intent, "intent 必须是非空 str"
    assert isinstance(out.answer, str) and out.answer, "answer 必须是非空 str"
    assert isinstance(out.confidence, float), "confidence 必须是 float"
    assert isinstance(out.sources, list), "sources 必须是 list"
    assert isinstance(out.suggested_actions, list), "suggested_actions 必须是 list"
    assert isinstance(out.fallback_used, bool), "fallback_used 必须是 bool"
    # error 允许为 None 或 str
    assert out.error is None or isinstance(out.error, str), "error 必须是 str 或 None"


# ═══════════════════════════════════════════════════════════════════
# 1. 意图分类正确性
# ═══════════════════════════════════════════════════════════════════

class TestIntentClassification:
    """_classify_intent 的关键词覆盖测试。"""

    def setup_method(self):
        self.agent = OpsCopilotAgent(repo=make_mock_repo())

    def test_trace_query_by_run(self):
        assert self.agent._classify_intent("最近最慢的 run 是什么？") == "trace_query"

    def test_trace_query_by_failed(self):
        assert self.agent._classify_intent("某个 run 为什么失败？") == "trace_query"

    def test_eval_query_by_experiment(self):
        assert self.agent._classify_intent("最近有哪些实验？") == "eval_query"

    def test_eval_query_by_pass_rate(self):
        assert self.agent._classify_intent("哪个实验 pass rate 最低？") == "eval_query"

    def test_prompt_query_by_published(self):
        assert self.agent._classify_intent("最近哪个 prompt 发布过？") == "prompt_query"

    def test_prompt_query_by_versions(self):
        assert self.agent._classify_intent("某个 prompt 有几个版本？") == "prompt_query"

    def test_release_query_by_release(self):
        assert self.agent._classify_intent("最近有哪些 release？") == "release_query"

    def test_release_query_by_rollback(self):
        assert self.agent._classify_intent("最近一次 rollback 是什么？") == "release_query"

    def test_unknown_intent_unrecognized(self):
        assert self.agent._classify_intent("今天天气怎么样？") == "unknown_intent"

    def test_unknown_intent_empty_question(self):
        assert self.agent._classify_intent("") == "unknown_intent"


# ═══════════════════════════════════════════════════════════════════
# 2. 四类 Handler 正常返回（8 个必测问题）
# ═══════════════════════════════════════════════════════════════════

class TestHandlerNormalReturn:
    """使用 mock 数据验证 4 个 handler 正常路径。"""

    def setup_method(self):
        self.repo = make_mock_repo(
            slowest_runs=MOCK_SLOWEST_RUNS,
            failed_runs=MOCK_FAILED_RUNS,
            recent_experiments=MOCK_RECENT_EXPERIMENTS,
            lowest_experiment=MOCK_LOWEST_EXPERIMENT,
            published_prompts=MOCK_PUBLISHED_PROMPTS,
            prompt_versions=MOCK_PROMPT_VERSIONS,
            recent_releases=MOCK_RECENT_RELEASES,
            last_rollback=MOCK_LAST_ROLLBACK,
        )
        self.agent = OpsCopilotAgent(repo=self.repo)

    # ── trace ──────────────────────────────────────────────────────

    def test_q1_slowest_run(self):
        """Q1: 最近最慢的 run 是什么？"""
        out = self.agent.answer(
            OpsCopilotInput(question="最近最慢的 run 是什么？"), db=MOCK_DB
        )
        assert_output_schema(out)
        assert out.intent == "trace_query"
        assert out.fallback_used is False
        assert "fraud_detection_workflow" in out.answer
        assert "320" in out.answer
        print(f"\n[Q1] {out.answer}")

    def test_q2_why_run_failed(self):
        """Q2: 某个 run 为什么失败？"""
        out = self.agent.answer(
            OpsCopilotInput(question="某个 run 为什么失败？"), db=MOCK_DB
        )
        assert_output_schema(out)
        assert out.intent == "trace_query"
        assert out.fallback_used is False
        assert "forecast_workflow" in out.answer
        assert "TimeoutError" in out.answer
        print(f"\n[Q2] {out.answer}")

    # ── eval ───────────────────────────────────────────────────────

    def test_q3_recent_experiments(self):
        """Q3: 最近有哪些实验？"""
        out = self.agent.answer(
            OpsCopilotInput(question="最近有哪些实验？"), db=MOCK_DB
        )
        assert_output_schema(out)
        assert out.intent == "eval_query"
        assert out.fallback_used is False
        assert "fraud_v2_eval" in out.answer
        print(f"\n[Q3] {out.answer}")

    def test_q4_lowest_pass_rate(self):
        """Q4: 哪个实验 pass rate 最低？"""
        out = self.agent.answer(
            OpsCopilotInput(question="哪个实验 pass rate 最低？"), db=MOCK_DB
        )
        assert_output_schema(out)
        assert out.intent == "eval_query"
        assert out.fallback_used is False
        assert "sentiment_v3_eval" in out.answer
        assert "0.61" in out.answer
        print(f"\n[Q4] {out.answer}")

    # ── prompt ─────────────────────────────────────────────────────

    def test_q5_recently_published_prompt(self):
        """Q5: 最近哪个 prompt 发布过？"""
        out = self.agent.answer(
            OpsCopilotInput(question="最近哪个 prompt 发布过？"), db=MOCK_DB
        )
        assert_output_schema(out)
        assert out.intent == "prompt_query"
        assert out.fallback_used is False
        assert "fraud_scoring_prompt" in out.answer
        print(f"\n[Q5] {out.answer}")

    def test_q6_prompt_versions(self):
        """Q6: 某个 prompt 有几个版本？"""
        out = self.agent.answer(
            OpsCopilotInput(question="某个 prompt 有几个版本？"), db=MOCK_DB
        )
        assert_output_schema(out)
        assert out.intent == "prompt_query"
        assert out.fallback_used is False
        assert "fraud_scoring_prompt" in out.answer
        print(f"\n[Q6] {out.answer}")

    # ── release ────────────────────────────────────────────────────

    def test_q7_recent_releases(self):
        """Q7: 最近有哪些 release？"""
        out = self.agent.answer(
            OpsCopilotInput(question="最近有哪些 release？"), db=MOCK_DB
        )
        assert_output_schema(out)
        assert out.intent == "release_query"
        assert out.fallback_used is False
        assert "4.0.1" in out.answer
        print(f"\n[Q7] {out.answer}")

    def test_q8_last_rollback(self):
        """Q8: 最近一次 rollback 是什么？"""
        out = self.agent.answer(
            OpsCopilotInput(question="最近一次 rollback 是什么？"), db=MOCK_DB
        )
        assert_output_schema(out)
        assert out.intent == "release_query"
        assert out.fallback_used is False
        assert "4.0.0" in out.answer
        assert "admin" in out.answer
        print(f"\n[Q8] {out.answer}")


# ═══════════════════════════════════════════════════════════════════
# 3. unknown_intent 降级
# ═══════════════════════════════════════════════════════════════════

class TestUnknownIntentFallback:

    def setup_method(self):
        self.agent = OpsCopilotAgent(repo=make_mock_repo())

    def test_unrecognized_question_returns_fallback(self):
        out = self.agent.answer(
            OpsCopilotInput(question="今天吃什么好？"), db=MOCK_DB
        )
        assert_output_schema(out)
        assert out.intent == "unknown_intent"
        assert out.fallback_used is True
        assert out.error == "intent_unrecognized"
        assert out.answer  # 非空


# ═══════════════════════════════════════════════════════════════════
# 4. 空结果降级
# ═══════════════════════════════════════════════════════════════════

class TestEmptyResultFallback:

    def test_trace_empty_result(self):
        agent = OpsCopilotAgent(repo=make_mock_repo(slowest_runs=[], failed_runs=[]))
        out = agent.answer(
            OpsCopilotInput(question="最近最慢的 run 是什么？"), db=MOCK_DB
        )
        assert_output_schema(out)
        assert out.intent == "trace_query"
        assert out.fallback_used is True
        assert out.error == "empty_result"

    def test_eval_empty_result(self):
        agent = OpsCopilotAgent(
            repo=make_mock_repo(recent_experiments=[], lowest_experiment=None)
        )
        out = agent.answer(
            OpsCopilotInput(question="最近有哪些实验？"), db=MOCK_DB
        )
        assert_output_schema(out)
        assert out.intent == "eval_query"
        assert out.fallback_used is True
        assert out.error == "empty_result"

    def test_prompt_empty_result(self):
        agent = OpsCopilotAgent(
            repo=make_mock_repo(published_prompts=[], prompt_versions=[])
        )
        out = agent.answer(
            OpsCopilotInput(question="最近哪个 prompt 发布过？"), db=MOCK_DB
        )
        assert_output_schema(out)
        assert out.intent == "prompt_query"
        assert out.fallback_used is True
        assert out.error == "empty_result"

    def test_release_empty_result(self):
        agent = OpsCopilotAgent(
            repo=make_mock_repo(recent_releases=[], last_rollback=None)
        )
        out = agent.answer(
            OpsCopilotInput(question="最近有哪些 release？"), db=MOCK_DB
        )
        assert_output_schema(out)
        assert out.intent == "release_query"
        assert out.fallback_used is True
        assert out.error == "empty_result"


# ═══════════════════════════════════════════════════════════════════
# 5. 异常降级
# ═══════════════════════════════════════════════════════════════════

class TestExceptionFallback:

    def test_repo_raises_exception(self):
        repo = make_mock_repo()
        repo.get_slowest_runs.side_effect = RuntimeError("DB connection lost")
        agent = OpsCopilotAgent(repo=repo)
        out = agent.answer(
            OpsCopilotInput(question="最近最慢的 run 是什么？"), db=MOCK_DB
        )
        assert_output_schema(out)
        assert out.fallback_used is True
        assert out.error is not None
        assert "RuntimeError" in out.error
        assert out.answer  # 非空可读

    def test_db_unavailable_fallback(self):
        agent = OpsCopilotAgent(repo=make_mock_repo())
        out = agent.answer(
            OpsCopilotInput(question="最近最慢的 run 是什么？"), db=None
        )
        assert_output_schema(out)
        assert out.fallback_used is True
        assert out.error == "db_unavailable"
        assert out.answer


# ═══════════════════════════════════════════════════════════════════
# 6. 输出结构完整性（跨所有 handler）
# ═══════════════════════════════════════════════════════════════════

class TestOutputSchemaCompleteness:
    """确保每条 answer() 返回结果都包含 7 个必填字段。"""

    def setup_method(self):
        self.agent = OpsCopilotAgent(
            repo=make_mock_repo(
                slowest_runs=MOCK_SLOWEST_RUNS,
                failed_runs=MOCK_FAILED_RUNS,
                recent_experiments=MOCK_RECENT_EXPERIMENTS,
                lowest_experiment=MOCK_LOWEST_EXPERIMENT,
                published_prompts=MOCK_PUBLISHED_PROMPTS,
                prompt_versions=MOCK_PROMPT_VERSIONS,
                recent_releases=MOCK_RECENT_RELEASES,
                last_rollback=MOCK_LAST_ROLLBACK,
            )
        )

    @pytest.mark.parametrize("question", [
        "最近最慢的 run 是什么？",
        "最近有哪些实验？",
        "最近哪个 prompt 发布过？",
        "最近有哪些 release？",
        "今天天气怎么样？",         # unknown_intent
        "帮我发布最新 prompt",       # readonly_blocked
    ])
    def test_schema_for_all_paths(self, question):
        out = self.agent.answer(OpsCopilotInput(question=question), db=MOCK_DB)
        assert_output_schema(out)


# ═══════════════════════════════════════════════════════════════════
# 7. 只读保护生效
# ═══════════════════════════════════════════════════════════════════

class TestReadOnlyProtection:
    """验证写操作意图被拦截，返回只读提示，不触发任何 repo 调用。"""

    def setup_method(self):
        self.repo = make_mock_repo()
        self.agent = OpsCopilotAgent(repo=self.repo)

    def _assert_blocked(self, question: str):
        out = self.agent.answer(OpsCopilotInput(question=question), db=MOCK_DB)
        assert_output_schema(out)
        assert out.intent == "readonly_blocked", f"应被拦截：{question}"
        assert out.fallback_used is False
        assert out.error is None
        assert "只读诊断" in out.answer or "后台管理模块" in out.answer
        # repo 不应被调用
        self.repo.get_slowest_runs.assert_not_called()
        self.repo.get_recent_releases.assert_not_called()
        self.repo.get_recent_published_prompts.assert_not_called()

    def test_block_publish_prompt(self):
        self._assert_blocked("帮我发布最新 prompt")

    def test_block_rollback_release(self):
        self._assert_blocked("帮我回滚上一个 release")

    def test_block_approve_review(self):
        self._assert_blocked("帮我审批这个 review")

    def test_block_delete(self):
        self._assert_blocked("帮我删除这个实验")

    def test_block_modify(self):
        self._assert_blocked("帮我修改这个 prompt")
