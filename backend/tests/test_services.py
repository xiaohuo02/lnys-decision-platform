# -*- coding: utf-8 -*-
"""backend/tests/test_services.py — Service 单元测试（不依赖真实 DB/Redis）"""
import pytest
from unittest.mock import AsyncMock, patch

from backend.config import settings
from backend.services.customer_service import CustomerService
from backend.services.forecast_service import ForecastService
from backend.services.fraud_service import FraudService
from backend.services.chat_service import ChatService
from backend.schemas.customer_schemas import ChurnPredictRequest
from backend.schemas.forecast_schemas import ForecastPredictRequest
from backend.schemas.fraud_schemas import FraudScoreRequest
from backend.schemas.chat_schemas import ChatMessageRequest


# ── CustomerService ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_customer_get_rfm_mock(mock_db, mock_redis):
    """无 CSV 时应返回 mock 数据（ENABLE_MOCK_DATA=True）"""
    svc = CustomerService(mock_db, mock_redis, agent=None)
    with patch.object(settings, "ENABLE_MOCK_DATA", True):
        result = await svc.get_rfm()
    assert result["code"] == 200
    assert "data" in result


@pytest.mark.asyncio
async def test_customer_predict_churn_cache_miss(mock_db, mock_redis):
    """缓存未命中且 agent 不可用时，应返回 degraded mock 结果"""
    mock_redis.get = AsyncMock(return_value=None)
    svc    = CustomerService(mock_db, mock_redis, agent=None)
    body   = ChurnPredictRequest(
        customer_id="LY000001", recency=30, frequency_30d=3, frequency_90d=8,
        monetary_trend=-0.1, return_rate=0.05, complaint_count=1,
        member_level="银卡", register_days=365, social_interaction=2,
    )
    with patch.object(settings, "ENABLE_MOCK_DATA", True):
        result = await svc.predict_churn(body)
    assert result["code"] == 200
    assert "churn_probability" in result["data"]
    assert result["meta"]["degraded"] is True


# ── ForecastService ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_forecast_summary_mock(mock_db, mock_redis):
    svc    = ForecastService(mock_db, mock_redis, agent=None)
    with patch.object(settings, "ENABLE_MOCK_DATA", True):
        result = await svc.get_summary()
    assert result["code"] == 200
    assert "mape_stacking" in result["data"]


@pytest.mark.asyncio
async def test_forecast_predict_cache_hit(mock_db, mock_redis):
    import json
    cached_data = json.dumps({"sku_code": "LY-GR-001", "forecast": []})
    mock_redis.get = AsyncMock(return_value=cached_data)
    svc  = ForecastService(mock_db, mock_redis, agent=None)
    body = ForecastPredictRequest(sku_code="LY-GR-001", store_id="NDE-001", days=7)
    result = await svc.predict(body)
    assert result["message"] == "ok (cached)"
    mock_redis.setex.assert_not_called()


# ── FraudService ──────────────────────────────────────────────────────────

def test_fraud_rule_engine_high_risk():
    """凌晨 + 跨省 + 超大额应触发高风险"""
    body = FraudScoreRequest(
        transaction_id="TX001", customer_id="LY000001",
        amount=6000.0, hour_of_day=2,
        province="广东", ip_province="北京", same_device_1h_count=1,
        is_new_account=False,
    )
    result = FraudService._rule_engine(body)
    assert result["risk_level"] == "高"
    assert result["hitl_required"] is True
    assert len(result["rules_triggered"]) >= 2


def test_fraud_rule_engine_low_risk():
    body = FraudScoreRequest(
        transaction_id="TX002", customer_id="LY000002",
        amount=200.0, hour_of_day=14,
        province="广东", ip_province="广东", same_device_1h_count=1,
        is_new_account=False,
    )
    result = FraudService._rule_engine(body)
    assert result["risk_level"] == "低"
    assert result["hitl_required"] is False


# ── ChatService ────────────────────────────────────────────────────────────

def test_chat_fallback_known_intent():
    result = ChatService._fallback_reply("我的订单什么时候发货", 0)
    assert result["intent"] in ("查订单",)
    assert result["confidence"] > 0.5


def test_chat_fallback_unknown():
    result = ChatService._fallback_reply("随便聊聊天", 0)
    assert result["handoff"] is True
    assert result["confidence"] < 0.5
