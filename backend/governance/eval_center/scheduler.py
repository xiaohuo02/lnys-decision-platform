# -*- coding: utf-8 -*-
"""backend/governance/eval_center/scheduler.py — 评测定时任务

接入已有的 CopilotPatrolScheduler (APScheduler) 注册评测定时任务：
  - 每天凌晨 2:00 — ML Agent 回归测试（范式一：Karpathy Loop）
  - 每天凌晨 3:00 — 从昨日 trace 提取 Tips（范式三 Phase 1）
  - 每周日凌晨 4:00 — Tips 聚类合并（范式三 Phase 2）
  - 每周一凌晨 5:00 — Skill Prompt 回归检测（范式二）
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import sqlalchemy
from loguru import logger


async def run_ml_agent_regression(db_factory=None) -> Dict[str, Any]:
    """每日 ML Agent 回归测试

    遍历所有 target_type='ml_agent' 的活跃实验，重新运行。
    """
    from backend.database import SessionLocal
    from backend.governance.eval_center.eval_service import run_experiment

    db = db_factory() if db_factory else SessionLocal()
    results = []

    try:
        rows = db.execute(sqlalchemy.text("""
            SELECT experiment_id, experiment_name
            FROM eval_experiments
            WHERE status IN ('completed', 'failed')
              AND JSON_UNQUOTE(JSON_EXTRACT(metadata, '$.schedule')) = 'daily_regression'
            ORDER BY created_at DESC
        """)).fetchall()

        for row in rows:
            exp = dict(row._mapping)
            eid = exp["experiment_id"]
            try:
                # 将状态重置为 pending 以允许重跑
                db.execute(sqlalchemy.text(
                    "UPDATE eval_experiments SET status='pending' WHERE experiment_id=:id"
                ), {"id": eid})
                db.commit()

                result = run_experiment(eid, db)
                results.append({"experiment_id": eid, "status": "ok", "pass_rate": result.get("pass_rate")})

                # 回归检测
                await _check_regression(eid, result, db)

            except Exception as exc:
                logger.error(f"[scheduler] ML Agent 回归 {eid}: {exc}")
                results.append({"experiment_id": eid, "status": "error", "error": str(exc)})

    finally:
        db.close()

    logger.info(f"[scheduler] ML Agent 每日回归完成: {len(results)} 个实验")
    return {"task": "ml_agent_regression", "results": results}


async def extract_daily_tips(db_factory=None) -> Dict[str, Any]:
    """每日从昨日 trace 提取 Tips"""
    from backend.database import SessionLocal
    from backend.governance.eval_center.memory.tip_extractor import TipExtractor
    from backend.governance.eval_center.memory.tip_manager import TipManager

    db = db_factory() if db_factory else SessionLocal()
    extractor = TipExtractor()
    manager = TipManager(db=db)

    try:
        yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
        today = datetime.utcnow().strftime("%Y-%m-%d")

        rows = db.execute(sqlalchemy.text("""
            SELECT run_id, workflow_name, status, duration_ms, steps_json
            FROM trace_runs
            WHERE created_at >= :yesterday AND created_at < :today
              AND status IN ('completed', 'partial')
            ORDER BY created_at DESC
            LIMIT 100
        """), {"yesterday": yesterday, "today": today}).fetchall()

        traces = []
        for row in rows:
            r = dict(row._mapping)
            steps = r.get("steps_json", "[]")
            if isinstance(steps, str):
                try:
                    steps = json.loads(steps)
                except json.JSONDecodeError:
                    steps = []
            traces.append({
                "run_id": r.get("run_id", ""),
                "workflow_name": r.get("workflow_name", ""),
                "status": r.get("status", ""),
                "duration_ms": r.get("duration_ms", 0),
                "steps": steps,
            })

        all_tips = await extractor.extract_batch(traces)
        saved = manager.save_tips(all_tips, db=db)

        logger.info(f"[scheduler] Tips 提取完成: {len(traces)} traces → {saved} tips")
        return {"task": "extract_daily_tips", "traces": len(traces), "tips_saved": saved}

    finally:
        db.close()


async def consolidate_tips(db_factory=None) -> Dict[str, Any]:
    """每周 Tips 聚类合并"""
    from backend.database import SessionLocal
    from backend.governance.eval_center.memory.tip_manager import TipManager

    db = db_factory() if db_factory else SessionLocal()
    manager = TipManager(db=db)

    try:
        # 获取所有活跃 Tips
        all_tips = manager.get_active_tips(limit=500, db=db)

        if len(all_tips) < 2:
            return {"task": "consolidate_tips", "message": "Tips 不足，跳过合并"}

        # 泛化未泛化的 Tips
        generalized = 0
        for tip in all_tips:
            if not tip.get("generalized_desc"):
                result = await manager.generalize_tip(
                    content=tip.get("content", ""),
                    trigger=tip.get("trigger_desc", ""),
                )
                db.execute(sqlalchemy.text(
                    "UPDATE eval_agent_tips SET generalized_desc=:desc WHERE tip_id=:tid"
                ), {
                    "desc": result.get("generalized_content", tip.get("content", "")),
                    "tid": tip.get("tip_id"),
                })
                generalized += 1

        db.commit()

        stats = manager.get_stats(db=db)
        logger.info(f"[scheduler] Tips 合并完成: 泛化 {generalized} 条, 统计={stats}")
        return {"task": "consolidate_tips", "generalized": generalized, "stats": stats}

    finally:
        db.close()


async def run_skill_regression(db_factory=None) -> Dict[str, Any]:
    """每周 Skill Prompt 回归检测"""
    from backend.database import SessionLocal
    from backend.governance.eval_center.eval_service import run_experiment

    db = db_factory() if db_factory else SessionLocal()
    results = []

    try:
        rows = db.execute(sqlalchemy.text("""
            SELECT experiment_id, experiment_name
            FROM eval_experiments
            WHERE status IN ('completed', 'failed')
              AND JSON_UNQUOTE(JSON_EXTRACT(metadata, '$.schedule')) = 'weekly_skill_regression'
            ORDER BY created_at DESC
        """)).fetchall()

        for row in rows:
            exp = dict(row._mapping)
            eid = exp["experiment_id"]
            try:
                db.execute(sqlalchemy.text(
                    "UPDATE eval_experiments SET status='pending' WHERE experiment_id=:id"
                ), {"id": eid})
                db.commit()

                result = run_experiment(eid, db)
                results.append({"experiment_id": eid, "status": "ok", "pass_rate": result.get("pass_rate")})

                await _check_regression(eid, result, db)

            except Exception as exc:
                logger.error(f"[scheduler] Skill 回归 {eid}: {exc}")
                results.append({"experiment_id": eid, "status": "error", "error": str(exc)})

    finally:
        db.close()

    logger.info(f"[scheduler] Skill 每周回归完成: {len(results)} 个实验")
    return {"task": "skill_regression", "results": results}


async def _check_regression(
    experiment_id: str,
    current_result: Dict[str, Any],
    db,
    regression_threshold: float = 0.05,
) -> None:
    """检查是否发生回归，触发告警"""
    current_rate = current_result.get("pass_rate", 0)

    # 查询上次结果
    row = db.execute(sqlalchemy.text("""
        SELECT pass_rate FROM eval_experiments
        WHERE experiment_id != :eid
          AND dataset_id = (SELECT dataset_id FROM eval_experiments WHERE experiment_id = :eid)
          AND status = 'completed'
        ORDER BY ended_at DESC LIMIT 1
    """), {"eid": experiment_id}).fetchone()

    if row is None:
        return

    prev_rate = float(dict(row._mapping).get("pass_rate", 0))

    if current_rate < prev_rate - regression_threshold:
        logger.warning(
            f"[scheduler] 检测到回归！实验 {experiment_id}: "
            f"pass_rate {prev_rate:.2%} → {current_rate:.2%} (Δ={current_rate - prev_rate:+.2%})"
        )
        # 发送飞书告警
        try:
            from backend.integrations.feishu.bridge import FeishuBridge
            bridge = FeishuBridge()
            await bridge.send_text_message(
                f"🔴 [评测中心] 检测到回归\n"
                f"实验: {experiment_id}\n"
                f"pass_rate: {prev_rate:.2%} → {current_rate:.2%}\n"
                f"请及时排查",
            )
        except Exception as exc:
            logger.warning(f"[scheduler] 飞书告警发送失败: {exc}")


def register_eval_jobs(scheduler) -> None:
    """注册评测定时任务到 APScheduler

    Args:
        scheduler: APScheduler 实例（通常是 CopilotPatrolScheduler.scheduler）
    """
    # 每天凌晨 2:00 — ML Agent 回归测试
    scheduler.add_job(
        lambda: asyncio.get_event_loop().run_until_complete(run_ml_agent_regression()),
        'cron', hour=2, minute=0,
        id='eval_ml_regression', replace_existing=True,
        name='ML Agent 每日回归测试',
    )

    # 每天凌晨 3:00 — 从昨日 trace 提取 Tips
    scheduler.add_job(
        lambda: asyncio.get_event_loop().run_until_complete(extract_daily_tips()),
        'cron', hour=3, minute=0,
        id='eval_tip_extraction', replace_existing=True,
        name='每日 Tips 提取',
    )

    # 每周日凌晨 4:00 — Tips 聚类合并
    scheduler.add_job(
        lambda: asyncio.get_event_loop().run_until_complete(consolidate_tips()),
        'cron', day_of_week='sun', hour=4, minute=0,
        id='eval_tip_consolidation', replace_existing=True,
        name='每周 Tips 聚类合并',
    )

    # 每周一凌晨 5:00 — Skill Prompt 回归检测
    scheduler.add_job(
        lambda: asyncio.get_event_loop().run_until_complete(run_skill_regression()),
        'cron', day_of_week='mon', hour=5, minute=0,
        id='eval_skill_regression', replace_existing=True,
        name='Skill Prompt 每周回归检测',
    )

    logger.info("[scheduler] 评测定时任务已注册 (4 个 job)")
