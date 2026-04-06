# -*- coding: utf-8 -*-
"""backend/core/progress_channel.py — SSE 实时进度推送通道

设计来源: Claude Code + Dify 流式进度推送机制

双通道设计 (P0-SSE-MultiWorker):
  1. 本地 asyncio.Queue: 同进程订阅者，零延迟路径
  2. Redis Pub/Sub:       跨进程/跨 worker 发布；订阅端 fallback 路径

工作流节点 emit() 时，事件会同时推送到两条通道：
  - 本地订阅者（本 worker 内的 SSE 连接）
  - Redis `progress:{run_id}` 频道（其他 worker 的 SSE 连接可订阅）

SSE 端点（workflow_sse.py）的路径选择：
  - 本地 channel 存在 → 订阅本地（快）
  - 本地 channel 不存在 → fallback 订阅 Redis（跨 worker）

事件类型:
  route_decided  — SupervisorAgent 路由完成
  step_started   — 节点开始执行
  step_completed — 节点执行完成
  step_failed    — 节点执行失败
  hitl_required  — 需要人工审核
  hitl_resolved  — 人工审核完成
  final          — workflow 完成
  error          — workflow 失败
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator, Dict, Optional

from loguru import logger


# ── Redis 频道与历史存储命名规范 ──────────────────────────────────

def _redis_channel_name(run_id: str) -> str:
    """pubsub 频道名"""
    return f"progress:{run_id}"


def _redis_history_key(run_id: str) -> str:
    """事件历史 List key。用于"晚到订阅者"回放已发生的事件。"""
    return f"progress:{run_id}:history"


# 历史事件最长保留时间（秒）
_HISTORY_TTL_SECONDS = 1800


# ── ProgressEvent 结构 ────────────────────────────────────────────

class ProgressEvent:
    """单个进度事件"""
    __slots__ = ("event_type", "data")

    def __init__(self, event_type: str, data: Dict[str, Any]):
        self.event_type = event_type
        self.data = data

    def to_sse(self) -> str:
        """序列化为 SSE 格式字符串"""
        payload = json.dumps(self.data, ensure_ascii=False, default=str)
        return f"event: {self.event_type}\ndata: {payload}\n\n"

    def to_dict(self) -> dict:
        return {"event": self.event_type, "data": self.data}


# ── ProgressChannel: 单个 run 的进度通道 ──────────────────────────

class ProgressChannel:
    """
    单个 workflow run 的进度推送通道。

    用法 (发送端 — 在 Workflow 节点中):
        channel = ProgressChannel(run_id)
        await channel.emit("step_completed", {"step_name": "customer", "progress_pct": 43})
        await channel.emit("final", {"artifact_id": "xxx", "summary": "..."})
        await channel.close()

    用法 (接收端 — 在 SSE 端点中):
        channel = progress_manager.get_channel(run_id)
        async for event in channel.subscribe():
            yield event.to_sse()
    """

    def __init__(self, run_id: str, redis_client: Any = None):
        self.run_id = run_id
        self._redis = redis_client
        self._queue: asyncio.Queue[Optional[ProgressEvent]] = asyncio.Queue()
        self._closed = False
        self._subscribers: list[asyncio.Queue] = []
        # 记录创建时所在的 event loop，用于 emit_threadsafe 跨线程调度
        try:
            self._loop: Optional[asyncio.AbstractEventLoop] = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None

    def emit_threadsafe(self, event_type: str, data: Dict[str, Any]) -> None:
        """线程安全地从 worker 线程（如 run_in_executor）向主 loop 推送事件。

        仅在"所在线程无 running loop 或 loop 不同"的场景下使用；若本身已在主 loop
        中，应直接 await self.emit(...)，避免不必要的跨线程调度开销。
        """
        if self._closed:
            return
        if self._loop is None or self._loop.is_closed():
            logger.debug(
                f"[ProgressChannel] emit_threadsafe skipped run_id={self.run_id} "
                f"(no loop available)"
            )
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self.emit(event_type, data), self._loop,
            )
        except RuntimeError as e:
            # loop is closed/stopped — client disconnected / shutdown
            logger.debug(
                f"[ProgressChannel] emit_threadsafe loop unavailable "
                f"run_id={self.run_id}: {e}"
            )
        except Exception as e:
            logger.warning(
                f"[ProgressChannel] emit_threadsafe unexpected error "
                f"run_id={self.run_id}: {e}"
            )

    async def emit(self, event_type: str, data: Dict[str, Any]) -> None:
        """发送一个进度事件。

        双通道推送：
          1. 本地 asyncio.Queue（同进程订阅者）
          2. Redis Pub/Sub `progress:{run_id}` 频道（跨进程订阅者）

        即使 Redis 发布失败也不影响本地订阅，保证同 worker 内 SSE 可用。
        """
        if self._closed:
            logger.warning(f"[ProgressChannel] emit on closed channel: run_id={self.run_id}")
            return

        event = ProgressEvent(event_type, {**data, "run_id": self.run_id})

        # 推送到所有本地订阅者
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(f"[ProgressChannel] subscriber queue full, dropping event")

        # 推送到 Redis（如可用）。消息体使用结构化 JSON，便于订阅端恢复为 ProgressEvent
        #
        # Fix B（历史回放）:
        #   - 除 publish 到 pubsub 外，同时把事件 RPUSH 到 `progress:{run_id}:history` 列表
        #   - 设置 TTL 30 分钟，避免内存泄漏
        #   - 这样"晚到者"（如用户点 RunTicker 跳 /analyze?run_id=xxx，而 workflow
        #     已经结束）也能通过 LRANGE 拉到历史事件，重建运行状态
        if self._redis is not None:
            try:
                payload = json.dumps(
                    {"type": event.event_type, "data": event.data},
                    ensure_ascii=False,
                    default=str,
                )
                pipe = self._redis.pipeline()
                pipe.publish(_redis_channel_name(self.run_id), payload)
                pipe.rpush(_redis_history_key(self.run_id), payload)
                pipe.expire(_redis_history_key(self.run_id), _HISTORY_TTL_SECONDS)
                await pipe.execute()
            except Exception as e:
                logger.warning(f"[ProgressChannel] redis publish failed run_id={self.run_id}: {e}")

        logger.debug(
            f"[ProgressChannel] emit run_id={self.run_id} "
            f"event={event_type} data_keys={list(data.keys())}"
        )

    async def subscribe(self) -> AsyncGenerator[ProgressEvent, None]:
        """
        订阅进度事件流。

        用于 SSE 端点:
            async for event in channel.subscribe():
                yield event.to_sse()
        """
        q: asyncio.Queue[Optional[ProgressEvent]] = asyncio.Queue(maxsize=100)
        self._subscribers.append(q)
        try:
            while True:
                event = await q.get()
                if event is None:
                    break  # 通道已关闭
                yield event
        finally:
            self._subscribers.remove(q)

    async def close(self) -> None:
        """关闭通道，通知所有订阅者"""
        self._closed = True
        for q in self._subscribers:
            try:
                q.put_nowait(None)  # sentinel
            except asyncio.QueueFull:
                pass
        logger.debug(f"[ProgressChannel] closed run_id={self.run_id}")


# ── ProgressManager: 管理所有活跃通道 ─────────────────────────────

class ProgressManager:
    """
    全局 ProgressChannel 管理器。

    用法:
        manager = ProgressManager()

        # Workflow 启动时创建通道
        channel = manager.create_channel("run_001")

        # SSE 端点获取通道
        channel = manager.get_channel("run_001")
        async for event in channel.subscribe():
            yield event.to_sse()

        # Workflow 结束时清理
        manager.remove_channel("run_001")
    """

    def __init__(self, redis_client: Any = None):
        self._channels: Dict[str, ProgressChannel] = {}
        self._redis = redis_client

    def set_redis(self, redis_client: Any) -> None:
        """注入 redis 客户端（在 lifespan 启动后调用一次）。

        对已存在的 channel 也回填 redis，避免启动期 channel 抢在注入前创建的情况。
        """
        self._redis = redis_client
        for ch in self._channels.values():
            if ch._redis is None:
                ch._redis = redis_client
        logger.info(
            f"[ProgressManager] redis injected; active_channels={len(self._channels)}"
        )

    @property
    def redis(self) -> Any:
        return self._redis

    def create_channel(self, run_id: str) -> ProgressChannel:
        """创建一个新的进度通道"""
        if run_id in self._channels:
            logger.warning(f"[ProgressManager] channel already exists: {run_id}, reusing")
            return self._channels[run_id]
        channel = ProgressChannel(run_id, redis_client=self._redis)
        self._channels[run_id] = channel
        logger.info(f"[ProgressManager] created channel: {run_id}")
        return channel

    def get_channel(self, run_id: str) -> Optional[ProgressChannel]:
        """获取已有的进度通道"""
        return self._channels.get(run_id)

    async def remove_channel(self, run_id: str) -> None:
        """关闭并移除通道"""
        channel = self._channels.pop(run_id, None)
        if channel:
            await channel.close()
            logger.info(f"[ProgressManager] removed channel: {run_id}")

    @property
    def active_count(self) -> int:
        return len(self._channels)


# ── ServiceProtocol 集成回调 ──────────────────────────────────────

def make_progress_callback(channel: ProgressChannel):
    """
    创建一个 progress_callback 供 ServiceProtocol 使用。

    用法:
        channel = progress_manager.create_channel(run_id)
        service_protocol.progress_callback = make_progress_callback(channel)
    """
    async def callback(event_type: str, step_name: str, data: dict) -> None:
        await channel.emit(event_type, data)
    return callback


# ── Redis 订阅生成器（跨 worker fallback） ─────────────────────────

async def subscribe_via_redis(
    redis: Any,
    run_id: str,
    disconnected_checker: Optional[Any] = None,
    terminal_events: tuple = ("final", "error"),
    replay_history: bool = True,
) -> AsyncGenerator[ProgressEvent, None]:
    """订阅 Redis `progress:{run_id}` 频道并逐条产出 ProgressEvent。

    用于 SSE 端点在本地 channel 不存在时的 fallback 路径，使多 worker 部署下
    创建 channel 的 worker 与订阅 SSE 的 worker 不同也能拿到事件。

    Fix B（历史回放）:
        - `replay_history=True` 时，在订阅 pubsub 前先从
          `progress:{run_id}:history` List 拉取所有已发生的事件并逐条 yield
        - 这解决了"晚到者"（订阅时机晚于 workflow 结束）拿不到任何事件的问题
        - 若历史里已含 terminal event（final/error），直接结束，不再订阅 pubsub
        - 执行顺序：先 subscribe 再 lrange，保证 lrange 期间 publish 的新事件不丢
          （即便重复，前端 useWorkflowStream 是幂等的）

    Args:
        redis                : redis.asyncio.Redis 实例
        run_id               : run id
        disconnected_checker : 可选的异步可调用对象，返回 True 时优雅关闭（常用: request.is_disconnected）
        terminal_events      : 收到任一事件类型后自动结束订阅
        replay_history       : 是否在订阅前回放历史事件，默认 True

    Yields:
        ProgressEvent
    """
    if redis is None:
        return
    pubsub = redis.pubsub()
    channel_name = _redis_channel_name(run_id)
    history_key = _redis_history_key(run_id)
    try:
        # 1) 先订阅 pubsub（防止在 LRANGE 期间 publish 到来的新事件丢失）
        await pubsub.subscribe(channel_name)
        logger.info(f"[SSE/redis-sub] subscribed run_id={run_id}")

        # 2) 回放历史事件（可选）
        if replay_history:
            try:
                history = await redis.lrange(history_key, 0, -1)
            except Exception as e:
                logger.warning(
                    f"[SSE/redis-sub] history lrange failed run_id={run_id}: {e}"
                )
                history = []

            terminal_in_history = False
            for raw in history:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")
                try:
                    body = json.loads(raw)
                except Exception:
                    continue
                ev_type = body.get("type")
                ev_data = body.get("data") or {}
                if not ev_type:
                    continue
                yield ProgressEvent(ev_type, ev_data)
                if ev_type in terminal_events:
                    terminal_in_history = True

            if terminal_in_history:
                logger.info(
                    f"[SSE/redis-sub] terminal in history ({len(history)} events), "
                    f"closing run_id={run_id}"
                )
                return

            logger.info(
                f"[SSE/redis-sub] history replayed ({len(history)} events), "
                f"now listening new messages run_id={run_id}"
            )

        # 3) 监听后续新消息
        # get_message 比 listen() 更可控（可设 timeout，便于 disconnect 检查）
        while True:
            if disconnected_checker is not None:
                try:
                    if await disconnected_checker():
                        logger.info(f"[SSE/redis-sub] client disconnected run_id={run_id}")
                        return
                except Exception:
                    # 检查函数异常不阻塞 SSE
                    pass

            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg is None:
                continue
            if msg.get("type") != "message":
                continue

            raw = msg.get("data")
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            try:
                body = json.loads(raw)
            except Exception as e:
                logger.warning(
                    f"[SSE/redis-sub] malformed payload run_id={run_id}: {e}; raw={raw[:200]!r}"
                )
                continue

            ev_type = body.get("type")
            ev_data = body.get("data") or {}
            if not ev_type:
                continue
            yield ProgressEvent(ev_type, ev_data)

            if ev_type in terminal_events:
                logger.info(
                    f"[SSE/redis-sub] terminal event '{ev_type}' run_id={run_id}, closing"
                )
                return
    finally:
        try:
            await pubsub.unsubscribe(channel_name)
        except Exception:
            pass
        try:
            await pubsub.close()
        except Exception:
            pass


# ── 全局单例 ──────────────────────────────────────────────────────

progress_manager = ProgressManager()
