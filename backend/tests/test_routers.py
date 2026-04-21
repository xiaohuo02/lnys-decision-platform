# -*- coding: utf-8 -*-
"""backend/tests/test_routers.py — Router 集成测试（使用 TestClient + mock 依赖）"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.dependencies.db import DbSession
from backend.dependencies.redis import RedisClient


def _make_client(mock_redis=None, mock_db=None):
    app = create_app()

    async def _fake_redis(request):
        return mock_redis or AsyncMock()

    def _fake_db():
        db = mock_db or MagicMock()
        try:
            yield db
        finally:
            pass

    from backend.database import get_db
    app.dependency_overrides[get_db] = _fake_db
    # Inject redis into app.state for the RedisClient dep
    if mock_redis:
        app.state.redis = mock_redis
    return TestClient(app, raise_server_exceptions=False)


# ── Health ────────────────────────────────────────────────────────────────

def test_health_liveness():
    client = _make_client()
    r = client.get("/api/health/live")
    assert r.status_code == 200
    assert r.json()["data"]["alive"] is True


def test_health_check_returns_200():
    with patch("backend.database.check_db_health", AsyncMock(return_value="ok")), \
         patch("backend.database.check_redis_health", AsyncMock(return_value="ok")):
        client = _make_client()
        r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["data"]["status"] in ("ok", "degraded")


# ── Customers ─────────────────────────────────────────────────────────────

def test_customers_rfm_mock():
    """无 CSV 时 /rfm 应返回 mock 数据"""
    with patch("backend.config.settings.ENABLE_MOCK_DATA", True):
        client = _make_client(mock_redis=AsyncMock())
        r = client.get("/api/customers/rfm")
    assert r.status_code == 200
    assert r.json()["code"] == 200


def test_customers_predict_churn():
    redis_mock = AsyncMock()
    redis_mock.get   = AsyncMock(return_value=None)
    redis_mock.setex = AsyncMock(return_value=True)
    client = _make_client(mock_redis=redis_mock)
    payload = {
        "customer_id": "LY000001", "recency": 30,
        "frequency_30d": 3, "frequency_90d": 8,
        "monetary_trend": -0.1, "return_rate": 0.05, "complaint_count": 1,
        "member_level": "银卡", "register_days": 365, "social_interaction": 2,
    }
    r = client.post("/api/customers/predict-churn", json=payload)
    assert r.status_code == 200
    assert r.json()["code"] == 200


# ── Fraud ─────────────────────────────────────────────────────────────────

def test_fraud_score_low_risk():
    redis_mock = AsyncMock()
    redis_mock.lpush = AsyncMock(return_value=1)
    client = _make_client(mock_redis=redis_mock)
    payload = {
        "transaction_id": "TX-TEST-001", "customer_id": "LY000001",
        "amount": 150.0, "hour_of_day": 14,
        "province": "广东", "ip_province": "广东",
        "same_device_1h_count": 1, "is_new_account": False,
    }
    r = client.post("/api/fraud/score", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["code"] == 200
    assert data["data"]["risk_level"] == "低"


def test_fraud_pending_reviews_empty():
    redis_mock = AsyncMock()
    client = _make_client(mock_redis=redis_mock)
    r = client.get("/api/fraud/pending-reviews")
    assert r.status_code == 200


# ── Chat ──────────────────────────────────────────────────────────────────

def test_chat_message_known_intent():
    redis_mock = AsyncMock()
    redis_mock.lrange = AsyncMock(return_value=[])
    redis_mock.lpush  = AsyncMock(return_value=1)
    redis_mock.ltrim  = AsyncMock(return_value=True)
    redis_mock.expire = AsyncMock(return_value=True)
    client = _make_client(mock_redis=redis_mock)
    payload = {
        "session_id": "sess-001", "message": "我的订单什么时候发货",
        "customer_id": "LY000001",
    }
    r = client.post("/api/chat/message", json=payload)
    assert r.status_code == 200
    assert r.json()["code"] == 200
