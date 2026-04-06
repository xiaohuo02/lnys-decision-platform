# -*- coding: utf-8 -*-
"""backend/schemas/base.py — 统一响应 Schema（全局唯一定义）

所有路由的 response_model 均应基于此处的 ApiResponse / PaginatedResponse。
"""
from typing import Any, Generic, List, Optional, TypeVar
from pydantic import BaseModel, Field


T = TypeVar("T")


# ── 元信息 ──────────────────────────────────────────────────
class MetaInfo(BaseModel):
    degraded: bool = False
    source:   str  = "db"
    trace_id: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)


# ── 统一响应格式 ────────────────────────────────────────────
class ApiResponse(BaseModel, Generic[T]):
    """统一业务接口返回格式 {code, data, message, meta}。

    用法示例::

        @router.get("/items", response_model=ApiResponse[List[ItemOut]])
        @router.get("/detail", response_model=ApiResponse[ItemOut])
    """
    code:    int = 200
    message: str = "ok"
    data:    Optional[T] = None
    meta:    Optional[MetaInfo] = None


# ── 分页列表内层结构 ────────────────────────────────────────
class PaginatedData(BaseModel, Generic[T]):
    """分页型列表统一内层结构，嵌入 ApiResponse.data 中。

    示例::

        response_model=ApiResponse[PaginatedData[RFMRecord]]
    """
    items:     List[T] = Field(default_factory=list)
    total:     int     = 0
    page:      int     = 1
    page_size: int     = 20
