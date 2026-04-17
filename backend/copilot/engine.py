# -*- coding: utf-8 -*-
"""backend/copilot/engine.py — CopilotEngine 核心引擎

统一入口，负责：
1. 构建上下文（三层记忆）
2. 权限校验
3. LLM Function Calling 路由到 Skill
4. Skill 执行 + 流式事件输出
5. LLM 综合回答
6. 对话持久化
"""
from __future__ import annotations

import asyncio
import json
import time
import traceback
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional, TYPE_CHECKING

import sqlalchemy
from loguru import logger

from backend.config import settings
# R6: 顶部统一 import telemetry，取代原 run() 内 11 处 inline 重复 import
from backend.core.telemetry import telemetry, TelemetryEventType
from backend.copilot.events import (
    CopilotEvent, EventType,
    run_start_event, run_end_event, run_error_event,
    text_delta_event, thinking_event, suggestions_event,
    intent_event, confidence_event, sources_event,
    context_status_event, security_check_event,
    memory_recall_event, decision_step_event,
)
from backend.copilot.base_skill import BaseCopilotSkill, SkillContext
from backend.copilot.registry import SkillRegistry
from backend.copilot.context import ContextManager
from backend.copilot.permissions import PermissionChecker, OPS_ONLY_SKILLS
from backend.copilot.agent_logger import (
    get_agent_logger, SkillCallTracer,
)

if TYPE_CHECKING:
    from backend.core.container import AgentContainer


class SkillCallDeduplicator:
    """检测连续重复的 Skill 调用并返回缓存结果。

    规则: 连续 max_repeat 次相同 skill_name + 相同参数 hash → 返回缓存 + 提示。

    并发/内存安全:
      - asyncio.Lock 保护 _recent / _cache 并发访问
      - _cache 按 (insert_ts, args_hash) 维护，统一按 cache_ttl 过期
      - _cache 达到 max_cache_size 时 LRU 淘汰最旧项，避免内存单调增长
    """

    def __init__(
        self,
        max_repeat: int = 3,
        cache_ttl: float = 120.0,
        max_cache_size: int = 256,
        max_recent_size: int = 512,
    ):
        self._max_repeat = max_repeat
        self._cache_ttl = cache_ttl
        self._max_cache_size = max_cache_size
        self._max_recent_size = max_recent_size
        self._recent: list[tuple[str, str, float]] = []        # (skill, args_hash, ts)
        self._cache: dict[str, tuple[Any, float]] = {}         # args_hash → (result, insert_ts)
        self._lock = asyncio.Lock()

    @staticmethod
    def _args_hash(args: Dict[str, Any]) -> str:
        import hashlib
        payload = json.dumps(args, sort_keys=True, default=str).encode()
        return hashlib.md5(payload).hexdigest()[:12]

    async def check_and_cache(
        self, skill_name: str, args: Dict[str, Any], result: Any = None,
    ) -> tuple[bool, Any]:
        """返回 (is_duplicate, cached_result)。如果 result 非 None 则写入缓存。"""
        args_hash = self._args_hash(args)
        now = time.time()

        async with self._lock:
            # 清理过期 recent 记录
            self._recent = [
                (s, h, t) for s, h, t in self._recent if now - t < self._cache_ttl
            ]
            # 清理过期 cache 条目
            expired = [k for k, (_, ts) in self._cache.items() if now - ts >= self._cache_ttl]
            for k in expired:
                self._cache.pop(k, None)

            # 写入缓存（含容量上限 LRU 淘汰）
            if result is not None:
                if (
                    args_hash not in self._cache
                    and len(self._cache) >= self._max_cache_size
                ):
                    # 按插入时间淘汰最旧一项
                    oldest = min(self._cache.items(), key=lambda kv: kv[1][1])[0]
                    self._cache.pop(oldest, None)
                self._cache[args_hash] = (result, now)

            # 记录本次调用（含 recent 容量上限）
            self._recent.append((skill_name, args_hash, now))
            if len(self._recent) > self._max_recent_size:
                self._recent = self._recent[-self._max_recent_size:]

            # 检测连续重复
            consecutive = 0
            for s, h, _ in reversed(self._recent):
                if s == skill_name and h == args_hash:
                    consecutive += 1
                else:
                    break

            if consecutive >= self._max_repeat and args_hash in self._cache:
                return True, self._cache[args_hash][0]
            return False, None


