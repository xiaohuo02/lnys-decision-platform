# -*- coding: utf-8 -*-
"""backend/core/bg_run_tracker.py — 后台 workflow 运行状态跟踪

提取自 analyze.py / workflow.py 的公共逻辑：
  pending → running → completed / failed / cancelled
"""
import asyncio
from datetime import datetime, timedelta, timezone

import sqlalchemy
from loguru import logger

from backend.config import settings
from backend.database import get_async_session_factory
from backend.core.cancel_registry import cancel_registry


async def run_with_status(run_id: str, coro_fn, kwargs: dict) -> None:
    """包装后台 workflow，自动更新 runs 表 pending → running → completed/failed/cancelled"""
    factory = get_async_session_factory()
    async with factory() as db:
        try:
            if cancel_registry.is_cancelled(run_id):
                logger.info(f"[bg_run] run_id={run_id} already cancelled before start")
                return

            await db.execute(sqlalchemy.text(
                "UPDATE runs SET status='running' WHERE run_id=:rid AND status='pending'"
            ), {"rid": run_id})
            await db.commit()

            # 总超时保护：避免 LLM / Workflow 无限挂起占用 BG 任务槽、污染 runs 表状态
            await asyncio.wait_for(
                coro_fn(**kwargs),
                timeout=settings.BG_WORKFLOW_TIMEOUT_SECONDS,
            )

            if cancel_registry.is_cancelled(run_id):
                logger.info(f"[bg_run] run_id={run_id} cancelled during execution")
                return

            await db.execute(sqlalchemy.text(
                "UPDATE runs SET status='completed', ended_at=NOW() WHERE run_id=:rid AND status='running'"
            ), {"rid": run_id})
            await db.commit()
        except asyncio.TimeoutError:
            logger.error(
                f"[bg_run] run_id={run_id} timed out after "
                f"{settings.BG_WORKFLOW_TIMEOUT_SECONDS}s"
            )
            try:
                await db.execute(sqlalchemy.text(
                    "UPDATE runs SET status='failed', ended_at=NOW(), error_message=:msg "
                    "WHERE run_id=:rid AND status IN ('pending','running')"
                ), {
                    "rid": run_id,
                    "msg": f"workflow timeout after {settings.BG_WORKFLOW_TIMEOUT_SECONDS}s",
                })
                await db.commit()
            except sqlalchemy.exc.SQLAlchemyError as e2:
                logger.warning(f"[bg_run] failed to update run status on timeout: {e2}")
        except Exception as e:
            logger.error(f"[bg_run] run_id={run_id} failed: {e}")
            try:
                await db.execute(sqlalchemy.text(
                    "UPDATE runs SET status='failed', ended_at=NOW(), error_message=:msg "
                    "WHERE run_id=:rid AND status IN ('pending','running')"
                ), {"rid": run_id, "msg": str(e)[:500]})
                await db.commit()
            except sqlalchemy.exc.SQLAlchemyError as e2:
                logger.warning(f"[bg_run] failed to update run status: {e2}")
        finally:
            cancel_registry.remove(run_id)


async def reap_stale_runs() -> int:
    """启动自愈：把 runs 表里卡在 pending/running 超过阈值的记录标为 failed。

    覆盖场景：FastAPI BackgroundTasks 在 uvicorn reload / 容器重启时丢失，
    但 runs 表里的状态行并未被 run_with_status 的 try/except 更新过，
    导致前端一直看到 "running" 却永远拿不到结果。

    返回被标记的记录数。失败时返回 0（non-fatal）。
    """
    stale_minutes = settings.BG_WORKFLOW_STALE_MINUTES
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)
    try:
        factory = get_async_session_factory()
        async with factory() as db:
            result = await db.execute(
                sqlalchemy.text(
                    "UPDATE runs "
                    "SET status='failed', ended_at=NOW(3), error_message=:msg "
                    "WHERE status IN ('pending','running') AND started_at < :cutoff"
                ),
                {
                    "cutoff": cutoff,
                    "msg": f"auto-failed on startup: stuck > {stale_minutes}min (process likely restarted)",
                },
            )
            await db.commit()
            count = result.rowcount or 0
            if count > 0:
                logger.warning(
                    f"[startup:reap] marked {count} stale runs as 'failed' "
                    f"(stuck >{stale_minutes}min)"
                )
            else:
                logger.info(f"[startup:reap] no stale runs (threshold >{stale_minutes}min)")
            return count
    except Exception as e:
        logger.warning(f"[startup:reap] reap stale runs failed (non-fatal): {e}")
        return 0
