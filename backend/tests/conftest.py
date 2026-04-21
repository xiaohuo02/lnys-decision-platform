# -*- coding: utf-8 -*-
"""backend/tests/conftest.py — 全局 pytest fixtures"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from backend.main import create_app


@pytest.fixture(scope="session")
def app():
    """创建测试用 FastAPI 实例（不启动 lifespan）"""
    return create_app()


@pytest.fixture(scope="session")
def client(app):
    """同步测试客户端，适合 router 集成测试"""
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.get    = AsyncMock(return_value=None)
    redis.setex  = AsyncMock(return_value=True)
    redis.lpush  = AsyncMock(return_value=1)
    redis.lrange = AsyncMock(return_value=[])
    redis.ltrim  = AsyncMock(return_value=True)
    redis.expire = AsyncMock(return_value=True)
    redis.ping   = AsyncMock(return_value=True)
    return redis


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute = MagicMock(return_value=MagicMock(fetchall=lambda: [], fetchone=lambda: None))
    db.commit  = MagicMock()
    db.rollback = MagicMock()
    return db
