# -*- coding: utf-8 -*-
"""backend/routers/external/workflow_sse.py

SSE 实时进度推送端点
GET /api/v1/workflows/{run_id}/stream → EventSourceResponse

前端使用:
  const es = new EventSource('/api/v1/workflows/<run_id>/stream');
  es.addEventListener('step_completed', (e) => { ... });
  es.addEventListener('final', (e) => { es.close(); });
  es.addEventListener('error', (e) => { es.close(); });
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from backend.core.progress_channel import (
    progress_manager,
    ProgressEvent,
    subscribe_via_redis,
)

router = APIRouter()

# ── 心跳间隔 (秒) ─────────────────────────────────────────────────
_HEARTBEAT_INTERVAL = 15
# ── 最大等待本地通道创建时间 (秒) ─────────────────────────────────
# 多 worker 部署下，本地 channel 可能永远不会在当前 worker 出现，所以等待时间
# 较短，超时后走 Redis fallback。
_MAX_WAIT_LOCAL_CHANNEL = 3
# ── SSE 流最大持续时间 (秒)，防止僵尸连接 ────────────────────────
_MAX_STREAM_DURATION = 600


async def _stream_local(channel, request: Request) -> AsyncGenerator[dict, None]:
    """订阅本地 channel（同 worker 内）。"""
    async for event in channel.subscribe():
        if await request.is_disconnected():
            logger.info(f"[SSE] client disconnected: run_id={channel.run_id}")
            return

        yield {
            "event": event.event_type,
            "data": json.dumps(event.data, ensure_ascii=False, default=str),
        }

        if event.event_type in ("final", "error"):
            logger.info(
                f"[SSE] terminal event '{event.event_type}': run_id={channel.run_id}"
            )
            return


async def _stream_redis(redis, run_id: str, request: Request) -> AsyncGenerator[dict, None]:
    """订阅 Redis pubsub（跨 worker fallback）。"""
    async def _disconnected():
        return await request.is_disconnected()

    async for event in subscribe_via_redis(
        redis, run_id, disconnected_checker=_disconnected
    ):
        yield {
            "event": event.event_type,
            "data": json.dumps(event.data, ensure_ascii=False, default=str),
        }


async def _event_generator(
    run_id: str, request: Request
) -> AsyncGenerator[dict, None]:
    """SSE 事件生成器。

    路径选择（P0-SSE-MultiWorker 修复）：
      1. 本地 channel 存在（workflow 在本 worker 跑）→ 订阅本地 asyncio.Queue
      2. 本地 channel 暂不存在 → 短暂等待（最多 _MAX_WAIT_LOCAL_CHANNEL 秒）
      3. 依然没有本地 channel，但 redis 可用 → fallback 订阅 Redis pubsub
      4. redis 也不可用 → 报 channel_not_found

    这保证了多 worker 部署下，创建 channel 的 worker ≠ 订阅 SSE 的 worker
    时，前端仍能通过 Redis pubsub 拿到事件。
    """
    # 1. 短暂等待本地 channel 出现（单 worker 或本 worker 跑 workflow 的快路径）
    channel = progress_manager.get_channel(run_id)
    waited = 0.0
    while channel is None and waited < _MAX_WAIT_LOCAL_CHANNEL:
        if await request.is_disconnected():
            logger.info(f"[SSE] client disconnected while waiting: run_id={run_id}")
            return
        await asyncio.sleep(0.2)
        waited += 0.2
        channel = progress_manager.get_channel(run_id)

    try:
        if channel is not None:
            # 本地路径（快）
            logger.info(f"[SSE] stream started (local) run_id={run_id}")
            async for chunk in _stream_local(channel, request):
                yield chunk
            return

        # 2. 本地无 channel，尝试 Redis fallback
        redis = progress_manager.redis
        if redis is None:
            yield {
                "event": "error",
                "data": json.dumps(
                    {
                        "run_id": run_id,
                        "error": "channel_not_found",
                        "message": (
                            f"等待 {_MAX_WAIT_LOCAL_CHANNEL}s 后未找到本地 channel，"
                            f"且 redis 不可用，无法跨 worker 订阅"
                        ),
                    },
                    ensure_ascii=False,
                ),
            }
            return

        logger.info(f"[SSE] stream started (redis fallback) run_id={run_id}")
        async for chunk in _stream_redis(redis, run_id, request):
            yield chunk

    except asyncio.CancelledError:
        logger.info(f"[SSE] stream cancelled: run_id={run_id}")
    except Exception as e:
        logger.error(f"[SSE] stream error: run_id={run_id} {e}")
        yield {
            "event": "error",
            "data": json.dumps(
                {"run_id": run_id, "error": "stream_error", "message": "流式推送异常"},
                ensure_ascii=False,
            ),
        }


@router.get("/workflows/{run_id}/stream")
async def workflow_stream(run_id: str, request: Request):
    """
    SSE 实时进度推送。

    前端通过 EventSource 连接此端点，实时接收 workflow 执行进度。

    **事件类型**:
    - `route_decided` — 路由决策完成
    - `step_started` — 节点开始执行
    - `step_completed` — 节点执行完成
    - `step_failed` — 节点执行失败
    - `hitl_required` — 需要人工审核
    - `hitl_resolved` — 人工审核完成
    - `final` — workflow 完成 (收到后应关闭连接)
    - `error` — workflow 失败 (收到后应关闭连接)
    """
    return EventSourceResponse(
        _event_generator(run_id, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Nginx 禁用缓冲
        },
        ping=_HEARTBEAT_INTERVAL,
    )
