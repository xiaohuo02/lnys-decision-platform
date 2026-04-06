# -*- coding: utf-8 -*-
"""backend/core/response.py — 统一响应结构工具函数

所有同步接口统一返回:
  {
    "code":    int,        # HTTP 语义状态码 (200/400/404/500/503)
    "data":    Any,        # 业务数据
    "message": str,        # 人可读消息
    "meta": {              # 可选元信息（前端可据此判断数据来源/降级/追踪）
      "degraded": bool,    # 是否降级返回
      "source":   str,     # 数据来源: "db" / "cache" / "csv" / "mock" / "agent"
      "trace_id": str|None # 可选追踪 ID
      "warnings": []       # 可选告警列表
    }
  }
"""
from typing import Any, Dict, List, Optional


def _build_meta(
    *,
    degraded: bool = False,
    source: str = "db",
    trace_id: Optional[str] = None,
    warnings: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "degraded": degraded,
        "source": source,
        "trace_id": trace_id,
        "warnings": warnings or [],
    }


def ok(
    data: Any = None,
    message: str = "ok",
    *,
    source: str = "db",
    trace_id: Optional[str] = None,
) -> dict:
    return {
        "code": 200,
        "data": data,
        "message": message,
        "meta": _build_meta(source=source, trace_id=trace_id),
    }


def cached(data: Any, *, trace_id: Optional[str] = None) -> dict:
    return {
        "code": 200,
        "data": data,
        "message": "ok (cached)",
        "meta": _build_meta(source="cache", trace_id=trace_id),
    }


def error(
    message: str,
    code: int = 500,
    data: Any = None,
    *,
    trace_id: Optional[str] = None,
) -> dict:
    return {
        "code": code,
        "data": data,
        "message": message,
        "meta": _build_meta(source="error", trace_id=trace_id),
    }


def not_ready(agent_name: str) -> dict:
    return {
        "code": 503,
        "data": None,
        "message": f"Agent '{agent_name}' 暂未就绪，模型文件尚未就位",
        "meta": _build_meta(source="error"),
    }


def degraded(
    data: Any,
    reason: str,
    *,
    source: str = "mock",
    trace_id: Optional[str] = None,
    warnings: Optional[List[str]] = None,
) -> dict:
    return {
        "code": 200,
        "data": data,
        "message": f"ok (degraded: {reason})",
        "meta": _build_meta(
            degraded=True,
            source=source,
            trace_id=trace_id,
            warnings=warnings or [reason],
        ),
    }
