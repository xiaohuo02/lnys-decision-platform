# -*- coding: utf-8 -*-
"""backend/routers/admin/eval_verdicts.py — R6-5 Eval + Policy 只读路由

端点:
  POST /admin/eval/evaluate            — 触发一次周期评测（默认 5 分钟窗口）
  GET  /admin/eval/verdicts            — 最近产出的 verdict
  GET  /admin/policy/changes           — 最近的 PolicyChange（建议/应用/回滚）
  GET  /admin/policy/mode              — 当前 enforce 模式 + whitelist
  POST /admin/policy/mode              — 切换 shadow / enforce（需管理员权限）

所有数据都是**内存环形缓冲**的快照（不查 DB），可直接返回。
enforce mode 默认 shadow；切换到 enforce 需走 POST，并带 whitelist 限制。
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Body, Query, HTTPException

router = APIRouter(tags=["admin-eval-policy"])


# ── Eval 端点 ─────────────────────────────────────────────

@router.post("/eval/evaluate")
async def eval_evaluate(window_seconds: int = Query(300, ge=60, le=3600)):
    """触发一次 PeriodicEvaluator.evaluate()，返回本次产出的 verdict 列表。

    生产场景下此端点由定时任务调用；admin 手动调用可立即产出快照，
    供可观测面板调试。
    """
    from backend.governance.eval_center.periodic_evaluator import periodic_evaluator
    verdicts = periodic_evaluator.evaluate(window_seconds=window_seconds)
    # 顺手把新产出的 verdict 推送给 PolicyAdjuster（连通 R6-5 闭环）
    applied_changes = []
    try:
        from backend.governance.policy_center.policy_adjuster import policy_adjuster
        applied_changes = policy_adjuster.process(verdicts)
    except Exception:
        applied_changes = []

    return {
        "ok": True,
        "data": {
            "verdicts": [v.to_dict() for v in verdicts],
            "policy_changes": [c.to_dict() for c in applied_changes],
            "window_seconds": window_seconds,
        },
    }


@router.get("/eval/verdicts")
async def eval_verdicts(
    limit: int = Query(50, ge=1, le=500),
    status: Optional[str] = Query(
        None, description="过滤状态: normal / warning / critical / insufficient",
    ),
):
    """最近产出的 EvalVerdict（内存环形缓冲）。"""
    from backend.governance.eval_center.periodic_evaluator import periodic_evaluator
    items = periodic_evaluator.recent(limit=limit, status=status)
    return {"ok": True, "data": items, "total": len(items)}


# ── Policy 端点 ───────────────────────────────────────────

@router.get("/policy/changes")
async def policy_changes(
    limit: int = Query(50, ge=1, le=500),
    applied_only: bool = Query(False),
):
    """最近的 PolicyChange（建议/应用/回滚）。"""
    from backend.governance.policy_center.policy_adjuster import policy_adjuster
    items = policy_adjuster.recent(limit=limit, applied_only=applied_only)
    return {"ok": True, "data": items, "total": len(items)}


@router.get("/policy/mode")
async def policy_mode_get():
    """当前 PolicyAdjuster 的 enforce mode + whitelist。"""
    from backend.governance.policy_center.policy_adjuster import policy_adjuster
    return {
        "ok": True,
        "data": {
            "mode": policy_adjuster.mode,
            "whitelist": sorted(policy_adjuster._whitelist),
        },
    }


@router.post("/policy/mode")
async def policy_mode_set(
    payload: dict = Body(...),
):
    """切换 enforce 模式 + 更新 whitelist。

    payload 示例:
      {"mode": "enforce", "whitelist": ["model.default_name"]}

    当前接口不做强鉴权（沿用路由级 admin 鉴权），但对 whitelist 强制限制：
    只允许内置支持的 policy_key 子集。
    """
    from backend.governance.policy_center.policy_adjuster import (
        policy_adjuster,
        _RECOMMENDATION_HANDLERS,
    )

    mode = str(payload.get("mode", "")).lower()
    if mode not in ("shadow", "enforce"):
        raise HTTPException(status_code=400, detail="mode must be 'shadow' or 'enforce'")

    whitelist_in: List[str] = list(payload.get("whitelist") or [])

    # 计算当前支持的 policy_key 集合（基于 handlers）
    supported = set()
    for handler in _RECOMMENDATION_HANDLERS.values():
        # 用一个虚拟 verdict 提取 policy_key
        try:
            from backend.governance.eval_center.periodic_evaluator import EvalVerdict
            dummy = EvalVerdict(
                metric="x", subject="x", value=0,
                threshold_warning=0, threshold_critical=0,
                status="warning", sample_size=10,
                window_seconds=60, timestamp=0,
            )
            pk, *_ = handler(dummy)
            supported.add(pk)
        except Exception:
            continue

    illegal = [k for k in whitelist_in if k not in supported]
    if illegal:
        raise HTTPException(
            status_code=400,
            detail=f"whitelist contains unsupported keys: {illegal}. supported={sorted(supported)}",
        )

    policy_adjuster.set_mode(mode)
    policy_adjuster.set_whitelist(whitelist_in)

    return {
        "ok": True,
        "data": {
            "mode": policy_adjuster.mode,
            "whitelist": sorted(policy_adjuster._whitelist),
        },
    }
