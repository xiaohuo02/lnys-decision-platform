# -*- coding: utf-8 -*-
"""backend/agents/checkpoint.py

PostgreSQL Checkpointer 管理模块
- 异步连接池初始化
- 首次使用自动调用 .setup() 建表
- 对外暴露 get_checkpointer() 上下文管理器
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from loguru import logger

# ── 延迟导入，避免未安装依赖时整个后端崩溃 ──────────────────────

try:
    from psycopg_pool import AsyncConnectionPool
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    _DEPS_AVAILABLE = True
except ImportError:
    _DEPS_AVAILABLE = False
    AsyncConnectionPool = None      # type: ignore
    AsyncPostgresSaver  = None      # type: ignore

from backend.config import settings

# ── 连接池单例 ──────────────────────────────────────────────────────

_pool: Optional["AsyncConnectionPool"] = None  # type: ignore
_setup_done = False
_lock = asyncio.Lock()


async def _get_pool() -> "AsyncConnectionPool":  # type: ignore
    """懒初始化连接池（应用层只用一个池）"""
    global _pool
    if _pool is None:
        if not _DEPS_AVAILABLE:
            raise RuntimeError(
                "langgraph-checkpoint-postgres / psycopg-pool 未安装。"
                "请运行: pip install langgraph-checkpoint-postgres psycopg[binary] psycopg-pool"
            )
        _pool = AsyncConnectionPool(
            conninfo=settings.POSTGRES_CHECKPOINT_URL,
            max_size=10,
            kwargs={"autocommit": True, "prepare_threshold": 0},
            open=False,
        )
        await _pool.open()
        logger.info("[checkpoint] PostgreSQL connection pool opened")
    return _pool


async def setup_checkpointer() -> None:
    """
    在应用启动时调用一次，确保 LangGraph checkpoint 表存在。
    幂等操作，多次调用安全。
    复用连接池而非每次新建独立连接。
    """
    global _setup_done
    async with _lock:
        if _setup_done:
            return
        if not _DEPS_AVAILABLE:
            logger.warning("[checkpoint] langgraph-checkpoint-postgres 未安装，跳过 setup")
            return
        try:
            pool = await _get_pool()
            saver = AsyncPostgresSaver(pool)
            await saver.setup()
            _setup_done = True
            logger.info("[checkpoint] LangGraph checkpoint tables ready (PostgreSQL)")
        except Exception as e:
            logger.error(f"[checkpoint] setup failed: {e}")
            raise


async def close_pool() -> None:
    """在应用关闭时调用，释放连接池"""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("[checkpoint] PostgreSQL connection pool closed")


@asynccontextmanager
async def get_checkpointer() -> AsyncIterator["AsyncPostgresSaver"]:  # type: ignore
    """
    异步上下文管理器，提供一个可用的 AsyncPostgresSaver 实例。
    复用全局连接池，不再每次 from_conn_string 新建独立连接。
    用法：
        async with get_checkpointer() as checkpointer:
            graph = build_graph(checkpointer=checkpointer)
            await graph.ainvoke(...)
    """
    if not _DEPS_AVAILABLE:
        raise RuntimeError("langgraph-checkpoint-postgres 未安装")
    pool = await _get_pool()
    yield AsyncPostgresSaver(pool)
