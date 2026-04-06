# -*- coding: utf-8 -*-
"""backend/models/business.py — 业务域 ORM Model

对应 init.sql 中 skus / stores / customers / orders /
analysis_results / fraud_records / chat_messages / inventory_snapshots。
"""
from sqlalchemy import (
    Column, String, Text, Integer, BigInteger, Boolean,
    Date, DateTime, Numeric, Enum as SAEnum, Index, func,
)

from backend.database import Base


class Sku(Base):
    __tablename__ = "skus"

    sku_code = Column(String(20), primary_key=True, comment="SKU编码，如 LY-GR-001")
    name = Column(String(100), nullable=False, comment="商品名称")
    category = Column(String(50), nullable=False, comment="品类")
    unit_price = Column(Numeric(10, 2), nullable=False, comment="零售单价（元）")
    season_tag = Column(String(20), default=None, comment="季节标签")


class Store(Base):
    __tablename__ = "stores"

    store_id = Column(String(10), primary_key=True, comment="门店编号，如 NDE-001")
    name = Column(String(100), nullable=False)
    city = Column(String(50), nullable=False)
    province = Column(String(50), nullable=False)
    tier = Column(String(10), nullable=False, comment="一线/二线/三线")


class Customer(Base):
    __tablename__ = "customers"

    customer_id = Column(String(20), primary_key=True, comment="客户ID，如 LY000001")
    name = Column(String(100), default=None)
    phone = Column(String(20), default=None)
    city = Column(String(50), default=None)
    province = Column(String(50), default=None)
    member_level = Column(
        SAEnum("普通", "银卡", "金卡", "钻石", name="member_level_enum"),
        default="普通",
    )
    register_date = Column(Date, default=None)
    channel = Column(
        SAEnum("online", "offline", "both", name="channel_enum"),
        default="online",
    )

    __table_args__ = (
        Index("idx_member", "member_level"),
        Index("idx_city", "city"),
    )


class Order(Base):
    __tablename__ = "orders"

    order_id = Column(String(30), primary_key=True)
    customer_id = Column(String(20), nullable=False)
    sku_code = Column(String(20), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    total_amount = Column(Numeric(12, 2), nullable=False)
    channel = Column(
        SAEnum("online", "offline", name="order_channel_enum"),
        default="online",
    )
    store_id = Column(String(10), default=None, comment="线下门店ID")
    ship_city = Column(String(50), default=None)
    payment_method = Column(String(20), default=None)
    order_date = Column(DateTime, nullable=False)

    __table_args__ = (
        Index("idx_customer", "customer_id"),
        Index("idx_date", "order_date"),
        Index("idx_sku", "sku_code"),
    )


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    module = Column(String(50), nullable=False, comment="模块名：customer/forecast/fraud/...")
    result_json = Column(Text, nullable=False, comment="Agent 输出 JSON")
    generated_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_module", "module"),
        Index("idx_time", "generated_at"),
    )


class FraudRecord(Base):
    __tablename__ = "fraud_records"

    transaction_id = Column(String(40), primary_key=True)
    risk_score = Column(Numeric(5, 4), nullable=False)
    risk_level = Column(
        SAEnum("低风险", "中风险", "高风险", name="risk_level_enum"),
        nullable=False,
    )
    rule_triggered = Column(Boolean, default=False)
    detected_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_level", "risk_level"),
        Index("idx_fraud_time", "detected_at"),
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(String(64), nullable=False)
    role = Column(SAEnum("user", "bot", name="chat_role_enum"), nullable=False)
    content = Column(Text, nullable=False)
    intent = Column(String(50), default=None)
    confidence = Column(Numeric(5, 4), default=None)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_session", "session_id"),
        Index("idx_chat_time", "created_at"),
    )


class InventorySnapshot(Base):
    __tablename__ = "inventory_snapshots"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    sku_code = Column(String(20), nullable=False)
    store_id = Column(String(10), nullable=False)
    stock_qty = Column(Integer, nullable=False, default=0)
    reorder_point = Column(Integer, default=None)
    date = Column(Date, nullable=False)

    __table_args__ = (
        Index("idx_sku_store", "sku_code", "store_id"),
        Index("idx_inv_date", "date"),
    )
