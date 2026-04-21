# -*- coding: utf-8 -*-
"""backend/governance/eval_center/periodic_evaluator.py — Telemetry → EvalVerdict (R6-5)

职责:
  周期性从 telemetry 拉原始事件, 按 skill / model / 组件维度聚合, 产出
  EvalVerdict（"某指标 > 阈值 → 告警/降级建议"）。

输入:
  - telemetry 最近 N 条事件（从 ring buffer 或 Redis Stream）

输出:
  - list[EvalVerdict] 存入内存环形缓冲（MAX_VERDICTS）
  - 每条 verdict 触发一次 EVAL_VERDICT 遥测事件（供 admin 查询 / 后续 PolicyAdjuster 消费）

支持的 metric:
  - skill_hit_rate_5m         最近 5 分钟 skill 被路由命中的比例
  - tool_timeout_rate_5m      最近 5 分钟 skill 超时比例
  - model_latency_p95_5m      每个 model 最近 5 分钟 p95 延迟 (ms)
  - router_failure_rate_5m    最近 5 分钟 routing 失败比例
  - pii_block_rate_5m         最近 5 分钟 input_guard 拦截比例（作为 PII 误杀代理指标）

阈值:
  - 默认阈值来自模块常量 DEFAULT_THRESHOLDS, 可在构造时覆盖
  - status 判定: normal / warning / critical

设计要点:
  - 无副作用: 只读 telemetry, 不写 DB (后续迭代可加)
  - 无状态: evaluate() 可幂等多次调用
  - 降级安全: telemetry 不可用时产出空列表, 不抛异常
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from loguru import logger


# ── Verdict 数据结构 ────────────────────────────────────────────

@dataclass(frozen=True)
class EvalVerdict:
    """一次评测结论。"""
    metric: str                      # 指标名，如 model_latency_p95_5m
    subject: str                     # 主体（model name / skill name / "global"）
    value: float                     # 实测值
    threshold_warning: float         # 警告阈值
    threshold_critical: float        # 严重阈值
    status: str                      # normal / warning / critical
    sample_size: int                 # 样本量（< 最小样本时 status=insufficient）
    window_seconds: int              # 统计窗口长度
    timestamp: float                 # 产出时间戳
    recommendation: str = ""         # 给 PolicyAdjuster 的建议 key, 如 "model_downgrade:qwen-plus"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric": self.metric,
            "subject": self.subject,
            "value": round(self.value, 4),
            "threshold_warning": self.threshold_warning,
            "threshold_critical": self.threshold_critical,
            "status": self.status,
            "sample_size": self.sample_size,
            "window_seconds": self.window_seconds,
            "timestamp": self.timestamp,
            "recommendation": self.recommendation,
        }


# ── 默认阈值配置 ────────────────────────────────────────────────

DEFAULT_THRESHOLDS: Dict[str, Dict[str, float]] = {
    # metric → {warning, critical}
    "skill_hit_rate_5m":       {"warning": 0.50, "critical": 0.30},   # 低于阈值告警
    "tool_timeout_rate_5m":    {"warning": 0.05, "critical": 0.15},   # 高于阈值告警
    "model_latency_p95_5m":    {"warning": 5000, "critical": 8000},   # ms
    "router_failure_rate_5m":  {"warning": 0.10, "critical": 0.25},
    "pii_block_rate_5m":       {"warning": 0.20, "critical": 0.50},   # 高块率可能意味误杀
}

MIN_SAMPLE_SIZE = 5   # 样本少于此数量的指标标记 insufficient


class PeriodicEvaluator:
    """周期性评测器。

    用法:
        evaluator = PeriodicEvaluator()
        verdicts = evaluator.evaluate(window_seconds=300)
        for v in verdicts:
            if v.status != "normal":
                # 推送到 PolicyAdjuster
                ...

    线程安全:
      - evaluate 只读 telemetry, 幂等可重入
      - verdict 环形缓冲有 lock (通过 deque 自身的线程安全)
    """

    MAX_VERDICTS = 500

    def __init__(
        self,
        thresholds: Optional[Dict[str, Dict[str, float]]] = None,
        db_session_factory: Any = None,
    ):
        """
        Args:
            thresholds:         覆盖默认阈值
            db_session_factory: 可选，同步 sessionmaker。传入后每次 evaluate 会
                                best-effort 把新 verdict 持久化到 eval_verdict 表；
                                不传则仅使用内存环形缓冲（与 R6-5 初版一致）。
        """
        self._thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
        self._verdicts: deque = deque(maxlen=self.MAX_VERDICTS)
        self._db_factory = db_session_factory

    def configure(self, db_session_factory: Any = None) -> None:
        """运行时注入 db_session_factory（lifespan 启动阶段调用）。

        传入后每次 evaluate 会 best-effort 写 eval_verdict 表。
        传 None 可关闭持久化，退回仅内存模式。
        """
        self._db_factory = db_session_factory

    @property
    def verdicts(self) -> List[EvalVerdict]:
        """返回内存环形缓冲中的全部 verdict。"""
        return list(self._verdicts)

    def recent(self, limit: int = 50, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """查询最近 verdict（供 admin API 使用）。"""
        items = list(self._verdicts)
        if status:
            items = [v for v in items if v.status == status]
        return [v.to_dict() for v in items[-limit:]]

    def clear(self) -> None:
        """清空缓冲（测试用）。"""
        self._verdicts.clear()

    # ── 核心入口 ────────────────────────────────────────────

    def evaluate(self, window_seconds: int = 300) -> List[EvalVerdict]:
        """拉 telemetry 并产出 verdict 列表。

        Args:
            window_seconds: 统计窗口（秒），默认 5 分钟

        Returns:
            本次产出的新 verdict 列表（也会追加到内部缓冲）
        """
        try:
            from backend.core.telemetry import telemetry
            events_raw = telemetry.recent(limit=2000)
        except Exception as e:
            logger.debug(f"[PeriodicEvaluator] telemetry recent failed: {e}")
            return []

        now = time.time()
        cutoff = now - window_seconds
        events = [e for e in events_raw if e.get("timestamp", 0) >= cutoff]
        if not events:
            return []

        new_verdicts: List[EvalVerdict] = []

        # 各指标分别计算
        new_verdicts.extend(self._eval_skill_hit_rate(events, window_seconds, now))
        new_verdicts.extend(self._eval_tool_timeout_rate(events, window_seconds, now))
        new_verdicts.extend(self._eval_model_latency_p95(events, window_seconds, now))
        new_verdicts.extend(self._eval_router_failure_rate(events, window_seconds, now))
        new_verdicts.extend(self._eval_pii_block_rate(events, window_seconds, now))

        # 追加到缓冲 + 发 EVAL_VERDICT 遥测
        for v in new_verdicts:
            self._verdicts.append(v)
            try:
                from backend.core.telemetry import telemetry, TelemetryEventType
                telemetry.emit(
                    TelemetryEventType.EVAL_VERDICT,
                    v.to_dict(),
                    component="PeriodicEvaluator",
                )
            except Exception:
                pass

        # R6-5 持久化: 若传入了 db_session_factory, best-effort 写 eval_verdict 表
        if new_verdicts and self._db_factory is not None:
            self._persist_to_db(new_verdicts)

        logger.info(
            f"[PeriodicEvaluator] produced {len(new_verdicts)} verdicts "
            f"from {len(events)} events in window={window_seconds}s"
        )
        return new_verdicts

    def _persist_to_db(self, verdicts: List[EvalVerdict]) -> None:
        """best-effort 批量写入 eval_verdict 表。失败只记日志不抛异常。"""
        try:
            import sqlalchemy
            db = self._db_factory()
        except Exception as e:
            logger.debug(f"[PeriodicEvaluator] open db session failed: {e}")
            return

        try:
            for v in verdicts:
                db.execute(sqlalchemy.text(
                    "INSERT INTO eval_verdict "
                    "(metric, subject, `value`, threshold_warning, threshold_critical, "
                    " status, sample_size, window_seconds, recommendation, created_at) "
                    "VALUES (:metric, :subject, :value, :thw, :thc, "
                    "        :status, :n, :w, :rec, FROM_UNIXTIME(:ts))"
                ), {
                    "metric": v.metric,
                    "subject": v.subject,
                    "value": v.value,
                    "thw": v.threshold_warning,
                    "thc": v.threshold_critical,
                    "status": v.status,
                    "n": v.sample_size,
                    "w": v.window_seconds,
                    "rec": v.recommendation,
                    "ts": v.timestamp,
                })
            db.commit()
        except Exception as e:
            logger.warning(f"[PeriodicEvaluator] db persist failed (non-fatal): {e}")
            try:
                db.rollback()
            except Exception:
                pass
        finally:
            try:
                db.close()
            except Exception:
                pass

    # ── 状态判定 ────────────────────────────────────────────

    def _status_for(
        self,
        metric: str,
        value: float,
        higher_is_worse: bool,
        sample_size: int,
    ) -> str:
        if sample_size < MIN_SAMPLE_SIZE:
            return "insufficient"
        th = self._thresholds.get(metric, {})
        warn = th.get("warning")
        crit = th.get("critical")
        if warn is None or crit is None:
            return "normal"
        if higher_is_worse:
            if value >= crit:
                return "critical"
            if value >= warn:
                return "warning"
            return "normal"
        else:
            if value <= crit:
                return "critical"
            if value <= warn:
                return "warning"
            return "normal"

    def _mk_verdict(
        self,
        metric: str,
        subject: str,
        value: float,
        higher_is_worse: bool,
        sample_size: int,
        window_seconds: int,
        now: float,
        recommendation: str = "",
    ) -> EvalVerdict:
        status = self._status_for(metric, value, higher_is_worse, sample_size)
        th = self._thresholds.get(metric, {})
        return EvalVerdict(
            metric=metric,
            subject=subject,
            value=value,
            threshold_warning=th.get("warning", 0),
            threshold_critical=th.get("critical", 0),
            status=status,
            sample_size=sample_size,
            window_seconds=window_seconds,
            timestamp=now,
            recommendation=recommendation if status in ("warning", "critical") else "",
        )

    # ── 具体指标计算 ────────────────────────────────────────

    def _eval_skill_hit_rate(
        self, events: List[Dict[str, Any]], window: int, now: float
    ) -> List[EvalVerdict]:
        run_starts = [e for e in events if e.get("type") == "run_started"]
        skill_exec = [e for e in events if e.get("type") == "skill_executed"]
        total = len(run_starts)
        hit = len(skill_exec)
        if total == 0:
            return []
        rate = hit / total
        return [self._mk_verdict(
            metric="skill_hit_rate_5m",
            subject="global",
            value=rate,
            higher_is_worse=False,   # 值越低越糟
            sample_size=total,
            window_seconds=window,
            now=now,
            recommendation="enhance_keyword_fallback" if rate < 0.5 else "",
        )]

    def _eval_tool_timeout_rate(
        self, events: List[Dict[str, Any]], window: int, now: float
    ) -> List[EvalVerdict]:
        skill_exec = [e for e in events if e.get("type") == "skill_executed"]
        total = len(skill_exec)
        if total == 0:
            return []
        timeouts = sum(1 for e in skill_exec if (e.get("data") or {}).get("error") == "timeout")
        rate = timeouts / total
        return [self._mk_verdict(
            metric="tool_timeout_rate_5m",
            subject="global",
            value=rate,
            higher_is_worse=True,
            sample_size=total,
            window_seconds=window,
            now=now,
            recommendation="extend_skill_timeout" if rate > 0.05 else "",
        )]

    def _eval_model_latency_p95(
        self, events: List[Dict[str, Any]], window: int, now: float
    ) -> List[EvalVerdict]:
        # 按 model 分组收集 latency
        by_model: Dict[str, List[int]] = defaultdict(list)
        for e in events:
            if e.get("type") != "model_completed":
                continue
            data = e.get("data") or {}
            model = data.get("model") or "unknown"
            lat = data.get("latency_ms")
            if isinstance(lat, (int, float)):
                by_model[model].append(int(lat))

        results: List[EvalVerdict] = []
        for model, latencies in by_model.items():
            latencies.sort()
            n = len(latencies)
            if n == 0:
                continue
            idx = max(0, int(n * 0.95) - 1)
            p95 = latencies[idx]
            results.append(self._mk_verdict(
                metric="model_latency_p95_5m",
                subject=model,
                value=float(p95),
                higher_is_worse=True,
                sample_size=n,
                window_seconds=window,
                now=now,
                recommendation=f"model_downgrade:{model}" if p95 > 8000 else "",
            ))
        return results

    def _eval_router_failure_rate(
        self, events: List[Dict[str, Any]], window: int, now: float
    ) -> List[EvalVerdict]:
        # 简化判定: run_failed 中带 "router" 错误占 run_started 的比例
        total = sum(1 for e in events if e.get("type") == "run_started")
        fails = 0
        for e in events:
            if e.get("type") != "run_failed":
                continue
            err = (e.get("data") or {}).get("error", "") or ""
            if "router" in err.lower() or "route" in err.lower():
                fails += 1
        if total == 0:
            return []
        rate = fails / total
        return [self._mk_verdict(
            metric="router_failure_rate_5m",
            subject="global",
            value=rate,
            higher_is_worse=True,
            sample_size=total,
            window_seconds=window,
            now=now,
            recommendation="enhance_router_prompt" if rate > 0.10 else "",
        )]

    def _eval_pii_block_rate(
        self, events: List[Dict[str, Any]], window: int, now: float
    ) -> List[EvalVerdict]:
        check_events = [
            e for e in events
            if e.get("type") in ("security_check_passed", "security_check_blocked")
        ]
        total = len(check_events)
        if total == 0:
            return []
        blocked = sum(1 for e in check_events if e.get("type") == "security_check_blocked")
        rate = blocked / total
        return [self._mk_verdict(
            metric="pii_block_rate_5m",
            subject="global",
            value=rate,
            higher_is_worse=True,
            sample_size=total,
            window_seconds=window,
            now=now,
            recommendation="relax_pii_rules" if rate > 0.20 else "",
        )]


# ── 默认单例 ────────────────────────────────────────────────
periodic_evaluator = PeriodicEvaluator()
