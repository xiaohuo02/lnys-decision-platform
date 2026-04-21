# -*- coding: utf-8 -*-
"""backend/governance/policy_center/policy_adjuster.py — Verdict → Policy 变更建议 (R6-5)

职责:
  订阅 PeriodicEvaluator 产出的 verdict, 按预定规则把异常指标映射为 PolicyChange:
    - shadow mode: 只记录 + 发 POLICY_SUGGESTED 遥测, 不修改任何 global state
    - enforce mode: 按每类 policy 的 whitelist 真正应用变更, 发 POLICY_APPLIED
  每个 PolicyChange 带 TTL, 到期自动回滚 (发 POLICY_ROLLED_BACK)。

设计原则:
  - 独立于 policy_engine.py（已有模块）, 不干扰其现有逻辑
  - enforce mode 默认关闭 (settings.POLICY_ENFORCE_MODE="shadow")
  - 每类 policy 的 enforce 实现都需要单独评估（从 shadow→enforce 是手动动作）
  - 变更带 TTL, 防止一次抖动造成永久降级

支持的 recommendation → PolicyChange 映射 (MVP):
  "model_downgrade:<model>"    → policy_key="model.default_name", new_value="<turbo 版>"
  "relax_pii_rules"            → policy_key="input_guard.pii_threshold", 调低阈值
  "enhance_keyword_fallback"   → policy_key="router.fallback_keywords_enabled", True
  "enhance_router_prompt"      → policy_key="router.prompt_version", 切更强版本
  "extend_skill_timeout"       → policy_key="skill.default_timeout_seconds", 加大
"""
from __future__ import annotations

import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from loguru import logger

from backend.governance.eval_center.periodic_evaluator import EvalVerdict


DEFAULT_TTL_SECONDS = 6 * 3600   # 策略变更默认 TTL 6 小时


@dataclass
class PolicyChange:
    """一次策略建议或变更记录。"""
    change_id: str
    suggested_at: float
    expires_at: float
    policy_key: str
    new_value: Any
    old_value: Any = None
    source_verdict: Dict[str, Any] = field(default_factory=dict)
    mode: str = "shadow"            # shadow / enforce
    applied: bool = False
    applied_at: Optional[float] = None
    rolled_back: bool = False
    rolled_back_at: Optional[float] = None
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "change_id": self.change_id,
            "suggested_at": self.suggested_at,
            "expires_at": self.expires_at,
            "policy_key": self.policy_key,
            "new_value": self.new_value,
            "old_value": self.old_value,
            "source_verdict": self.source_verdict,
            "mode": self.mode,
            "applied": self.applied,
            "applied_at": self.applied_at,
            "rolled_back": self.rolled_back,
            "rolled_back_at": self.rolled_back_at,
            "reason": self.reason,
        }


# ── recommendation → PolicyChange 映射 ──────────────────────

# 每个 recommendation 的实现方式:
#   (policy_key, new_value_fn(verdict) -> Any, ttl_seconds, reason_template)
_RECOMMENDATION_HANDLERS = {
    "model_downgrade": lambda verdict: (
        "model.default_name",
        _turbo_of(verdict.subject),
        DEFAULT_TTL_SECONDS,
        f"model={verdict.subject} p95 latency {verdict.value:.0f}ms > "
        f"{verdict.threshold_critical:.0f}ms",
    ),
    "relax_pii_rules": lambda verdict: (
        "input_guard.pii_threshold",
        "lenient",
        DEFAULT_TTL_SECONDS,
        f"pii block rate {verdict.value:.1%} exceeds warning",
    ),
    "enhance_keyword_fallback": lambda verdict: (
        "router.fallback_keywords_enabled",
        True,
        DEFAULT_TTL_SECONDS,
        f"skill hit rate {verdict.value:.1%} below warning",
    ),
    "enhance_router_prompt": lambda verdict: (
        "router.prompt_version",
        "v2-robust",
        DEFAULT_TTL_SECONDS,
        f"router failure rate {verdict.value:.1%} exceeds warning",
    ),
    "extend_skill_timeout": lambda verdict: (
        "skill.default_timeout_seconds",
        90,
        DEFAULT_TTL_SECONDS // 2,
        f"tool timeout rate {verdict.value:.1%} exceeds warning",
    ),
}


