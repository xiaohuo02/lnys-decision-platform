# -*- coding: utf-8 -*-
"""backend/routers/internal/services.py

内部 Service 调试路由
供开发联调、回归验证、后台运维触发使用。
workflow/agent 在模块化单体内直接调用 backend/services/*，不经过此路由。
"""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["internal-services"])


# ══════════════════════════════════════════════════════════════
#  POST /internal/data/prepare
# ══════════════════════════════════════════════════════════════
class DataPrepBody(BaseModel):
    sources:  Optional[List[str]] = None
    nrows:    Optional[int] = 500
    run_id:   Optional[str] = None

@router.post("/data/prepare")
def debug_data_prepare(body: DataPrepBody):
    from backend.services.data_preparation_service import (
        data_preparation_service, DataPrepRequest, DataSource,
    )
    sources = [DataSource(s) for s in body.sources] if body.sources else None
    req = DataPrepRequest(
        sources=sources or [DataSource.ORDERS, DataSource.CUSTOMERS],
        nrows=body.nrows,
        run_id=body.run_id,
    )
    result = data_preparation_service.prepare(req)
    return result.model_dump()


# ══════════════════════════════════════════════════════════════
#  POST /internal/customer/intelligence
# ══════════════════════════════════════════════════════════════
class CustomerIntelBody(BaseModel):
    analysis_types: Optional[List[str]] = None
    top_n:          int = 5
    run_id:         Optional[str] = None

@router.post("/customer/intelligence")
def debug_customer_intel(body: CustomerIntelBody):
    from backend.services.customer_intelligence_service import (
        customer_intelligence_service, CustomerIntelRequest,
    )
    req = CustomerIntelRequest(
        analysis_types=body.analysis_types or ["rfm", "churn", "clv"],
        top_n=body.top_n,
        run_id=body.run_id,
    )
    return customer_intelligence_service.analyze(req).model_dump()


# ══════════════════════════════════════════════════════════════
#  POST /internal/forecast/run
# ══════════════════════════════════════════════════════════════
class ForecastBody(BaseModel):
    forecast_days:   int = 30
    compare_models:  bool = True
    run_id:          Optional[str] = None

@router.post("/forecast/run")
def debug_forecast(body: ForecastBody):
    from backend.services.sales_forecast_service import (
        sales_forecast_service, ForecastRequest,
    )
    req = ForecastRequest(
        forecast_days=body.forecast_days,
        compare_models=body.compare_models,
        run_id=body.run_id,
    )
    return sales_forecast_service.forecast(req).model_dump()


# ══════════════════════════════════════════════════════════════
#  POST /internal/fraud/score
# ══════════════════════════════════════════════════════════════
class FraudScoreBody(BaseModel):
    features:       Dict[str, Any] = {}
    transaction_id: Optional[str] = None
    run_id:         Optional[str] = None

@router.post("/fraud/score")
def debug_fraud_score(body: FraudScoreBody):
    from backend.services.fraud_scoring_service import (
        fraud_scoring_service, FraudScoringRequest,
    )
    req = FraudScoringRequest(
        transaction_id=body.transaction_id,
        features=body.features,
        run_id=body.run_id,
    )
    return fraud_scoring_service.score(req).model_dump()


# ══════════════════════════════════════════════════════════════
#  POST /internal/sentiment/analyze
# ══════════════════════════════════════════════════════════════
class SentimentBody(BaseModel):
    negative_threshold: float = 0.3
    top_n_themes:       int = 5
    nrows:              Optional[int] = None
    run_id:             Optional[str] = None

@router.post("/sentiment/analyze")
def debug_sentiment(body: SentimentBody):
    from backend.services.sentiment_intelligence_service import (
        sentiment_intelligence_service, SentimentRequest,
    )
    req = SentimentRequest(
        negative_threshold=body.negative_threshold,
        top_n_themes=body.top_n_themes,
        nrows=body.nrows,
        run_id=body.run_id,
    )
    return sentiment_intelligence_service.analyze(req).model_dump()


# ══════════════════════════════════════════════════════════════
#  POST /internal/inventory/optimize
# ══════════════════════════════════════════════════════════════
class InventoryBody(BaseModel):
    store_id:    Optional[str] = None
    lead_time:   float = 7.0
    run_id:      Optional[str] = None

@router.post("/inventory/optimize")
def debug_inventory(body: InventoryBody):
    from backend.services.inventory_optimization_service import (
        inventory_optimization_service, InventoryRequest,
    )
    req = InventoryRequest(
        store_id=body.store_id,
        lead_time_days=body.lead_time,
        run_id=body.run_id,
    )
    return inventory_optimization_service.optimize(req).model_dump()


# ══════════════════════════════════════════════════════════════
#  POST /internal/association/mine
# ══════════════════════════════════════════════════════════════
class AssocBody(BaseModel):
    sku_codes: Optional[List[str]] = None
    top_n:     int = 10
    min_lift:  float = 1.2
    run_id:    Optional[str] = None

@router.post("/association/mine")
def debug_association(body: AssocBody):
    from backend.services.association_mining_service import (
        association_mining_service, AssociationRequest,
    )
    req = AssociationRequest(
        sku_codes=body.sku_codes,
        top_n=body.top_n,
        min_lift=body.min_lift,
        run_id=body.run_id,
    )
    return association_mining_service.query(req).model_dump()


# ══════════════════════════════════════════════════════════════
#  POST /internal/report/render
# ══════════════════════════════════════════════════════════════
class ReportBody(BaseModel):
    executive_summary: Optional[str] = None
    risk_highlights:   Optional[str] = None
    action_plan:       Optional[str] = None
    report_type:       str = "business_overview"
    format:            str = "markdown"
    run_id:            Optional[str] = None

@router.post("/report/render")
def debug_report_render(body: ReportBody):
    from backend.services.report_rendering_service import (
        report_rendering_service, ReportRenderRequest,
    )
    req = ReportRenderRequest(
        run_id=body.run_id,
        report_type=body.report_type,
        requested_format=body.format,
        executive_summary=body.executive_summary,
        risk_highlights=body.risk_highlights,
        action_plan=body.action_plan,
    )
    result = report_rendering_service.render(req)
    return {
        "data_ready":      result.data_ready,
        "partial":         result.partial,
        "word_count":      result.word_count,
        "artifact_uri":    result.artifact_uri,
        "artifact_uris":   result.artifact_uris,
        "report_markdown": result.report_markdown[:500] + "..." if len(result.report_markdown) > 500 else result.report_markdown,
    }
