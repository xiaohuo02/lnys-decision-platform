# -*- coding: utf-8 -*-
"""backend/database.py — SQLAlchemy MySQL + Redis 连接（含健康检查）

提供两套引擎：
  1. 同步引擎（pymysql）— 向后兼容非 async 路由，通过 get_db() 注入
  2. 异步引擎（asyncmy）— 高并发 async 路由，通过 get_async_db() 注入

连接池配置通过 settings.DB_POOL_SIZE / DB_MAX_OVERFLOW 统一管理。
"""
from typing import AsyncGenerator, Generator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
import redis.asyncio as aioredis
from fastapi.concurrency import run_in_threadpool
from loguru import logger

from backend.config import settings

# ── MySQL（同步）─────────────────────────────────────────────────────────────────
_engine = None
_SessionLocal = None
Base = declarative_base()


def _get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        try:
            _engine = create_engine(
                settings.DATABASE_URL,
                pool_size=settings.DB_POOL_SIZE,
                max_overflow=settings.DB_MAX_OVERFLOW,
                pool_pre_ping=True,
                pool_recycle=settings.DB_POOL_RECYCLE,
            )
            _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
            logger.debug(
                f"[db:sync] MySQL 同步引擎已创建: {settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME} "
                f"pool={settings.DB_POOL_SIZE}+{settings.DB_MAX_OVERFLOW}"
            )
        except Exception as e:
            logger.error(f"[db:sync] MySQL 引擎创建失败: {e}")
            raise
    return _engine


def SessionLocal():
    """公开工厂：供后台任务等非 Depends 场景创建 Session"""
    _get_engine()
    return _SessionLocal()


def get_db() -> Generator:
    """FastAPI Depends：提供同步 Session（向后兼容非 async 路由）"""
    _get_engine()
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── MySQL（异步 — asyncmy 驱动）───────────────────────────────────────────────
_async_engine: Optional[AsyncEngine] = None
_async_session_factory: Optional[async_sessionmaker] = None


def _get_async_engine() -> AsyncEngine:
    """Lazy-init 异步引擎（asyncmy 驱动，每个 Worker 独立连接池）"""
    global _async_engine, _async_session_factory
    if _async_engine is None:
        _async_engine = create_async_engine(
            settings.ASYNC_DATABASE_URL,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_pre_ping=True,
            pool_recycle=settings.DB_POOL_RECYCLE,
        )
        _async_session_factory = async_sessionmaker(
            _async_engine,
            expire_on_commit=False,
            autoflush=False,
            class_=AsyncSession,
        )
        logger.debug(
            f"[db:async] MySQL 异步引擎已创建 (asyncmy): {settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME} "
            f"pool={settings.DB_POOL_SIZE}+{settings.DB_MAX_OVERFLOW}"
        )
    return _async_engine


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Depends：提供异步 AsyncSession（用于高并发 async 路由）"""
    _get_async_engine()
    assert _async_session_factory is not None
    async with _async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


def get_async_session_factory() -> async_sessionmaker:
    """公开工厂：供后台任务等非 Depends 场景创建 AsyncSession"""
    _get_async_engine()
    assert _async_session_factory is not None
    return _async_session_factory


async def close_async_engine() -> None:
    """Lifespan shutdown 时关闭异步引擎"""
    global _async_engine, _async_session_factory
    if _async_engine is not None:
        await _async_engine.dispose()
        _async_engine = None
        _async_session_factory = None
        logger.info("[db:async] MySQL 异步引擎已关闭")


def _sync_check_db() -> str:
    """同步探测 MySQL（在线程池中执行）"""
    engine = _get_engine()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return "ok"


async def check_db_health() -> str:
    """探测 MySQL 可用性，返回 'ok' 或错误描述（不抛异常）"""
    try:
        return await run_in_threadpool(_sync_check_db)
    except Exception as e:
        logger.warning(f"[db:health] MySQL 不可达: {e}")
        return f"error: {e}"


# ── Redis ──────────────────────────────────────────────────────────────────
_redis_client: Optional[aioredis.Redis] = None


def _build_redis() -> aioredis.Redis:
    return aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
    )


async def get_redis() -> aioredis.Redis:
    """获取全局 Redis 客户端（懒初始化，首次调用创建）"""
    global _redis_client
    if _redis_client is None:
        _redis_client = _build_redis()
        logger.debug(f"[redis] 客户端已创建: {settings.REDIS_HOST}:{settings.REDIS_PORT}")
    return _redis_client


async def close_redis() -> None:
    """关闭 Redis 连接（lifespan shutdown 调用）"""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("[redis] 连接已关闭")


async def check_redis_health() -> str:
    """探测 Redis 可用性，返回 'ok' 或错误描述（不抛异常）"""
    try:
        client = await get_redis()
        await client.ping()
        return "ok"
    except Exception as e:
        logger.warning(f"[redis:health] Redis 不可达: {e}")
        return f"error: {e}"


# ── PostgreSQL（通过 checkpoint 连接池）──────────────────────────────────
async def check_pg_health() -> str:
    """探测 PostgreSQL 可用性，返回 'ok' 或错误描述（不抛异常）"""
    try:
        from backend.agents.checkpoint import _get_pool, _DEPS_AVAILABLE
        if not _DEPS_AVAILABLE:
            return "未安装"
        pool = await _get_pool()
        async with pool.connection() as conn:
            await conn.execute("SELECT 1")
        return "ok"
    except Exception as e:
        logger.warning(f"[pg:health] PostgreSQL 不可达: {e}")
        return f"error: {e}"