def _turbo_of(model_name: str) -> str:
    """粗粒度映射: 把某模型降级到 turbo 变体。"""
    mn = (model_name or "").lower()
    if "plus" in mn or "max" in mn:
        return mn.replace("plus", "turbo").replace("max", "turbo")
    if "gpt-4" in mn:
        return "gpt-4-turbo"
    return "qwen-turbo"


# ── PolicyAdjuster ──────────────────────────────────────────

class PolicyAdjuster:
    """verdict → policy change 建议与应用。

    Args:
        enforce_mode: "shadow" 或 "enforce"
        enforce_whitelist: enforce 模式下，仅对 whitelist 中的 policy_key 真正应用
                           （其它 key 仍停留在 shadow）
    """

    MAX_CHANGES = 300

    def __init__(
        self,
        enforce_mode: str = "shadow",
        enforce_whitelist: Optional[List[str]] = None,
        db_session_factory: Any = None,
    ):
        """
        Args:
            enforce_mode:       shadow / enforce
            enforce_whitelist:  enforce 模式下允许真正落地的 policy_key 集合
            db_session_factory: 可选同步 sessionmaker, best-effort 写 policy_change_log
            apply_handlers:     后续可通过 register_apply_handler 注册
        """
        if enforce_mode not in ("shadow", "enforce"):
            raise ValueError(f"invalid enforce_mode: {enforce_mode}")
        self._mode = enforce_mode
        self._whitelist = set(enforce_whitelist or [])
        self._changes: deque = deque(maxlen=self.MAX_CHANGES)
        self._db_factory = db_session_factory
        # policy_key → callable(change) 真正落地某类变更的注册表（默认空 = dry-run）
        self._apply_handlers: Dict[str, Any] = {}

    def configure(self, db_session_factory: Any = None) -> None:
        """运行时注入 db_session_factory（lifespan 启动阶段调用）。"""
        self._db_factory = db_session_factory

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> None:
        """运行时切换 shadow / enforce（管理员操作）。"""
        if mode not in ("shadow", "enforce"):
            raise ValueError(f"invalid mode: {mode}")
        self._mode = mode

    def set_whitelist(self, whitelist: List[str]) -> None:
        self._whitelist = set(whitelist)

    @property
    def changes(self) -> List[PolicyChange]:
        return list(self._changes)

    def recent(self, limit: int = 50, applied_only: bool = False) -> List[Dict[str, Any]]:
        items = list(self._changes)
        if applied_only:
            items = [c for c in items if c.applied]
        return [c.to_dict() for c in items[-limit:]]

    def clear(self) -> None:
        """清空变更缓冲（测试用）。"""
        self._changes.clear()

    # ── 核心入口 ──────────────────────────────────────────

    def register_apply_handler(self, policy_key: str, handler) -> None:
        """为某个 policy_key 注册真实的"应用"函数。

        默认情况下所有 enforce 分支都是 dry-run（只记录 applied=True）；
        业务方可在 lifespan 内显式注册 handler 让变更真正生效。

        handler 签名:
            def handler(change: PolicyChange) -> None
                # 读 change.new_value, 修改全局 state（ModelSelector 等）
                # 异常应由 handler 自己吞掉, Adjuster 不会 catch

        Args:
            policy_key: 如 "model.default_name"
            handler:    回调函数
        """
        if not callable(handler):
            raise ValueError("handler must be callable")
        self._apply_handlers[policy_key] = handler

    def unregister_apply_handler(self, policy_key: str) -> None:
        self._apply_handlers.pop(policy_key, None)

    def process(self, verdicts: List[EvalVerdict]) -> List[PolicyChange]:
        """逐条处理 verdict，产出策略变更建议/应用记录。"""
        now = time.time()
        new_changes: List[PolicyChange] = []

        for v in verdicts:
            if v.status in ("normal", "insufficient"):
                continue
            if not v.recommendation:
                continue

            change = self._plan_change(v, now)
            if change is None:
                continue

            # 判定本次走 shadow 还是真 enforce
            effective_mode = self._mode
            if effective_mode == "enforce" and self._whitelist:
                if change.policy_key not in self._whitelist:
                    effective_mode = "shadow"
            change.mode = effective_mode

            if effective_mode == "enforce":
                self._apply(change)

            self._emit(change, "suggested")
            if change.applied:
                self._emit(change, "applied")

            self._changes.append(change)
            new_changes.append(change)

        # 处理过期 rollback
        self._rollback_expired(now)

        # R6-5 持久化: best-effort 批量写 policy_change_log
        if new_changes and self._db_factory is not None:
            self._persist_changes(new_changes)

        return new_changes

    def _persist_changes(self, changes: List[PolicyChange]) -> None:
        """best-effort 写 policy_change_log。失败只记日志不抛异常。"""
        try:
            import json as _json
            import sqlalchemy
            db = self._db_factory()
        except Exception as e:
            logger.debug(f"[PolicyAdjuster] open db session failed: {e}")
            return

        try:
            for c in changes:
                db.execute(sqlalchemy.text(
                    "INSERT INTO policy_change_log "
                    "(change_id, policy_key, new_value, old_value, source_verdict, "
                    " mode, applied, applied_at, rolled_back, rolled_back_at, "
                    " reason, suggested_at, expires_at) "
                    "VALUES "
                    "(:cid, :pk, :nv, :ov, :sv, "
                    " :mode, :ap, IF(:at IS NULL, NULL, FROM_UNIXTIME(:at)), "
                    " :rb, IF(:rt IS NULL, NULL, FROM_UNIXTIME(:rt)), "
                    " :rs, FROM_UNIXTIME(:sa), FROM_UNIXTIME(:ea))"
                ), {
                    "cid": c.change_id,
                    "pk": c.policy_key,
                    "nv": _json.dumps(c.new_value, ensure_ascii=False, default=str),
                    "ov": _json.dumps(c.old_value, ensure_ascii=False, default=str),
                    "sv": _json.dumps(c.source_verdict, ensure_ascii=False, default=str),
                    "mode": c.mode,
                    "ap": 1 if c.applied else 0,
                    "at": c.applied_at,
                    "rb": 1 if c.rolled_back else 0,
                    "rt": c.rolled_back_at,
                    "rs": c.reason,
                    "sa": c.suggested_at,
                    "ea": c.expires_at,
                })
            db.commit()
        except Exception as e:
            logger.warning(f"[PolicyAdjuster] db persist failed (non-fatal): {e}")
            try:
                db.rollback()
            except Exception:
                pass
        finally:
            try:
                db.close()
            except Exception:
                pass

    # ── 变更规划 ──────────────────────────────────────────

    def _plan_change(self, verdict: EvalVerdict, now: float) -> Optional[PolicyChange]:
        rec = verdict.recommendation
        # recommendation 形如 "model_downgrade:qwen-plus"
        key = rec.split(":", 1)[0]
        handler = _RECOMMENDATION_HANDLERS.get(key)
        if handler is None:
            logger.debug(f"[PolicyAdjuster] no handler for recommendation: {rec}")
            return None

        try:
            policy_key, new_value, ttl, reason = handler(verdict)
        except Exception as e:
            logger.warning(f"[PolicyAdjuster] handler for '{rec}' failed: {e}")
            return None

        return PolicyChange(
            change_id=str(uuid.uuid4()),
            suggested_at=now,
            expires_at=now + ttl,
            policy_key=policy_key,
            new_value=new_value,
            source_verdict=verdict.to_dict(),
            reason=reason,
        )

    # ── 应用 / 回滚 ────────────────────────────────────────

    def _apply(self, change: PolicyChange) -> None:
        """真正应用一次 policy 变更（enforce 模式）。

        逻辑:
          - 先 snapshot 当前值到 change.old_value
          - 如果注册了 apply handler → 调用它真正修改 global state
          - 否则 → dry-run，只记 applied=True（与 R6-5 初版一致）
          - 调用方应通过 register_apply_handler 为想要真正落地的 policy_key 注册处理函数

        异常语义: handler 抛异常 → logger 记录, applied 仍置 True
                 （handler 内部已有变更, 不回退）
        """
        change.applied = True
        change.applied_at = time.time()
        change.old_value = self._snapshot_current_value(change.policy_key)

        handler = self._apply_handlers.get(change.policy_key)
        if handler is None:
            logger.info(
                f"[PolicyAdjuster] applied (dry-run, no handler) {change.policy_key} "
                f"{change.old_value!r} -> {change.new_value!r} reason={change.reason}"
            )
            return

        try:
            handler(change)
            logger.info(
                f"[PolicyAdjuster] applied (handler) {change.policy_key} "
                f"{change.old_value!r} -> {change.new_value!r} reason={change.reason}"
            )
        except Exception as e:
            logger.error(
                f"[PolicyAdjuster] handler failed for {change.policy_key}: {e}"
            )

    def _snapshot_current_value(self, policy_key: str) -> Any:
        """粗粒度读取当前 policy 值，供 old_value 记录。"""
        try:
            from backend.config import settings
            if policy_key == "model.default_name":
                return settings.LLM_MODEL_NAME
            if policy_key == "skill.default_timeout_seconds":
                return 60  # 当前硬编码在 engine 里
            return None
        except Exception:
            return None

    def _rollback_expired(self, now: float) -> None:
        import dataclasses as _dc
        for c in self._changes:
            if c.applied and not c.rolled_back and now >= c.expires_at:
                c.rolled_back = True
                c.rolled_back_at = now

                # 若有 handler 已真正落地, 构造反向 change 调 handler 把值恢复回去
                handler = self._apply_handlers.get(c.policy_key)
                if handler is not None:
                    reverse = _dc.replace(
                        c, new_value=c.old_value, old_value=c.new_value,
                        reason=f"TTL rollback: {c.reason}",
                    )
                    try:
                        handler(reverse)
                    except Exception as e:
                        logger.error(
                            f"[PolicyAdjuster] rollback handler failed "
                            f"{c.policy_key}: {e}"
                        )

                self._emit(c, "rolled_back")
                logger.info(
                    f"[PolicyAdjuster] rolled back {c.policy_key} after TTL "
                    f"(expired at {c.expires_at})"
                )

    # ── Telemetry ────────────────────────────────────────

    def _emit(self, change: PolicyChange, phase: str) -> None:
        try:
            from backend.core.telemetry import telemetry, TelemetryEventType
            evt = {
                "suggested": TelemetryEventType.POLICY_SUGGESTED,
                "applied": TelemetryEventType.POLICY_APPLIED,
                "rolled_back": TelemetryEventType.POLICY_ROLLED_BACK,
            }.get(phase)
            if evt is None:
                return
            telemetry.emit(
                evt,
                change.to_dict(),
                component="PolicyAdjuster",
            )
        except Exception:
            pass


# ── 默认单例（按 settings 构造 shadow 模式） ──────────────
def _build_default_adjuster() -> PolicyAdjuster:
    try:
        from backend.config import settings
        mode = (settings.POLICY_ENFORCE_MODE or "shadow").lower()
    except Exception:
        mode = "shadow"
    return PolicyAdjuster(enforce_mode=mode)


policy_adjuster = _build_default_adjuster()
