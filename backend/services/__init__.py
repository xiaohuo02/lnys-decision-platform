# -*- coding: utf-8 -*-
from loguru import logger as _logger

try:
    from backend.services.data_preparation_service import data_preparation_service
except Exception as _e:
    _logger.warning(f"[services] DataPreparationService 加载失败: {_e}"); data_preparation_service = None  # type: ignore

try:
    from backend.services.customer_intelligence_service import customer_intelligence_service
except Exception as _e:
    _logger.warning(f"[services] CustomerIntelligenceService 加载失败: {_e}"); customer_intelligence_service = None  # type: ignore

try:
    from backend.services.sales_forecast_service import sales_forecast_service
except Exception as _e:
    _logger.warning(f"[services] SalesForecastService 加载失败: {_e}"); sales_forecast_service = None  # type: ignore

try:
    from backend.services.fraud_scoring_service import fraud_scoring_service
except Exception as _e:
    _logger.warning(f"[services] FraudScoringService 加载失败: {_e}"); fraud_scoring_service = None  # type: ignore

try:
    from backend.services.sentiment_intelligence_service import sentiment_intelligence_service
except Exception as _e:
    _logger.warning(f"[services] SentimentIntelligenceService 加载失败: {_e}"); sentiment_intelligence_service = None  # type: ignore

try:
    from backend.services.inventory_optimization_service import inventory_optimization_service
except Exception as _e:
    _logger.warning(f"[services] InventoryOptimizationService 加载失败: {_e}"); inventory_optimization_service = None  # type: ignore

try:
    from backend.services.association_mining_service import association_mining_service
except Exception as _e:
    _logger.warning(f"[services] AssociationMiningService 加载失败: {_e}"); association_mining_service = None  # type: ignore

try:
    from backend.services.report_rendering_service import report_rendering_service
except Exception as _e:
    _logger.warning(f"[services] ReportRenderingService 加载失败: {_e}"); report_rendering_service = None  # type: ignore
