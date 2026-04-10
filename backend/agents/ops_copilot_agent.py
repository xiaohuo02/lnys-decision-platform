# -*- coding: utf-8 -*-
"""backend/agents/ops_copilot_agent.py  v4.1

OpsCopilotAgent — 后台运维自然语言只读诊断助手

╔══════════════════════════════════════════════════════════════════╗
║  Agent 契约                                                       ║
╠══════════════════════════════════════════════════════════════════╣
║  职责                                                             ║
║    理解管理员自然语言问题，查询治理数据，给出结构化只读回答。        ║
║                                                                  ║
║  支持的 4 类问题                                                  ║
║    trace_query   — run/workflow trace 查询（最慢/失败 run）        ║
║    eval_query    — 评测实验查询（列表/pass rate）                  ║
║    prompt_query  — Prompt 版本与发布状态查询                      ║
║    release_query — Release 发布历史与 rollback 查询               ║
║                                                                  ║
║  不支持的动作                                                     ║
║    发布 / 回滚 / 修改 / 审批 / 删除 / 启用 / 禁用                 ║
║    → 统一返回只读拦截提示，不执行任何写操作                         ║
║                                                                  ║
║  降级策略（4 类）                                                  ║
║    1. 写操作动作意图  → 只读拦截，fallback_used=False              ║
║    2. 无法识别意图   → unknown_intent 降级，fallback_used=True     ║
║    3. 数据源不可用   → db_unavailable 降级，fallback_used=True     ║
║    4. 查询结果为空   → empty_result 降级，fallback_used=True       ║
║    5. 内部异常       → internal_error 降级，fallback_used=True     ║
║                                                                  ║
║  当前数据依赖                                                     ║
║    真实 DB 查询（通过 OpsCopilotReadRepository 只读方法）          ║
║    测试环境使用 mock repo                                         ║
║                                                                  ║
║  输入  OpsCopilotInput  (见 backend/schemas/ops_copilot.py)       ║
║  输出  OpsCopilotOutput (见 backend/schemas/ops_copilot.py)       ║
╚══════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import os
from typing import Any, Dict, List, Optional

import sqlalchemy
from loguru import logger

from backend.schemas.ops_copilot import OpsCopilotInput, OpsCopilotOutput


# ── 只读动作拦截关键词（必须有明确判断逻辑，不依赖 SQL 类型） ──────

_WRITE_ACTION_PATTERNS: List[str] = [
    "帮我发布", "请发布", "执行发布", "进行发布",
    "帮我回滚", "请回滚", "执行回滚", "进行回滚",
    "帮我审批", "请审批", "执行审批", "进行审批",
    "帮我修改", "请修改", "执行修改", "进行修改",
    "帮我删除", "请删除", "执行删除", "进行删除",
    "帮我启用", "请启用", "执行启用", "进行启用",
    "帮我禁用", "请禁用", "执行禁用", "进行禁用",
    "help me publish", "help me rollback", "help me approve",
]

# ── 意图分类关键词（仅 4 类，未命中走 unknown_intent）────────────

_INTENT_RULES: List[tuple[str, List[str]]] = [
    ("system_query",  ["运行状况", "系统状态", "系统健康", "整体状况",
                       "总体状态", "健康状态", "运行情况", "系统概览",
                       "运行状态", "系统运行", "健康检查", "系统概况",
                       "平台状态", "服务状态", "当前状态"]),
    ("trace_query",   ["trace", "run", "workflow", "失败", "超时",
                       "错误", "运行记录", "最慢", "slow", "failed", "fail",
                       "工作流", "耗时"]),
    ("review_query",  ["审核", "待审", "review", "审批", "审查",
                       "人工审核", "HITL", "hitl"]),
    ("eval_query",    ["eval", "评测", "实验", "准确率", "指标",
                       "pass rate", "passrate", "experiment"]),
    ("prompt_query",  ["prompt", "提示词", "发布过", "有几个版本",
                       "版本号", "published", "草稿", "待发布"]),
    ("release_query", ["release", "rollback", "最近发布", "有哪些release",
                       "上线", "发布了", "版本发布"]),
]


def _q_fingerprint(question: str) -> str:
    """返回问题的 SHA-1 前 8 位，用于日志追踪，不泄漏原文。"""
    return hashlib.sha1(question.encode("utf-8")).hexdigest()[:8]


# ── 只读数据访问层（Agent 不直接写 SQL） ─────────────────────────

class OpsCopilotReadRepository:
    """OpsCopilot 只读数据访问层。

    所有方法只执行 SELECT，严禁包含 INSERT / UPDATE / DELETE。
    Agent 主体通过此类获取数据，不直接拼接 SQL。
    """

    def get_slowest_runs(self, db, limit: int = 5) -> List[Dict[str, Any]]:
        """返回最近耗时最长的已完成 runs。"""
        rows = db.execute(sqlalchemy.text(
            "SELECT run_id, workflow_name, status, "
            "TIMESTAMPDIFF(SECOND, started_at, ended_at) AS duration_sec "
            "FROM runs WHERE ended_at IS NOT NULL "
            "ORDER BY duration_sec DESC LIMIT :limit"
        ), {"limit": limit}).fetchall()
        return [dict(r._mapping) for r in rows]

    def get_failed_runs(self, db, limit: int = 5) -> List[Dict[str, Any]]:
        """返回最近失败的 runs 及错误摘要。"""
        rows = db.execute(sqlalchemy.text(
            "SELECT run_id, workflow_name, error_message, started_at "
            "FROM runs WHERE status='failed' "
            "ORDER BY started_at DESC LIMIT :limit"
        ), {"limit": limit}).fetchall()
        return [dict(r._mapping) for r in rows]

    def get_recent_experiments(self, db, limit: int = 5) -> List[Dict[str, Any]]:
        """返回最近的评测实验列表。"""
        rows = db.execute(sqlalchemy.text(
            "SELECT experiment_id, name, status, pass_rate, created_at "
            "FROM eval_experiments ORDER BY created_at DESC LIMIT :limit"
        ), {"limit": limit}).fetchall()
        return [dict(r._mapping) for r in rows]

    def get_lowest_pass_rate_experiment(self, db) -> Optional[Dict[str, Any]]:
        """返回已完成实验中 pass_rate 最低的一条。"""
        row = db.execute(sqlalchemy.text(
            "SELECT experiment_id, name, pass_rate, created_at "
            "FROM eval_experiments WHERE status='completed' "
            "ORDER BY pass_rate ASC LIMIT 1"
        )).fetchone()
        return dict(row._mapping) if row else None

    def get_recent_published_prompts(self, db, limit: int = 5) -> List[Dict[str, Any]]:
        """返回最近发布状态的 prompts。"""
        rows = db.execute(sqlalchemy.text(
            "SELECT name, agent_name, version, updated_at "
            "FROM prompts WHERE status='active' "
            "ORDER BY updated_at DESC LIMIT :limit"
        ), {"limit": limit}).fetchall()
        return [dict(r._mapping) for r in rows]

    def get_prompt_versions(self, db, limit: int = 10) -> List[Dict[str, Any]]:
        """返回各 prompt 的版本数量统计。"""
        rows = db.execute(sqlalchemy.text(
            "SELECT name, COUNT(*) AS version_count "
            "FROM prompts GROUP BY name ORDER BY version_count DESC LIMIT :limit"
        ), {"limit": limit}).fetchall()
        return [dict(r._mapping) for r in rows]

    def get_recent_releases(self, db, limit: int = 5) -> List[Dict[str, Any]]:
        """返回最近的 release 记录。"""
        rows = db.execute(sqlalchemy.text(
            "SELECT release_id, name, version, status, released_by, created_at "
            "FROM releases ORDER BY created_at DESC LIMIT :limit"
        ), {"limit": limit}).fetchall()
        return [dict(r._mapping) for r in rows]

    def get_last_rollback(self, db) -> Optional[Dict[str, Any]]:
        """返回最近一次 rollback 记录，无则返回 None。"""
        row = db.execute(sqlalchemy.text(
            "SELECT release_id, name, version, released_by, created_at "
            "FROM releases WHERE status='rolled_back' "
            "ORDER BY created_at DESC LIMIT 1"
        )).fetchone()
        return dict(row._mapping) if row else None

    def get_pending_reviews(self, db) -> Dict[str, Any]:
        """返回待审核任务统计和最近待审记录。"""
        row = db.execute(sqlalchemy.text(
            "SELECT COUNT(*) AS total, "
            "SUM(status='pending') AS pending, "
            "SUM(status='in_review') AS in_review, "
            "SUM(status='approved') AS approved, "
            "SUM(status='rejected') AS rejected "
            "FROM review_cases"
        )).fetchone()
        stats = dict(row._mapping) if row else {}
        recent = db.execute(sqlalchemy.text(
            "SELECT case_id, review_type, priority, status, subject, created_at "
            "FROM review_cases WHERE status IN ('pending','in_review') "
            "ORDER BY created_at DESC LIMIT 5"
        )).fetchall()
        return {"stats": stats, "recent": [dict(r._mapping) for r in recent]}

    def get_system_summary(self, db) -> Dict[str, Any]:
        """返回系统整体运行状态汇总。"""
        runs_row = db.execute(sqlalchemy.text(
            "SELECT COUNT(*) AS total, "
            "SUM(status='completed') AS completed, "
            "SUM(status='failed') AS failed, "
            "SUM(status='running') AS running "
            "FROM runs"
        )).fetchone()
        runs = dict(runs_row._mapping) if runs_row else {}
        reviews_row = db.execute(sqlalchemy.text(
            "SELECT COUNT(*) AS total, SUM(status='pending') AS pending "
            "FROM review_cases"
        )).fetchone()
        reviews = dict(reviews_row._mapping) if reviews_row else {}
        prompts_row = db.execute(sqlalchemy.text(
            "SELECT COUNT(*) AS total, SUM(status='active') AS active "
            "FROM prompts"
        )).fetchone()
        prompts = dict(prompts_row._mapping) if prompts_row else {}
        releases_row = db.execute(sqlalchemy.text(
            "SELECT COUNT(*) AS total FROM releases"
        )).fetchone()
        releases = dict(releases_row._mapping) if releases_row else {}
        return {"runs": runs, "reviews": reviews, "prompts": prompts, "releases": releases}


# ── Agent 主体 ────────────────────────────────────────────────────

class OpsCopilotAgent:
    """运维 Copilot Agent。

    职责：只读动作拦截、意图分类、路由、汇总、解释、降级。
    数据访问统一通过 OpsCopilotReadRepository，Agent 本体不直接执行 SQL。
    """

    def __init__(self, repo: Optional[OpsCopilotReadRepository] = None) -> None:
        self._repo: OpsCopilotReadRepository = repo or OpsCopilotReadRepository()

    # ── 异步 LLM 增强回答 ────────────────────────────────────

    async def aanswer(self, inp: OpsCopilotInput, db=None) -> OpsCopilotOutput:
        """
        异步回答：先走同步 answer() 获取结构化数据，
        再用 LLM 生成更自然的回答。LLM 失败时降级到同步结果。
        """
        base_output = self.answer(inp, db=db)

        # 降级场景或只读拦截时不调 LLM
        if base_output.fallback_used or base_output.intent == "readonly_blocked":
            return base_output

        llm_answer = await self._llm_enhance(
            question=inp.question,
            intent=base_output.intent,
            base_answer=base_output.answer,
            sources=base_output.sources,
        )
        if llm_answer:
            base_output.answer = llm_answer

        return base_output

    async def _llm_enhance(
        self,
        question: str,
        intent: str,
        base_answer: str,
        sources: List[str],
    ) -> Optional[str]:
        """用 qwen3.5-plus 增强运维回答"""
        try:
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import SystemMessage, HumanMessage

            api_key  = os.getenv("LLM_API_KEY", "")
            base_url = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
            model    = os.getenv("LLM_MODEL_NAME", "qwen3.5-plus-2026-02-15")

            if not api_key:
                return None

            system_prompt = (
                "你是柠优生活平台的运维诊断助手。\n"
                "规则：\n"
                "- 基于提供的查询结果回答，不要编造数据\n"
                "- 回答简洁专业，150字以内\n"
                "- 可以给出诊断建议和排查方向\n"
                "- 不能执行任何写操作（发布/回滚/修改/审批）\n"
                "- 如果数据显示异常，给出可能的原因分析\n"
            )

            user_prompt = (
                f"管理员问题: {question}\n"
                f"识别意图: {intent}\n"
                f"查询结果: {base_answer}\n"
                f"数据来源: {', '.join(sources)}\n\n"
                f"请生成更清晰的运维诊断回答:"
            )

            llm = ChatOpenAI(
                api_key=api_key,
                base_url=base_url,
                model=model,
                max_tokens=400,
                temperature=0.3,
                timeout=60,
            )
            resp = await llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ])
            content = resp.content.strip() if resp.content else ""

            if len(content) >= 10:
                logger.info(
                    f"[OpsCopilot] LLM enhanced: {len(content)}c, model={model}"
                )
                return content
            return None
        except Exception as e:
            logger.warning(f"[OpsCopilot] LLM enhance failed (fallback): {e}")
            return None

    def answer(self, inp: OpsCopilotInput, db=None) -> OpsCopilotOutput:
        """处理一次 OpsCopilot 问答请求，返回统一结构化输出。"""
        fp = _q_fingerprint(inp.question)
        logger.info(f"[OpsCopilot] received fp={fp} len={len(inp.question)}")

        # 1. 只读动作拦截（必须在意图分类前执行）
        if self._is_write_action(inp.question):
            logger.info(f"[OpsCopilot] write-action blocked fp={fp}")
            return OpsCopilotOutput(
                intent="readonly_blocked",
                answer=(
                    "当前 Agent 仅支持只读诊断，不支持执行发布、回滚、"
                    "审批、修改、删除等写操作。如需操作，请前往对应的后台管理模块。"
                ),
                confidence=1.0,
                sources=[],
                suggested_actions=["前往对应后台管理模块执行操作"],
                fallback_used=False,
                error=None,
            )

        # 2. 意图分类
        intent = self._classify_intent(inp.question)
        logger.info(f"[OpsCopilot] intent={intent} fp={fp}")

        # 3. 数据源可用性检查
        if db is None:
            logger.warning(f"[OpsCopilot] db_unavailable fallback fp={fp}")
            return self._make_fallback(
                intent=intent,
                answer="暂时无法查询治理数据，请直接访问治理控制台。",
                error="db_unavailable",
            )

        # 4. 路由 & 执行
        try:
            logger.info(f"[OpsCopilot] dispatch intent={intent} fp={fp}")
            return self._dispatch(intent, inp.question, db)
        except Exception as exc:
            logger.error(
                f"[OpsCopilot] internal_error intent={intent} fp={fp} "
                f"exc_type={type(exc).__name__}"
            )
            return self._make_fallback(
                intent=intent,
                answer="查询时遇到内部异常，请稍后重试或直接访问治理控制台。",
                error=f"{type(exc).__name__}: {str(exc)[:120]}",
            )

    # ── 只读动作拦截 ────────────────────────────────────────────

    def _is_write_action(self, question: str) -> bool:
        """判断问题是否包含写操作动作意图。代码级判断，不依赖 SQL 只读性。"""
        q = question.lower()
        return any(pattern in q for pattern in _WRITE_ACTION_PATTERNS)

    # ── 意图分类 ────────────────────────────────────────────────

    def _classify_intent(self, question: str) -> str:
        """基于关键词打分分类意图；未命中任何类别时返回 unknown_intent。"""
        q = question.lower()
        best_intent, best_score = "unknown_intent", 0
        for intent, keywords in _INTENT_RULES:
            score = sum(1 for kw in keywords if kw in q)
            if score > best_score:
                best_score, best_intent = score, intent
        return best_intent

    # ── 路由 ────────────────────────────────────────────────────

    def _dispatch(self, intent: str, question: str, db) -> OpsCopilotOutput:
        handlers = {
            "system_query":   self._handle_system_query,
            "trace_query":    self._handle_trace_query,
            "review_query":   self._handle_review_query,
            "eval_query":     self._handle_eval_query,
            "prompt_query":   self._handle_prompt_query,
            "release_query":  self._handle_release_query,
            "unknown_intent": self._handle_unknown_intent,
        }
        handler = handlers.get(intent, self._handle_unknown_intent)
        return handler(question, db)

    # ── 6 类 Handler（+ unknown）────────────────────────────────

    def _handle_system_query(self, question: str, db) -> OpsCopilotOutput:
        """处理系统整体运行状态查询：runs/reviews/prompts/releases 汇总。"""
        summary = self._repo.get_system_summary(db)
        runs = summary.get("runs", {})
        reviews = summary.get("reviews", {})
        prompts = summary.get("prompts", {})
        releases = summary.get("releases", {})

        total_runs = int(runs.get("total") or 0)
        completed = int(runs.get("completed") or 0)
        failed = int(runs.get("failed") or 0)
        running = int(runs.get("running") or 0)
        pending_reviews = int(reviews.get("pending") or 0)
        total_prompts = int(prompts.get("total") or 0)
        active_prompts = int(prompts.get("active") or 0)
        total_releases = int(releases.get("total") or 0)

        parts = [
            f"工作流：共 {total_runs} 次运行，{completed} 次完成，{failed} 次失败，{running} 个运行中。",
            f"审核任务：{pending_reviews} 个待处理。",
            f"Prompt：共 {total_prompts} 个，{active_prompts} 个已激活。",
            f"发布记录：共 {total_releases} 条。",
        ]
        health = "正常" if failed == 0 and running == 0 else ("存在异常" if failed > 0 else "运行中")

        return OpsCopilotOutput(
            intent="system_query",
            answer=f"系统整体状态：{health}。" + " ".join(parts),
            confidence=0.9,
            sources=["runs 表", "review_cases 表", "prompts 表", "releases 表"],
            suggested_actions=["前往 Traces 查看运行详情", "前往审核中心处理待审任务"],
            fallback_used=False,
            error=None,
        )

    def _handle_review_query(self, question: str, db) -> OpsCopilotOutput:
        """处理审核任务查询：待审核数量、最近待审记录。"""
        data = self._repo.get_pending_reviews(db)
        stats = data.get("stats", {})
        recent = data.get("recent", [])

        total = int(stats.get("total") or 0)
        pending = int(stats.get("pending") or 0)
        in_review = int(stats.get("in_review") or 0)
        approved = int(stats.get("approved") or 0)
        rejected = int(stats.get("rejected") or 0)

        if total == 0:
            return self._make_fallback(
                intent="review_query",
                answer="暂无审核任务数据。",
                error="empty_result",
            )

        parts = [
            f"审核任务共 {total} 个：{pending} 个待处理，{in_review} 个审核中，"
            f"{approved} 个已通过，{rejected} 个已驳回。"
        ]

        if recent:
            top = recent[0]
            parts.append(
                f"最近待审：「{(top.get('subject') or '-')[:40]}」"
                f"（{top.get('review_type')}，优先级 {top.get('priority')}）。"
            )

        return OpsCopilotOutput(
            intent="review_query",
            answer=" ".join(parts),
            confidence=0.85,
            sources=["review_cases 表"],
            suggested_actions=["前往审核中心处理待审任务"],
            fallback_used=False,
            error=None,
        )

    def _handle_trace_query(self, question: str, db) -> OpsCopilotOutput:
        """处理 trace/run 相关查询：最慢 run、失败 run。"""
        slowest = self._repo.get_slowest_runs(db)
        failed = self._repo.get_failed_runs(db)

        if not slowest and not failed:
            logger.info("[OpsCopilot] trace_query empty_result fallback")
            return self._make_fallback(
                intent="trace_query",
                answer="暂无可查询的 run 数据，请确认数据是否已产生。",
                error="empty_result",
            )

        parts: List[str] = []
        sources: List[str] = []

        if slowest:
            top = slowest[0]
            parts.append(
                f"最近最慢的 run：工作流 '{top.get('workflow_name')}'，"
                f"耗时 {top.get('duration_sec')} 秒（ID: {top.get('run_id')}）。"
            )
            sources.append("runs 表（按耗时降序）")

        if failed:
            top_fail = failed[0]
            err_msg = (top_fail.get("error_message") or "无错误信息")[:80]
            parts.append(
                f"最近失败的 run：工作流 '{top_fail.get('workflow_name')}'，"
                f"原因：{err_msg}。"
            )
            sources.append("runs 表（status=failed）")

        return OpsCopilotOutput(
            intent="trace_query",
            answer=" ".join(parts),
            confidence=0.85,
            sources=sources,
            suggested_actions=["前往 Traces 页面查看详细日志"],
            fallback_used=False,
            error=None,
        )

    def _handle_eval_query(self, question: str, db) -> OpsCopilotOutput:
        """处理评测实验相关查询：实验列表、pass rate 最低实验。"""
        recent = self._repo.get_recent_experiments(db)
        lowest = self._repo.get_lowest_pass_rate_experiment(db)

        if not recent:
            logger.info("[OpsCopilot] eval_query empty_result fallback")
            return self._make_fallback(
                intent="eval_query",
                answer="暂无评测实验数据。",
                error="empty_result",
            )

        names = "、".join(e.get("name", "unknown") for e in recent[:3])
        parts = [f"最近有 {len(recent)} 个评测实验，包括：{names} 等。"]
        sources = ["eval_experiments 表（最近 5 条）"]

        if lowest:
            parts.append(
                f"pass rate 最低的实验：'{lowest.get('name')}'，"
                f"pass rate = {lowest.get('pass_rate')}。"
            )
            sources.append("eval_experiments 表（pass_rate ASC）")

        return OpsCopilotOutput(
            intent="eval_query",
            answer=" ".join(parts),
            confidence=0.85,
            sources=sources,
            suggested_actions=["前往 Eval Center 查看实验详情"],
            fallback_used=False,
            error=None,
        )

    def _handle_prompt_query(self, question: str, db) -> OpsCopilotOutput:
        """处理 Prompt 版本与发布状态查询：已发布 prompt、版本数量。"""
        published = self._repo.get_recent_published_prompts(db)
        versions = self._repo.get_prompt_versions(db)

        if not published and not versions:
            logger.info("[OpsCopilot] prompt_query empty_result fallback")
            return self._make_fallback(
                intent="prompt_query",
                answer="暂无 Prompt 数据。",
                error="empty_result",
            )

        parts: List[str] = []
        sources: List[str] = []

        if published:
            names = "、".join(p.get("name", "?") for p in published[:3])
            parts.append(f"最近发布过的 Prompt：{names}。")
            sources.append("prompts 表（status=published，按时间降序）")

        if versions:
            ver_info = "、".join(
                f"{v.get('name')}（{v.get('version_count')} 个版本）"
                for v in versions[:3]
            )
            parts.append(f"版本数量：{ver_info}。")
            sources.append("prompts 表（按版本数分组统计）")

        return OpsCopilotOutput(
            intent="prompt_query",
            answer=" ".join(parts),
            confidence=0.85,
            sources=sources,
            suggested_actions=["前往 Prompt Center 查看版本管理"],
            fallback_used=False,
            error=None,
        )

    def _handle_release_query(self, question: str, db) -> OpsCopilotOutput:
        """处理 Release 发布历史查询：release 列表、最近一次 rollback。"""
        recent = self._repo.get_recent_releases(db)
        last_rb = self._repo.get_last_rollback(db)

        if not recent:
            logger.info("[OpsCopilot] release_query empty_result fallback")
            return self._make_fallback(
                intent="release_query",
                answer="暂无 Release 数据。",
                error="empty_result",
            )

        names = "、".join(
            f"{r.get('name')} v{r.get('version')}" for r in recent[:3]
        )
        parts = [f"最近有 {len(recent)} 次 release：{names}。"]
        sources = ["releases 表（最近 5 条）"]

        if last_rb:
            parts.append(
                f"最近一次 rollback：'{last_rb.get('name')} v{last_rb.get('version')}'，"
                f"操作者：{last_rb.get('released_by')}。"
            )
            sources.append("releases 表（status=rolled_back）")
        else:
            parts.append("当前无 rollback 记录。")

        return OpsCopilotOutput(
            intent="release_query",
            answer=" ".join(parts),
            confidence=0.85,
            sources=sources,
            suggested_actions=["前往 Release Center 查看发布历史"],
            fallback_used=False,
            error=None,
        )

    def _handle_unknown_intent(self, question: str, db=None) -> OpsCopilotOutput:
        """处理无法识别意图的问题，统一降级。"""
        logger.info("[OpsCopilot] unknown_intent fallback")
        return self._make_fallback(
            intent="unknown_intent",
            answer=(
                "无法识别您的问题意图。当前支持查询：trace/run 状态、"
                "评测实验、Prompt 版本、Release 历史。"
                "请换一种提问方式，或前往治理控制台。"
            ),
            error="intent_unrecognized",
            suggested_actions=["前往治理控制台查看各模块状态"],
        )

    # ── 降级工厂 ─────────────────────────────────────────────────

    @staticmethod
    def _make_fallback(
        intent: str,
        answer: str,
        error: str,
        suggested_actions: Optional[List[str]] = None,
    ) -> OpsCopilotOutput:
        """生成统一降级输出。fallback_used=True，answer 不为空，error 有值。"""
        return OpsCopilotOutput(
            intent=intent,
            answer=answer,
            confidence=0.0,
            sources=[],
            suggested_actions=suggested_actions or [],
            fallback_used=True,
            error=error,
        )


ops_copilot_agent = OpsCopilotAgent()
