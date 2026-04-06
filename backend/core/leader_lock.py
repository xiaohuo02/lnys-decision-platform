# -*- coding: utf-8 -*-
"""backend/core/leader_lock.py — 通用 Redis Leader 选举锁

用于确保多 worker / 多实例部署中，单例组件（FeishuBridge、PatrolScheduler 等）
在集群里**至多一个实例**运行。

设计要点（最佳实践）:
  1. 安全默认: Redis 不可用 / acquire 失败 → 返回 False（宁缺勿多，避免重复启动）
  2. 原子续期: 使用 Lua 脚本做 compare-and-expire，避免续到别人的锁
  3. 原子释放: 使用 Lua 脚本做 compare-and-delete，不会误删他人锁
  4. 自愿放弃: 续期失败（key 消失/被他人占用）立即放弃 leader 身份，
               不再重新抢占，由下一次 lifespan 重启决定
  5. 身份标识: 每次 acquire 生成 instance_id 写入 value，用于 Lua 脚本比对

典型用法:

    from backend.core.leader_lock import LeaderLock

    lock = LeaderLock(redis, key="lnys:feishu_leader", ttl_seconds=60)
    if await lock.acquire():
        await lock.start_renewal()
        try:
            # 启动 leader 专属组件（FeishuBridge / PatrolScheduler / ...）
            ...
        finally:
            await lock.release()
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any, Optional

from loguru import logger


# ── Lua 脚本：保证续期和释放的原子性 ────────────────────────────────

# 若 key 值等于 ARGV[1]，则 EXPIRE 为 ARGV[2] 秒，返回 1；否则返回 0
_LUA_RENEW = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('EXPIRE', KEYS[1], ARGV[2])
else
    return 0
end
"""

# 若 key 值等于 ARGV[1]，则 DEL，返回 1；否则返回 0
_LUA_RELEASE = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
else
    return 0
end
"""


class LeaderLock:
    """单 leader 分布式锁（Redis 实现）。"""

    def __init__(
        self,
        redis: Any,
        key: str,
        ttl_seconds: int = 60,
        renew_interval_seconds: Optional[int] = None,
    ) -> None:
        """
        Args:
            redis:                    redis.asyncio.Redis 客户端；若为 None 则永远视为非 leader
            key:                      Redis 锁 key
            ttl_seconds:              锁过期时间（秒），超过此时间未续期则自动失效
            renew_interval_seconds:   续期间隔。默认为 ttl/3，必须 < ttl
        """
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._redis = redis
        self._key = key
        self._ttl = ttl_seconds
        self._renew_interval = renew_interval_seconds or max(ttl_seconds // 3, 1)
        if self._renew_interval >= self._ttl:
            raise ValueError("renew_interval must be less than ttl")

        self._instance_id = uuid.uuid4().hex[:12]
        self._is_leader = False
        self._renew_task: Optional[asyncio.Task] = None

    # ── 查询 ──────────────────────────────────────────────────────

    @property
    def is_leader(self) -> bool:
        return self._is_leader

    @property
    def instance_id(self) -> str:
        return self._instance_id

    # ── 核心 API ──────────────────────────────────────────────────

    async def acquire(self) -> bool:
        """尝试获取 leader 锁。

        Returns:
            True  — 本实例成为 leader
            False — 未获取（Redis 故障 / 已被他人持有），应视为非 leader
        """
        if self._redis is None:
            logger.warning(
                f"[LeaderLock:{self._key}] Redis 不可用，作为非 leader 默认 (safe)"
            )
            return False

        try:
            acquired = await self._redis.set(
                self._key, self._instance_id, nx=True, ex=self._ttl,
            )
            if acquired:
                self._is_leader = True
                logger.info(
                    f"[LeaderLock:{self._key}] acquired "
                    f"instance={self._instance_id} ttl={self._ttl}s"
                )
                return True
            logger.info(f"[LeaderLock:{self._key}] held by another instance")
            return False
        except Exception as e:
            logger.warning(
                f"[LeaderLock:{self._key}] acquire failed (non-leader default): {e}"
            )
            return False

    async def start_renewal(self) -> None:
        """启动后台心跳续期任务。幂等调用安全。"""
        if not self._is_leader:
            return
        if self._renew_task is not None and not self._renew_task.done():
            return
        self._renew_task = asyncio.create_task(
            self._renew_loop(),
            name=f"leader-lock-renew:{self._key}",
        )
        logger.info(
            f"[LeaderLock:{self._key}] renewal started interval={self._renew_interval}s"
        )

    async def release(self) -> None:
        """释放 leader 锁：停止心跳 + 原子删除 Redis key。幂等调用安全。"""
        # 停止心跳
        if self._renew_task is not None:
            self._renew_task.cancel()
            try:
                await self._renew_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.debug(f"[LeaderLock:{self._key}] renewal task exited: {e}")
            self._renew_task = None

        # 原子删除 key（compare-and-delete）
        if self._is_leader and self._redis is not None:
            try:
                result = await self._redis.eval(
                    _LUA_RELEASE, 1, self._key, self._instance_id,
                )
                if int(result or 0) == 1:
                    logger.info(f"[LeaderLock:{self._key}] released")
                else:
                    logger.debug(
                        f"[LeaderLock:{self._key}] key not owned by this instance, skip delete"
                    )
            except Exception as e:
                logger.warning(f"[LeaderLock:{self._key}] release error: {e}")

        self._is_leader = False

    # ── 内部 ──────────────────────────────────────────────────────

    async def _renew_loop(self) -> None:
        """周期性续期任务。任一次续期失败（key 丢失/被抢）即放弃 leader。"""
        try:
            while self._is_leader:
                await asyncio.sleep(self._renew_interval)
                if not self._is_leader:
                    break
                try:
                    renewed = await self._redis.eval(
                        _LUA_RENEW, 1, self._key, self._instance_id, str(self._ttl),
                    )
                    if int(renewed or 0) != 1:
                        logger.warning(
                            f"[LeaderLock:{self._key}] leadership lost "
                            f"(renewal returned 0), stopping"
                        )
                        self._is_leader = False
                        return
                    logger.debug(f"[LeaderLock:{self._key}] renewed")
                except Exception as e:
                    logger.warning(
                        f"[LeaderLock:{self._key}] renewal error: {e}，放弃 leader 身份"
                    )
                    self._is_leader = False
                    return
        except asyncio.CancelledError:
            logger.debug(f"[LeaderLock:{self._key}] renewal cancelled")
            raise
