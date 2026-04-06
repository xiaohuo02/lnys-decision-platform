# -*- coding: utf-8 -*-
"""backend/core/memory_freshness.py — 记忆新鲜度评分引擎

设计灵感: Forge memory governance + Ebbinghaus 遗忘曲线

每条记忆的 freshness_score ∈ [0, 1] 由以下因子综合计算:
  - recency:   时间衰减 (指数衰减, half_life 可配)
  - frequency: 访问频率 (被 recall 的次数)
  - importance: 人工/系统标记的重要度
  - relevance:  与当前上下文的相关度 (可选, 需要 embedding)

用法:
    from backend.core.memory_freshness import freshness_engine

    score = freshness_engine.score(
        updated_at=datetime(2025, 1, 15),
        importance=0.7,
        access_count=3,
    )
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class FreshnessConfig(BaseModel):
    """新鲜度评分权重配置"""
    recency_weight: float = 0.4
    importance_weight: float = 0.35
    frequency_weight: float = 0.25
    half_life_days: float = 30.0      # 时间衰减半衰期
    max_access_boost: int = 10        # 访问次数上限 (避免过度放大)


class MemoryFreshnessScore(BaseModel):
    """单条记忆的新鲜度评分结果"""
    overall: float                     # 综合分 [0, 1]
    recency: float                     # 时间新鲜度 [0, 1]
    importance: float                  # 重要度 [0, 1]
    frequency: float                   # 频率分 [0, 1]
    stale_days: int                    # 距上次更新的天数
    status: str                        # fresh / warm / stale / expired


class MemoryHealthSummary(BaseModel):
    """记忆健康总览"""
    total_memories: int = 0
    active_memories: int = 0
    fresh_count: int = 0               # score > 0.7
    warm_count: int = 0                # 0.4 < score <= 0.7
    stale_count: int = 0               # 0.2 < score <= 0.4
    expired_count: int = 0             # score <= 0.2
    avg_freshness: float = 0.0
    avg_importance: float = 0.0
    layer_stats: Dict[str, int] = Field(default_factory=dict)  # rules / memory / thread
    domain_stats: Dict[str, int] = Field(default_factory=dict)


class FreshnessEngine:
    """记忆新鲜度评分引擎"""

    def __init__(self, config: Optional[FreshnessConfig] = None):
        self._config = config or FreshnessConfig()

    @property
    def config(self) -> FreshnessConfig:
        return self._config

    def score(
        self,
        updated_at: datetime,
        importance: float = 0.5,
        access_count: int = 0,
        now: Optional[datetime] = None,
    ) -> MemoryFreshnessScore:
        """计算单条记忆的新鲜度评分"""
        cfg = self._config
        now = now or datetime.now(timezone.utc)

        # ── Recency: 指数衰减 ──
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        delta_days = max((now - updated_at).total_seconds() / 86400, 0)
        recency = math.exp(-0.693 * delta_days / cfg.half_life_days)  # ln(2) ≈ 0.693

        # ── Importance: 直接映射 ──
        imp = max(0.0, min(1.0, importance))

        # ── Frequency: 对数映射 ──
        capped = min(access_count, cfg.max_access_boost)
        freq = math.log1p(capped) / math.log1p(cfg.max_access_boost)

        # ── Weighted sum ──
        overall = (
            cfg.recency_weight * recency
            + cfg.importance_weight * imp
            + cfg.frequency_weight * freq
        )
        overall = round(max(0.0, min(1.0, overall)), 4)

        # ── Status label ──
        if overall > 0.7:
            status = "fresh"
        elif overall > 0.4:
            status = "warm"
        elif overall > 0.2:
            status = "stale"
        else:
            status = "expired"

        return MemoryFreshnessScore(
            overall=overall,
            recency=round(recency, 4),
            importance=round(imp, 4),
            frequency=round(freq, 4),
            stale_days=int(delta_days),
            status=status,
        )

    def batch_score(
        self,
        memories: List[Dict[str, Any]],
        now: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """批量评分, 每条记忆附带 freshness 字段"""
        now = now or datetime.now(timezone.utc)
        results = []
        for mem in memories:
            updated = mem.get("updated_at") or mem.get("created_at") or now
            if isinstance(updated, str):
                try:
                    updated = datetime.fromisoformat(updated)
                except Exception:
                    updated = now
            fs = self.score(
                updated_at=updated,
                importance=mem.get("importance", 0.5),
                access_count=mem.get("access_count", 0),
                now=now,
            )
            results.append({
                **mem,
                "freshness": fs.model_dump(),
            })
        return results

    def health_summary(
        self,
        scored_memories: List[Dict[str, Any]],
    ) -> MemoryHealthSummary:
        """从已评分的记忆列表生成健康总览"""
        total = len(scored_memories)
        if total == 0:
            return MemoryHealthSummary()

        fresh = warm = stale = expired = 0
        imp_sum = 0.0
        fs_sum = 0.0
        domain_stats: Dict[str, int] = {}

        for mem in scored_memories:
            f = mem.get("freshness", {})
            s = f.get("overall", 0)
            fs_sum += s
            imp_sum += f.get("importance", 0)

            if s > 0.7:
                fresh += 1
            elif s > 0.4:
                warm += 1
            elif s > 0.2:
                stale += 1
            else:
                expired += 1

            domain = mem.get("domain", "general")
            domain_stats[domain] = domain_stats.get(domain, 0) + 1

        return MemoryHealthSummary(
            total_memories=total,
            active_memories=total,
            fresh_count=fresh,
            warm_count=warm,
            stale_count=stale,
            expired_count=expired,
            avg_freshness=round(fs_sum / total, 4),
            avg_importance=round(imp_sum / total, 4),
            domain_stats=domain_stats,
        )


# ── 全局单例 ──
freshness_engine = FreshnessEngine()
