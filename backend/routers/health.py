# -*- coding: utf-8 -*-
"""backend/routers/health.py — 健康检查（三类端点）

/api/health        综合检查，前端 Dashboard 和监控面板调用
/api/health/live   Liveness：进程是否存活（K8s / Docker HEALTHCHECK）
/api/health/ready  Readiness：Redis 就绪后才接收流量
/api/health/deps   Dependency：详细的每项依赖状态，排查用
"""
import time
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.config import settings
from backend.database import check_db_health, check_redis_health, check_pg_health

router = APIRouter(tags=["健康检查"])

_MODEL_CHECKS = [
    ("churn_xgb",  lambda: settings.ART_CUSTOMER / "churn_xgb.pkl"),
    ("fraud_lgb",  lambda: settings.ART_FRAUD    / "fraud_lgb.pkl"),
    ("iso_forest", lambda: settings.ART_FRAUD    / "iso_forest.pkl"),
    ("bert",       lambda: settings.ART_NLP      / "bert_sentiment"),
    ("lda",        lambda: settings.ART_NLP      / "lda_dict.pkl"),
    ("sarima",     lambda: settings.ART_FORECAST / "sarima.pkl"),
    ("stacking",   lambda: settings.ART_FORECAST / "stacking_weights.pkl"),
]


# ── 1. 综合检查（前端轮询）────────────────────────────────────────────
@router.get("/health", summary="综合健康检查")
async def health_check(request: Request):
    t0 = time.perf_counter()
    db_status = await check_db_health()
    db_ms = round((time.perf_counter() - t0) * 1000)

    t0 = time.perf_counter()
    redis_status = await check_redis_health()
    redis_ms = round((time.perf_counter() - t0) * 1000)

    t0 = time.perf_counter()
    pg_status = await check_pg_health()
    pg_ms = round((time.perf_counter() - t0) * 1000)

    models = {name: ("ok" if fn().exists() else "missing") for name, fn in _MODEL_CHECKS}
    agents = getattr(request.app.state, "agent_registry", {})

    all_ok   = db_status == "ok" and redis_status == "ok" and pg_status == "ok"
    overall  = "ok" if all_ok else "degraded"

    return {"code": 200, "data": {
        "status": overall,
        "env":    settings.ENV,
        "db":     db_status,
        "redis":  redis_status,
        "pg":     pg_status,
        "latency_ms": {"db": db_ms, "redis": redis_ms, "pg": pg_ms},
        "models": models,
        "agents": agents,
    }, "message": "ok", "meta": {
        "degraded": overall != "ok",
        "source":   "health_check",
        "trace_id": None,
        "warnings": [] if all_ok else [f"db={db_status}", f"redis={redis_status}"],
    }}


# ── 2. Liveness（进程存活）──────────────────────────────────────────
@router.get("/health/live", summary="Liveness 探针（进程存活）")
async def liveness():
    return {"code": 200, "data": {"alive": True}, "message": "ok"}


# ── 3. Readiness（就绪接收流量）────────────────────────────────────
@router.get("/health/ready", summary="Readiness 探针（Redis 就绪）")
async def readiness():
    redis_status = await check_redis_health()
    if redis_status != "ok":
        return JSONResponse(
            status_code=503,
            content={"code": 503, "data": {"redis": redis_status}, "message": "not ready"},
        )
    return {"code": 200, "data": {"ready": True}, "message": "ok"}


# ── 4. Dependency 详情（排查用）────────────────────────────────────
@router.get("/health/deps", summary="依赖详情（DB / Redis / 模型 / Agent）")
async def deps(request: Request):
    db_status    = await check_db_health()
    redis_status = await check_redis_health()
    models = {name: ("ok" if fn().exists() else "missing") for name, fn in _MODEL_CHECKS}
    agents = getattr(request.app.state, "agent_registry", {})
    return {"code": 200, "data": {
        "db":     db_status,
        "redis":  redis_status,
        "models": models,
        "agents": agents,
        "mock_data_enabled": settings.ENABLE_MOCK_DATA,
    }, "message": "ok"}