class CopilotEngine:
    """统一 Copilot 引擎 — 运维助手和运营助手共用。

    R6-2: 构造可接收 AgentContainer。当 settings.COPILOT_CONTAINER_ENABLED 为 True
    且 container 非空时，从 container 取 skill_registry 等共享单例；否则走旧路径。
    这个机制让 Engine 在不破坏旧调用方的前提下，逐步迁移到 container 依赖注入。
    """

    def __init__(self, redis=None, db=None, container: "Optional[AgentContainer]" = None):
        self._redis = redis
        self._db = db
        self._container = container
        # Skill registry: 优先从 container 取（允许测试替换），fallback 单例
        if container is not None and settings.COPILOT_CONTAINER_ENABLED:
            self._registry = container.skill_registry
        else:
            self._registry = SkillRegistry.instance()
        self._context_mgr = ContextManager(redis=redis, db=db)
        self._permission = PermissionChecker(db=db)
        self._dedup = SkillCallDeduplicator()

    async def run(
        self,
        question: str,
        mode: str,
        user_id: str,
        user_role: str,
        thread_id: str,
        page_context: Optional[Dict[str, Any]] = None,
        source: str = "web",
    ) -> AsyncGenerator[CopilotEvent, None]:
        """主入口：处理用户问题，yield SSE 事件流

        Args:
            question:     用户自然语言问题
            mode:         "ops" | "biz"
            user_id:      用户 ID
            user_role:    用户角色
            thread_id:    对话线程 ID
            page_context: 当前页面上下文
            source:       来源 "web" | "feishu" | "scheduler" | "api"
        """
        start_time = time.time()
        agent_log = get_agent_logger(mode)
        agent_log.info(
            f"[engine:run] question='{question[:80]}' mode={mode} "
            f"user={user_id} role={user_role} source={source}"
        )
        _acc_tokens = 0   # 累计本次对话所有 LLM 调用的 token
        _acc_cost   = 0.0
        _output_parts: list[str] = []   # 收集输出文本用于 output_summary

        # 0. 输入预校验 — 空问题 / 过短问题快速返回
        question = (question or "").strip()
        if len(question) < 1:
            yield run_start_event(thread_id, mode)
            yield text_delta_event("请输入您的问题，我会为您分析。")
            yield run_end_event(thread_id, self._elapsed_ms(start_time))
            return

        # 1. 生命周期开始
        yield run_start_event(thread_id, mode)

        # 1.1 输入安全检查 — InputGuard
        try:
            from backend.governance.guardrails import input_guard
            guard_result = input_guard.check(question)
            guard_hits = [
                {"rule": h.rule, "severity": h.severity, "message": h.message}
                for h in (guard_result.hits or [])
            ]
            yield security_check_event(
                check_type="input_guard",
                passed=guard_result.passed,
                detail=guard_result.blocked_reason or f"{len(guard_result.hits or [])} checks",
                hits=guard_hits or None,
            )
            if not guard_result.passed:
                yield text_delta_event(f"⚠️ {guard_result.blocked_reason}")
                yield run_end_event(thread_id, self._elapsed_ms(start_time))
                return
            if guard_result.sanitized_text:
                question = guard_result.sanitized_text
            # Emit security telemetry for dashboard aggregation
            try:
                _se = TelemetryEventType.SECURITY_CHECK_PASSED if guard_result.passed else TelemetryEventType.SECURITY_CHECK_BLOCKED
                telemetry.emit(_se, {
                    "check_type": "input_guard",
                    "hits_count": len(guard_result.hits or []),
                }, component="InputGuard", thread_id=thread_id)
                # Emit PII detection events
                pii_hits = [h for h in (guard_result.hits or []) if h.rule.startswith("pii_")]
                if pii_hits:
                    telemetry.emit(TelemetryEventType.PII_DETECTED, {
                        "direction": "input",
                        "count": len(pii_hits),
                        "rules": [h.rule for h in pii_hits],
                    }, component="InputGuard", thread_id=thread_id)
            except Exception:
                pass
        except Exception as e:
            agent_log.debug(f"[engine:guard] input_guard check skipped: {e}")

        try:
            telemetry.emit(TelemetryEventType.RUN_STARTED, {
                "mode": mode, "user_id": user_id, "source": source,
            }, component="CopilotEngine", thread_id=thread_id)
        except Exception:
            pass

        try:
            # 2. 构建上下文
            context = await self._context_mgr.build(
                thread_id=thread_id,
                user_id=user_id,
                user_role=user_role,
                mode=mode,
                page_context=page_context,
                source=source,
            )

            # 保存用户消息到 Redis
            await self._context_mgr.save_to_thread_history(thread_id, "user", question)

            # 2.5 上下文治理 — evaluate token budget, auto-compact if needed
            try:
                from backend.core.context_monitor import context_monitor, ContextStatus
                from backend.core.token_counter import token_counter

                ctx_tokens = token_counter.estimate_messages(context.thread_history)
                ctx_status = context_monitor.evaluate(ctx_tokens, thread_id)
                _max_tokens = context_monitor.budget.max_tokens
                _usage_pct = (ctx_tokens / _max_tokens * 100) if _max_tokens > 0 else 0

                telemetry.emit(TelemetryEventType.CONTEXT_EVALUATED, {
                    "tokens": ctx_tokens,
                    "status": ctx_status.value,
                    "max_tokens": _max_tokens,
                }, component="CopilotEngine", thread_id=thread_id)

                if ctx_status == ContextStatus.NEEDS_COMPACT:
                    agent_log.info(f"[engine:ctx] NEEDS_COMPACT tokens={ctx_tokens} thread={thread_id}")
                    telemetry.emit(TelemetryEventType.COMPACT_TRIGGERED, {
                        "tokens_before": ctx_tokens,
                        "thread_id": thread_id,
                    }, component="CopilotEngine", thread_id=thread_id)

                    result = await context_monitor.compact_messages(
                        context.thread_history, thread_id=thread_id
                    )
                    if result.is_effective:
                        context.thread_history = result.compacted_messages
                        telemetry.emit(TelemetryEventType.COMPACT_COMPLETED, {
                            "tokens_before": result.tokens_before,
                            "tokens_after": result.tokens_after,
                            "messages_before": result.messages_before,
                            "messages_after": result.messages_after,
                            "duration_ms": result.duration_ms,
                        }, component="CopilotEngine", thread_id=thread_id)
                        yield context_status_event(
                            status="compacted", tokens=result.tokens_after,
                            max_tokens=_max_tokens,
                            usage_pct=result.tokens_after / _max_tokens * 100 if _max_tokens else 0,
                            compacted=True,
                            tokens_before=result.tokens_before,
                            tokens_after=result.tokens_after,
                        )
                    else:
                        yield context_status_event(
                            status=ctx_status.value, tokens=ctx_tokens,
                            max_tokens=_max_tokens, usage_pct=_usage_pct,
                        )
                elif ctx_status == ContextStatus.CIRCUIT_BREAK:
                    agent_log.error(f"[engine:ctx] CIRCUIT_BREAK thread={thread_id} tokens={ctx_tokens}")
                    yield context_status_event(
                        status="circuit_break", tokens=ctx_tokens,
                        max_tokens=_max_tokens, usage_pct=_usage_pct,
                    )
                    yield text_delta_event("⚠️ 当前对话过长，建议开启新对话。")
                else:
                    yield context_status_event(
                        status="healthy", tokens=ctx_tokens,
                        max_tokens=_max_tokens, usage_pct=_usage_pct,
                    )
            except Exception as e:
                agent_log.warning(f"[engine:ctx] context governance check failed (non-fatal): {e}")

            # 2.6 记忆召回事件 — 让前端知道用了哪些记忆层
            try:
                mem_layers_used = []
                if getattr(context, 'redis_history_count', 0) > 0:
                    mem_layers_used.append(("L1_redis", context.redis_history_count))
                if getattr(context, 'memory_count', 0) > 0:
                    mem_layers_used.append(("L2_memory", context.memory_count))
                if getattr(context, 'rules_count', 0) > 0:
                    mem_layers_used.append(("L3_rules", context.rules_count))
                for layer, count in mem_layers_used:
                    yield memory_recall_event(layer=layer, count=count)
                    try:
                        telemetry.emit(TelemetryEventType.MEMORY_RECALLED, {
                            "layer": layer, "count": count,
                        }, component="CopilotEngine", thread_id=thread_id)
                    except Exception:
                        pass
            except Exception:
                pass

            # 3. 获取可用 Skill
            allowed_skills = await self._permission.get_allowed_skills(user_id, user_role, mode)
            available_skills = self._registry.get_available_skills(mode, user_role, allowed_skills)

            if not available_skills:
                yield text_delta_event("抱歉，当前没有可用的分析功能。请联系管理员配置权限。")
                yield run_end_event(thread_id, self._elapsed_ms(start_time))
                return

            # 4. LLM Function Calling 路由
            yield decision_step_event("routing", f"正在分析意图，{len(available_skills)} 个 Skill 可用")
            yield thinking_event("start")
            yield thinking_event("delta", "Analyzing user intent...")

            selected_skill, tool_args, route_tokens = await self._route_to_skill(
                question, context, available_skills
            )
            _acc_tokens += route_tokens

            if selected_skill is None:
                # 没有匹配的 Skill → 通用对话
                yield thinking_event("delta", "General question, generating response...")
                yield thinking_event("end")
                yield intent_event("general_chat")
                yield confidence_event(0.5)

                async for event in self._general_chat(question, context):
                    yield event
                    if event.type == EventType.TEXT_DELTA and event.content:
                        _output_parts.append(str(event.content))
            else:
                yield thinking_event("delta", f"Routing to {selected_skill.display_name}...")
                yield thinking_event("end")
                yield intent_event(selected_skill.name)
                yield confidence_event(0.9)

                # 4.5 重复调用检测
                is_dup, cached = await self._dedup.check_and_cache(selected_skill.name, tool_args)
                if is_dup and cached is not None:
                    yield CopilotEvent(
                        type=EventType.SKILL_CACHE_HIT,
                        metadata={
                            "skill": selected_skill.name,
                            "reason": "连续重复调用，返回缓存结果",
                        },
                    )
                    yield decision_step_event(
                        "cache_hit",
                        f"{selected_skill.display_name} 结果命中缓存",
                    )
                    skill_data = cached
                    # 跳过执行，直接走综合回答（§3.2 abstain 短路）
                    if skill_data and not skill_data.get("abstain"):
                        async for event in self._synthesize_answer(question, context, selected_skill, skill_data):
                            yield event
                            if event.type == EventType.TEXT_DELTA and event.content:
                                _output_parts.append(str(event.content))
                    elapsed_ms = self._elapsed_ms(start_time)
                    yield run_end_event(thread_id, elapsed_ms)
                    return

                # 5. 执行 Skill
                yield decision_step_event("skill_exec", f"执行 {selected_skill.display_name}")
                context.tool_args = tool_args
                tracer = SkillCallTracer(mode, selected_skill.name, user_id, thread_id)
                tracer.start()

                yield CopilotEvent(
                    type=EventType.TOOL_CALL_START,
                    metadata={
                        "skill": selected_skill.name,
                        "display_name": selected_skill.display_name,
                    },
                )

                skill_data = None
                try:
                    async with asyncio.timeout(60):
                        async for event in selected_skill.execute(question, context):
                            if event.type == EventType.TOOL_RESULT:
                                skill_data = event.data
                            yield event
                            tracer.log_event(event.type.value)

                    yield CopilotEvent(type=EventType.TOOL_CALL_END, metadata={"skill": selected_skill.name})
                    tracer.end(success=True)

                    # 缓存 Skill 结果用于去重
                    if skill_data:
                        await self._dedup.check_and_cache(selected_skill.name, tool_args, result=skill_data)

                    try:
                        telemetry.emit(TelemetryEventType.SKILL_EXECUTED, {
                            "skill": selected_skill.name,
                            "display_name": selected_skill.display_name,
                            "has_data": skill_data is not None,
                        }, component="CopilotEngine", thread_id=thread_id)
                    except Exception:
                        pass
                except asyncio.TimeoutError:
                    tracer.end(success=False, error="timeout")
                    agent_log.error(f"[engine:skill_timeout] skill={selected_skill.name} exceeded 60s")
                    yield CopilotEvent(type=EventType.TOOL_CALL_END, metadata={"skill": selected_skill.name, "error": "timeout"})
                    yield text_delta_event(f"\n\n抱歉，{selected_skill.display_name} 执行超时，请稍后重试。")
                except Exception as e:
                    tracer.end(success=False, error=str(e))
                    agent_log.error(f"[engine:skill_error] skill={selected_skill.name} error={e}")
                    yield CopilotEvent(type=EventType.TOOL_CALL_END, metadata={"skill": selected_skill.name, "error": str(e)})

                # 6. LLM 综合回答（§3.2 abstain 短路：拒答时 skill 自身已输出文案，不再调 LLM）
                if skill_data and not skill_data.get("abstain"):
                    yield decision_step_event("synthesize", "LLM 综合分析中")
                    async for event in self._synthesize_answer(question, context, selected_skill, skill_data):
                        yield event
                        if event.type == EventType.TEXT_DELTA and event.content:
                            _output_parts.append(str(event.content))
                elif skill_data and skill_data.get("abstain"):
                    yield decision_step_event("abstain", f"知识库拒答: {skill_data.get('reason', 'unknown')}")

            # 保存助手回答到 Redis
            # (完整内容由持久化层在 SSE 结束后批量写入 DB)

            # 6.5 输出 PII 检测 — 在 run_end 之前检查输出是否含敏感信息
            try:
                _full_output = "".join(_output_parts)
                if _full_output:
                    from backend.governance.guardrails import input_guard as _ig
                    _, pii_hits = _ig._handle_pii(_full_output)
                    if pii_hits:
                        yield security_check_event(
                            check_type="output_pii_scan",
                            passed=True,
                            detail=f"输出中检测到 {len(pii_hits)} 处 PII 信息",
                            hits=[{"rule": h.rule, "severity": h.severity, "message": h.message} for h in pii_hits],
                        )
                        yield decision_step_event("output_pii", f"输出 PII 检测: {len(pii_hits)} 处已标记")
                        try:
                            telemetry.emit(TelemetryEventType.PII_DETECTED, {
                                "direction": "output",
                                "count": len(pii_hits),
                                "rules": [h.rule for h in pii_hits],
                            }, component="OutputPIIScanner", thread_id=thread_id)
                        except Exception:
                            pass
            except Exception as _pii_err:
                agent_log.debug(f"[engine:output_pii] scan skipped: {_pii_err}")

            elapsed_ms = self._elapsed_ms(start_time)
            agent_log.info(f"[engine:done] elapsed={elapsed_ms}ms thread={thread_id}")

            try:
                telemetry.emit(TelemetryEventType.RUN_COMPLETED, {
                    "mode": mode, "skill": selected_skill.name if selected_skill else "general_chat",
                    "latency_ms": elapsed_ms, "tokens": _acc_tokens,
                }, component="CopilotEngine", thread_id=thread_id)
            except Exception:
                pass

            yield run_end_event(thread_id, elapsed_ms)

            # 写 runs 记录（fire-and-forget，异步线程避免阻塞事件循环）
            _out_text = "".join(_output_parts)
            asyncio.ensure_future(asyncio.to_thread(
                self._write_copilot_run,
                user_id=user_id, mode=mode, thread_id=thread_id,
                skill_name=selected_skill.name if selected_skill else "general_chat",
                input_summary=question[:500],
                output_summary=_out_text[:500],
                status="completed", latency_ms=elapsed_ms,
                total_tokens=_acc_tokens, total_cost=_acc_cost,
            ))

        except (asyncio.CancelledError, GeneratorExit):
            # 客户端断开或任务被取消。此时 SSE 通道已无法再 yield 给客户端，
            # 必须 re-raise 以保持 asyncio 取消语义，否则上层 await 会认为任务正常结束，
            # 导致 Trace/metrics/task-state 不一致。
            agent_log.warning(f"[engine:cancelled] thread={thread_id}")
            raise
        except Exception as e:
            error_msg = f"处理失败: {type(e).__name__}"
            agent_log.error(f"[engine:error] {e}\n{traceback.format_exc()}")

            try:
                telemetry.emit(TelemetryEventType.RUN_FAILED, {
                    "mode": mode, "error": str(e)[:200],
                    "latency_ms": self._elapsed_ms(start_time),
                }, component="CopilotEngine", thread_id=thread_id)
                telemetry.emit(TelemetryEventType.ERROR_CLASSIFIED, {
                    "error_type": type(e).__name__,
                    "error_message": str(e)[:200],
                    "severity": "high",
                }, component="CopilotEngine", thread_id=thread_id)
            except Exception:
                pass

            yield run_error_event(error_msg)
            elapsed_ms = self._elapsed_ms(start_time)
            yield run_end_event(thread_id, elapsed_ms)

            asyncio.ensure_future(asyncio.to_thread(
                self._write_copilot_run,
                user_id=user_id, mode=mode, thread_id=thread_id,
                skill_name="error",
                input_summary=question[:500],
                output_summary="",
                status="failed", latency_ms=elapsed_ms,
                error_message=str(e)[:500],
                total_tokens=_acc_tokens, total_cost=_acc_cost,
            ))

    def _write_copilot_run(
        self, user_id: str, mode: str, thread_id: str,
        skill_name: str, input_summary: str, output_summary: str,
        status: str, latency_ms: int, error_message: str = "",
        total_tokens: int = 0, total_cost: float = 0.0,
    ) -> None:
        """Fire-and-forget: 将 Copilot 对话写入 runs 表"""
        try:
            from backend.database import SessionLocal
            db = SessionLocal()
            try:
                run_id = str(uuid.uuid4())
                wf_name = f"copilot_{mode}"
                db.execute(sqlalchemy.text("""
                    INSERT INTO runs
                        (run_id, thread_id, request_id, entrypoint, workflow_name,
                         status, triggered_by, input_summary, output_summary,
                         total_tokens, total_cost,
                         error_message, started_at, ended_at, latency_ms)
                    VALUES
                        (:rid, :tid, :rid, :ep, :wf,
                         :st, :user, :inp, :out,
                         :tokens, :cost,
                         :err, NOW(), NOW(), :lat)
                """), {
                    "rid": run_id, "tid": thread_id,
                    "ep": f"copilot/{mode}", "wf": wf_name,
                    "st": status, "user": user_id,
                    "inp": (input_summary or "")[:500],
                    "out": (output_summary or "")[:500],
                    "err": (error_message or "")[:500],
                    "tokens": total_tokens, "cost": total_cost,
                    "lat": latency_ms,
                })
                # 写 step
                db.execute(sqlalchemy.text("""
                    INSERT INTO run_steps
                        (step_id, run_id, step_type, step_name, agent_name,
                         status, input_summary, output_summary, error_message,
                         started_at, ended_at)
                    VALUES
                        (:sid, :rid, 'agent_call', :sn, :an,
                         :st, :inp, :out, :err, NOW(), NOW())
                """), {
                    "sid": str(uuid.uuid4()), "rid": run_id,
                    "sn": skill_name, "an": skill_name,
                    "st": status,
                    "inp": (input_summary or "")[:200],
                    "out": (output_summary or "")[:200],
                    "err": (error_message or "")[:500],
                })
                db.commit()
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"[copilot:db] write run failed (non-fatal): {e}")

    # ── R6-1: Pipeline Stage 版本的 run（与原 run() 行为等价）──
    async def run_v2(
        self,
        question: str,
        mode: str,
        user_id: str,
        user_role: str,
        thread_id: str,
        page_context: Optional[Dict[str, Any]] = None,
        source: str = "web",
    ) -> AsyncGenerator[CopilotEvent, None]:
        """Pipeline 版本的主入口。

        与原 run() 事件序列等价，但内部用 Pipeline + 9 个 Stage 编排:
          InputGuardStage → ContextStage → TokenGovernorStage → MemoryRecallStage
          → RouterStage → DedupStage → SkillExecStage → OutputPIIStage
          ⇢ PersistStage (finalize, 无条件执行)

        通过 settings.COPILOT_PIPELINE_V2 feature flag 决定是否采用此版本；
        外层 router 显式根据 flag 选 run / run_v2，Engine 内部不做路由。
        """
        from backend.copilot.pipeline import Pipeline, RunState
        from backend.copilot.pipeline.stages import (
            build_default_stages,
            build_finalize_stages,
        )

        state = RunState(
            question=question or "",
            mode=mode,
            user_id=user_id,
            user_role=user_role,
            thread_id=thread_id,
            page_context=page_context or {},
            source=source,
            run_id=str(uuid.uuid4()),
        )

        pipeline = Pipeline(
            stages=build_default_stages(self),
            finalize_stages=build_finalize_stages(self),
        )

        agent_log = get_agent_logger(mode)
        agent_log.info(
            f"[engine:run_v2] question='{question[:80]}' mode={mode} "
            f"user={user_id} role={user_role} source={source}"
        )

        try:
            async for event in pipeline.run(state):
                yield event
        except (asyncio.CancelledError, GeneratorExit):
            agent_log.warning(f"[engine:run_v2:cancelled] thread={thread_id}")
            raise

    async def run_single_skill(
        self,
        skill_name: str,
        question: str,
        mode: str,
        user_role: str,
        user_id: str = "system",
        source: str = "scheduler",
    ) -> Dict[str, Any]:
        """直接执行单个 Skill（供巡检调度器使用）"""
        skill = self._registry.get(skill_name)
        if skill is None:
            return {"error": f"Skill '{skill_name}' not found"}

        context = SkillContext(
            user_id=user_id,
            user_role=user_role,
            mode=mode,
            thread_id=f"patrol_{skill_name}",
            source=source,
        )

        result = {}
        try:
            async for event in skill.execute(question, context):
                if event.type == EventType.TOOL_RESULT and event.data:
                    result = event.data
        except Exception as e:
            result = {"error": str(e)}

        return result

    # ── LLM 路由 ──

    async def _route_to_skill(
        self,
        question: str,
        context: SkillContext,
        available_skills: List[BaseCopilotSkill],
    ) -> tuple[Optional[BaseCopilotSkill], Dict[str, Any], int]:
        """使用 LLM Function Calling 将问题路由到合适的 Skill
        
        Returns: (skill, tool_args, tokens_used)
        """
        if not available_skills:
            return None, {}, 0

        tools = [s.to_function_schema() for s in available_skills]

        try:
            import openai
            from backend.core.model_selector import model_selector, ModelRole

            routing_spec = model_selector.get_spec(ModelRole.ROUTING)
            client = openai.AsyncOpenAI(
                api_key=routing_spec.api_key or settings.LLM_API_KEY,
                base_url=routing_spec.base_url or settings.LLM_BASE_URL,
                timeout=float(routing_spec.timeout),
            )

            messages = [
                {"role": "system", "content": context.system_prompt},
            ]
            # 注入最近历史
            for msg in context.thread_history[-6:]:
                messages.append(msg)
            messages.append({"role": "user", "content": question})

            telemetry.emit(TelemetryEventType.MODEL_REQUESTED, {
                "model": routing_spec.model_name, "role": "routing",
                "messages_count": len(messages),
            }, component="CopilotEngine", thread_id=context.thread_id)

            t0 = time.time()
            async with asyncio.timeout(routing_spec.timeout):
                response = await client.chat.completions.create(
                    model=routing_spec.model_name,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    temperature=routing_spec.temperature,
                )

            choice = response.choices[0]
            route_tokens = 0
            _tokens_in = 0
            _tokens_out = 0
            if hasattr(response, 'usage') and response.usage:
                route_tokens = getattr(response.usage, 'total_tokens', 0) or 0
                _tokens_in = getattr(response.usage, 'prompt_tokens', 0) or 0
                _tokens_out = getattr(response.usage, 'completion_tokens', 0) or 0

            telemetry.emit(TelemetryEventType.MODEL_COMPLETED, {
                "model": routing_spec.model_name, "role": "routing",
                "tokens_in": _tokens_in, "tokens_out": _tokens_out,
                "latency_ms": int((time.time() - t0) * 1000),
            }, component="CopilotEngine", thread_id=context.thread_id)

            if choice.message.tool_calls:
                tool_call = choice.message.tool_calls[0]
                fn_name = tool_call.function.name
                fn_args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}

                skill = self._registry.get(fn_name)
                if skill:
                    # 如果 LLM 选了 kb_rag_skill 但关键词匹配到领域专用 skill，优先用领域 skill
                    if fn_name == "kb_rag_skill":
                        kw_override = self._keyword_fallback(question, available_skills)
                        if kw_override and kw_override.name != "kb_rag_skill":
                            logger.info(
                                f"[engine:route] LLM 选 kb_rag_skill 但关键词匹配到 {kw_override.name}，覆盖"
                            )
                            return kw_override, {}, route_tokens
                    logger.info(f"[engine:route] LLM 路由到 skill={fn_name} args={fn_args} tokens={route_tokens}")
                    return skill, fn_args, route_tokens
                else:
                    logger.warning(f"[engine:route] LLM 返回未注册 skill={fn_name}，尝试关键词回退")

            # LLM 没有选择任何 tool → 先尝试关键词匹配再降级到通用对话
            kw_skill = self._keyword_fallback(question, available_skills)
            if kw_skill:
                logger.info(f"[engine:route] LLM 未选 tool，关键词匹配到 {kw_skill.name}")
                return kw_skill, {}, route_tokens
            return None, {}, route_tokens

        except Exception as e:
            logger.warning(f"[engine:route] LLM 路由失败，回退到关键词匹配: {e}")
            return self._keyword_fallback(question, available_skills), {}, 0

    def _keyword_fallback(
        self, question: str, skills: List[BaseCopilotSkill]
    ) -> Optional[BaseCopilotSkill]:
        """关键词匹配回退（LLM 不可用时）"""
        keyword_map = {
            "inventory_skill":       ["库存", "补货", "安全库存", "EOQ", "SKU", "缺货"],
            "forecast_skill":        ["预测", "销售预测", "趋势", "销量", "forecast"],
            "sentiment_skill":       ["舆情", "评价", "负面", "情感", "口碑"],
            "customer_intel_skill":  ["客户", "流失", "RFM", "CLV", "分群", "高价值"],
            "fraud_skill":           ["欺诈", "风险", "风控", "异常交易", "风控态势"],
            "association_skill":     ["关联", "搭配", "购物篮", "推荐"],
            "kb_rag_skill":          ["知识库", "搜索", "查询知识", "报告", "报表", "流程", "步骤", "工作流"],
            "trace_skill":           ["trace", "跟踪", "run", "失败", "延迟"],
            "system_skill":          ["系统", "健康", "状态", "服务"],
        }

        q_lower = question.lower()
        for skill_name, keywords in keyword_map.items():
            for kw in keywords:
                if kw in q_lower:
                    for s in skills:
                        if s.name == skill_name:
                            logger.info(f"[engine:keyword_fallback] matched {skill_name}")
                            return s
        return None

    # ── 通用对话 ──

    async def _general_chat(
        self, question: str, context: SkillContext
    ) -> AsyncGenerator[CopilotEvent, None]:
        """无 Skill 匹配时的通用 LLM 对话"""
        try:
            import openai
            from backend.core.model_selector import model_selector, ModelRole

            primary_spec = model_selector.get_spec(ModelRole.PRIMARY)
            client = openai.AsyncOpenAI(
                api_key=primary_spec.api_key or settings.LLM_API_KEY,
                base_url=primary_spec.base_url or settings.LLM_BASE_URL,
                timeout=float(primary_spec.timeout),
            )

            messages = [
                {"role": "system", "content": context.system_prompt},
            ]
            for msg in context.thread_history[-6:]:
                messages.append(msg)
            messages.append({"role": "user", "content": question})

            telemetry.emit(TelemetryEventType.MODEL_REQUESTED, {
                "model": primary_spec.model_name, "role": "primary",
                "messages_count": len(messages),
            }, component="CopilotEngine", thread_id=context.thread_id)

            t0 = time.time()
            _stream_tokens_in = 0
            _stream_tokens_out = 0

            async with asyncio.timeout(primary_spec.timeout):
                stream = await client.chat.completions.create(
                    model=primary_spec.model_name,
                    messages=messages,
                    stream=True,
                    stream_options={"include_usage": True},
                    temperature=primary_spec.temperature or 0.7,
                )

                async for chunk in stream:
                    if chunk.choices:
                        delta = chunk.choices[0].delta
                        if delta.content:
                            yield text_delta_event(delta.content)
                    if hasattr(chunk, 'usage') and chunk.usage:
                        _stream_tokens_in = getattr(chunk.usage, 'prompt_tokens', 0) or 0
                        _stream_tokens_out = getattr(chunk.usage, 'completion_tokens', 0) or 0

            telemetry.emit(TelemetryEventType.MODEL_COMPLETED, {
                "model": primary_spec.model_name, "role": "primary",
                "tokens_in": _stream_tokens_in, "tokens_out": _stream_tokens_out,
                "latency_ms": int((time.time() - t0) * 1000),
            }, component="CopilotEngine", thread_id=context.thread_id)

        except asyncio.TimeoutError:
            logger.error(f"[engine:general_chat] LLM 调用超时 ({primary_spec.timeout}s)")
            yield text_delta_event("抱歉，AI 响应超时，请稍后重试。")
        except Exception as e:
            logger.error(f"[engine:general_chat] LLM 调用失败: {e}")
            yield text_delta_event(f"抱歉，AI 服务暂时不可用。错误: {type(e).__name__}")

    # ── LLM 综合回答 ──

    @staticmethod
    def _detect_instruction_mode(question: str) -> str:
        """检测用户的指令意图，返回额外的约束提示"""
        q = question.lower()
        if any(k in q for k in ["列出", "列举", "清单", "哪些", "前5", "前10", "top"]):
            return "用户要求列出具体条目，你必须以列表或表格形式逐条列出，不能只给概要。"
        if any(k in q for k in ["只告诉我", "只要", "直接说", "简短", "一句话", "数量是多少"]):
            return "用户要求简短直答，先用一句话直接回答核心数字，然后可以补充少量建议。"
        if any(k in q for k in ["建议", "方案", "怎么办", "应对", "措施"]):
            return "用户要求可执行建议，每条建议必须包含：具体对象、具体数字、具体动作、优先级。"
        if any(k in q for k in ["最关键", "最重要", "最紧急", "核心发现"]):
            return "用户要求提炼重点，按重要性排序给出 Top 3 发现，每条带具体数据支撑。"
        return ""

    @staticmethod
    def _render_synthesize_prompt(
        context_system_prompt: str,
        skill_hint: str,
        instruction_hint: str,
        user_id: Optional[str] = None,
    ) -> str:
        """组装 _synthesize_answer 的 system prompt。

        R6-4 优先策略:
          1. 若 settings.PROMPT_STORE_ENABLED 且 prompt_store 有 "agent.synthesize_base"
             → 用 prompt_store.render(...) 得到结果（发 PROMPT_USED 遥测, 支持灰度）
          2. 否则 fallback 到原 hardcoded 拼接（行为与 R6 之前完全一致）

        Args:
            context_system_prompt: 来自 ContextManager 的 system_prompt 片段
            skill_hint:            per-skill 的 summarization_hint（可能为空）
            instruction_hint:      按用户问题关键词推断出的指令约束（可能为空）
            user_id:               灰度分桶用

        Returns:
            最终要放入 messages[0]['content'] 的字符串
        """
        # ── Path A: PromptStore（灰度 / 版本化） ──
        if settings.PROMPT_STORE_ENABLED:
            try:
                from backend.core.prompt_store import prompt_store
                if prompt_store.get("agent.synthesize_base") is not None:
                    # YAML v1 使用 {skill_hint_block} / {instruction_hint_block}
                    # 由调用方负责包装空串或 "\n{text}\n"
                    skill_block = f"\n{skill_hint}\n" if skill_hint else ""
                    instr_block = (
                        f"\n⚠️ 指令约束：{instruction_hint}\n" if instruction_hint else ""
                    )
                    return prompt_store.render(
                        key="agent.synthesize_base",
                        variables={
                            "system_prompt": context_system_prompt,
                            "skill_hint_block": skill_block,
                            "instruction_hint_block": instr_block,
                        },
                        user_id=user_id,
                    )
            except Exception as e:
                logger.debug(
                    f"[engine:synthesize] prompt_store render failed, "
                    f"fallback to hardcoded: {e}"
                )

        # ── Path B: hardcoded fallback（行为与 R6 之前一致） ──
        prompt_parts = [
            f"{context_system_prompt}\n\n",
            "你刚刚调用了分析工具获得了数据结果。请基于数据给出专业的分析总结。\n",
            "通用要求：\n",
            "1. 必须引用工具返回的关键数值（如数量、比例、评分、金额等），用 **加粗** 标注\n",
            "2. 如果用户要求列出具体条目（如SKU、交易、客户），必须逐条列出，不能省略\n",
            "3. 给出可操作的具体建议（包含具体数字、优先级、执行步骤），不能只说'建议关注'\n",
            "4. 使用 Markdown 格式，结构清晰\n",
            "5. 必须使用中文回答\n",
            "6. 不要编造数据中没有的内容\n",
        ]
        if skill_hint:
            prompt_parts.append(f"\n{skill_hint}\n")
        if instruction_hint:
            prompt_parts.append(f"\n⚠️ 指令约束：{instruction_hint}\n")
        return "".join(prompt_parts)

    async def _synthesize_answer(
        self,
        question: str,
        context: SkillContext,
        skill: "BaseCopilotSkill",
        skill_data: Dict[str, Any],
    ) -> AsyncGenerator[CopilotEvent, None]:
        """Skill 返回结构化数据后，LLM 生成自然语言总结"""
        try:
            import openai
            from backend.core.model_selector import model_selector, ModelRole
            from backend.core.token_counter import token_counter

            primary_spec = model_selector.get_spec(ModelRole.PRIMARY)
            client = openai.AsyncOpenAI(
                api_key=primary_spec.api_key or settings.LLM_API_KEY,
                base_url=primary_spec.base_url or settings.LLM_BASE_URL,
                timeout=float(primary_spec.timeout),
            )

            # §3.1 L1 判定：是否启用 Grounding 强制引用
            require_grounding = (
                bool(skill_data.get("require_grounding"))
                and settings.KB_GROUNDING_ENFORCE_CITATIONS
            )
            citations = skill_data.get("citations") or []
            allowed_cids = {c["cid"] for c in citations if c.get("cid")}

            if require_grounding and citations:
                # 用结构化 <chunks> 块替代原始 JSON dump，LLM 更容易对齐引用
                from backend.copilot.grounding_filter import build_citation_block
                data_str = build_citation_block(citations)
            else:
                # 截断过大的数据（保留核心字段，精简列表）
                data_str = json.dumps(skill_data, ensure_ascii=False, default=str)
                data_str = token_counter.truncate_to_budget(
                    data_str, budget=4000, strategy="head_tail",
                )

            # 构建 per-skill 摘要约束
            skill_hint = getattr(skill, "summarization_hint", "") or ""
            instruction_hint = self._detect_instruction_mode(question)

            # R6-4: 优先走 PromptStore（当 flag 开启且已注册对应 key）
            system_content = self._render_synthesize_prompt(
                context_system_prompt=context.system_prompt,
                skill_hint=skill_hint,
                instruction_hint=instruction_hint,
                user_id=getattr(context, "user_id", None),
            )
            if require_grounding:
                # §3.1 L1：追加引用规则（prompt 级强制）
                from backend.copilot.grounding_filter import DEFAULT_CITATION_RULES
                system_content += DEFAULT_CITATION_RULES

            messages = [
                {"role": "system", "content": system_content},
                {
                    "role": "user",
                    "content": f"用户问题: {question}\n\n工具 {skill.name} 返回的数据:\n{data_str}",
                },
            ]

            telemetry.emit(TelemetryEventType.MODEL_REQUESTED, {
                "model": primary_spec.model_name, "role": "primary",
                "skill": skill.name,
            }, component="CopilotEngine", thread_id=context.thread_id)

            t0 = time.time()
            _stream_tokens_in = 0
            _stream_tokens_out = 0
            # §3.1 L1：require_grounding 时累积 LLM 输出，流结束后跑 filter_ungrounded
            accumulated: list = []

            async with asyncio.timeout(primary_spec.timeout):
                stream = await client.chat.completions.create(
                    model=primary_spec.model_name,
                    messages=messages,
                    stream=True,
                    stream_options={"include_usage": True},
                    temperature=primary_spec.temperature or 0.5,
                )

                async for chunk in stream:
                    if chunk.choices:
                        delta = chunk.choices[0].delta
                        if delta.content:
                            if require_grounding:
                                accumulated.append(delta.content)
                            yield text_delta_event(delta.content)
                    if hasattr(chunk, 'usage') and chunk.usage:
                        _stream_tokens_in = getattr(chunk.usage, 'prompt_tokens', 0) or 0
                        _stream_tokens_out = getattr(chunk.usage, 'completion_tokens', 0) or 0

            telemetry.emit(TelemetryEventType.MODEL_COMPLETED, {
                "model": primary_spec.model_name, "role": "primary",
                "skill": skill.name,
                "tokens_in": _stream_tokens_in, "tokens_out": _stream_tokens_out,
                "latency_ms": int((time.time() - t0) * 1000),
            }, component="CopilotEngine", thread_id=context.thread_id)

            # §3.1 L1 后验校验：流式结束后对 LLM 全文做 filter_ungrounded
            if require_grounding and accumulated:
                try:
                    from backend.copilot.grounding_filter import filter_ungrounded
                    full_text = "".join(accumulated)
                    gresult = filter_ungrounded(full_text, allowed_cids, strict=True)
                    min_ratio = float(getattr(settings, "KB_MIN_GROUNDED_RATIO", 0.8))
                    passed = gresult["grounded_ratio"] >= min_ratio

                    yield CopilotEvent(
                        type=EventType.ARTIFACT_START,
                        artifact_type="grounding_check",
                        metadata={"component": "GroundingMeta", "passed": passed},
                    )
                    yield CopilotEvent(
                        type=EventType.ARTIFACT_DELTA,
                        content={
                            "grounded_ratio": gresult["grounded_ratio"],
                            "total_sentences": gresult["total_sentences"],
                            "kept": len(gresult["kept_sentences"]),
                            "dropped": len(gresult["dropped_sentences"]),
                            "citations_used": gresult["citations_used"],
                            "allowed_cids": sorted(allowed_cids),
                            "dropped_preview": [
                                {"text": (d.get("text") or "")[:120], "reason": d.get("reason")}
                                for d in gresult["dropped_sentences"][:5]
                            ],
                            "min_required": min_ratio,
                            "passed": passed,
                        },
                    )
                    yield CopilotEvent(type=EventType.ARTIFACT_END)

                    if (not passed) and getattr(
                        settings, "KB_GROUNDING_WARN_ON_LOW_RATIO", True
                    ):
                        warn_msg = getattr(
                            settings, "KB_GROUNDING_WARN_MSG",
                            "\n\n> ⚠️ 上述答复中部分内容未在知识库中找到直接依据。\n",
                        )
                        yield text_delta_event(warn_msg)
                except Exception as ge:
                    logger.warning(f"[engine:grounding_check] failed: {ge}")

        except asyncio.TimeoutError:
            logger.warning("[engine:synthesize] LLM 综合回答超时")
            yield text_delta_event("\n\n*（AI 总结超时，请参考上方数据。）*")
        except Exception as e:
            logger.warning(f"[engine:synthesize] LLM 综合回答失败: {e}")
            yield text_delta_event("\n\n*（AI 总结暂时不可用，请参考上方数据。）*")

    async def save_assistant_reply(self, thread_id: str, content: str) -> None:
        """保存助手回复到 Redis，供后续轮次上下文使用"""
        await self._context_mgr.save_to_thread_history(thread_id, "assistant", content)

    @staticmethod
    def _elapsed_ms(start: float) -> int:
        return int((time.time() - start) * 1000)
