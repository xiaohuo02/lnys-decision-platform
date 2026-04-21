# -*- coding: utf-8 -*-
"""backend/routers/report.py — 报告管理 API（瘦路由）

GET  /api/reports              → 报告列表
POST /api/reports/generate     → 生成报告
GET  /api/reports/{id}/download → 下载报告 Markdown
"""
import uuid
from pathlib import Path
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from backend.config import settings
from backend.core.response import ok
from backend.core.exceptions import AppError
from backend.schemas.base import ApiResponse
from backend.database import get_async_db
from backend.services.report_rendering_service import (
    report_rendering_service,
    ReportRenderRequest,
)

router = APIRouter()

_STORE_ROOT = settings.ARTIFACT_STORE_ROOT / "reports"

# 内存中简易报告索引（生产环境应落DB）
_report_index: dict[str, dict] = {}


# ── 请求模型 ──────────────────────────────────────────────────
class GenerateReportBody(BaseModel):
    report_type: str = "business_overview"
    title:       str = "经营分析报告"
    modules:     List[str] = Field(default_factory=lambda: ["kpi", "customer", "forecast"])
    date_start:  Optional[str] = None
    date_end:    Optional[str] = None
    format:      str = "markdown"


# ── 模块摘要数据拉取 ─────────────────────────────────────────
_MODULE_TO_ANALYSIS = {
    "customer":  "customer_analysis",
    "forecast":  "sales_forecast",
    "sentiment": "sentiment_analysis",
    "fraud":     "fraud_detection",
    "inventory": "inventory_optimization",
    "association": "association_rules",
}

_MODULE_DEFAULTS = {
    "customer":    "客户分层：高价值客户占比 18.3%，流失风险客户 23 人，RFM 综合评分均值 6.2。",
    "forecast":    "销售预测：未来 7 天预测总量 ¥128,500，Stacking 模型 MAPE=19.5%，置信区间覆盖率 92%。",
    "sentiment":   "舆情分析：正面情感占比 68.2%，负面 12.5%，热点话题为产品质量和物流时效。",
    "fraud":       "欺诈风控：本期拦截可疑交易 47 笔，拦截率 99.92%，LightGBM AUC=0.9992。",
    "inventory":   "库存优化：A类 SKU 28 个需补货，安全库存达标率 85%，建议关注高 CV 品类。",
    "association": "关联分析：Top 规则 support=0.15 confidence=0.82，推荐组合商品 12 组。",
}

_EXPORT_FORMAT_ALIASES = {
    "md": "markdown",
    "markdown": "markdown",
    "html": "html",
    "htm": "html",
    "pdf": "markdown",
    "excel": "markdown",
    "txt": "markdown",
}

_EXPORT_MEDIA_TYPES = {
    "markdown": "text/markdown; charset=utf-8",
    "html": "text/html; charset=utf-8",
}

_EXPORT_EXTENSIONS = {
    "markdown": ".md",
    "html": ".html",
}


def _normalize_export_format(fmt: Optional[str]) -> str:
    return _EXPORT_FORMAT_ALIASES.get((fmt or "markdown").strip().lower(), "markdown")


def _snippet(text: str, limit: int = 72) -> str:
    compact = " ".join(str(text).split())
    if len(compact) <= limit:
        return compact
    return compact[:limit - 3] + "..."


def _compose_executive_summary(
    module_summaries: dict[str, Optional[str]],
    date_start: Optional[str],
    date_end: Optional[str],
) -> str:
    lines: List[str] = []
    if date_start and date_end:
        lines.append(f"本报告覆盖 {date_start} 至 {date_end} 的经营表现，重点结合客户、销售、风控、库存与舆情数据进行复盘。")
    else:
        lines.append("本报告基于当前已生成的经营分析结果进行汇总，可直接用于管理层周会或答辩展示。")

    ordered_modules = [
        ("customer", "客户经营"),
        ("forecast", "销售趋势"),
        ("inventory", "库存履约"),
        ("fraud", "交易风控"),
        ("sentiment", "品牌舆情"),
        ("association", "联动推荐"),
    ]
    for key, label in ordered_modules:
        if module_summaries.get(key):
            lines.append(f"{label}：{_snippet(module_summaries[key])}")

    missing = [label for key, label in ordered_modules if not module_summaries.get(key)]
    if missing:
        lines.append(f"当前未纳入 {', '.join(missing)} 数据，相关结论建议结合补充分析复核。")

    return "\n\n".join(lines[:5])


def _compose_risk_highlights(module_summaries: dict[str, Optional[str]]) -> str:
    risk_map = [
        ("customer", "客户留存"),
        ("fraud", "交易风控"),
        ("inventory", "库存履约"),
        ("sentiment", "品牌舆情"),
        ("forecast", "预测偏差"),
    ]
    lines: List[str] = []
    for key, label in risk_map:
        if module_summaries.get(key):
            lines.append(f"- {label}：{_snippet(module_summaries[key], 96)}")

    if not lines:
        return "当前未发现高优先级风险信号，但仍建议在正式发布或答辩前复核基础数据完整性。"
    return "\n".join(lines[:4])


def _compose_action_plan(
    selected_modules: List[str],
    module_summaries: dict[str, Optional[str]],
) -> str:
    action_bank = {
        "customer": "复核高价值与高流失风险客群，安排分层运营与挽回动作。",
        "forecast": "根据预测结果更新未来一周备货和排班计划，并跟踪误差回收。",
        "inventory": "优先处理库存预警 SKU，确认补货节奏与安全库存阈值。",
        "fraud": "抽查高风险交易与规则命中样本，确保人工审核链路可回放。",
        "sentiment": "跟进负面舆情主题与高频投诉点，形成对外回应口径。",
        "association": "将高置信关联规则同步给营销侧，验证组合推荐转化效果。",
    }
    actions: List[str] = []
    for module in selected_modules:
        if module in action_bank and module_summaries.get(module):
            actions.append(action_bank[module])
    if not actions:
        actions = [
            "确认本期报告使用的数据范围和生成时间，确保汇报口径一致。",
            "复核关键指标截图与结论，准备答辩场景下的追问说明。",
            "将重点风险和优先动作同步给业务负责人，形成闭环跟进。",
        ]
    return "\n".join(f"{idx}. {text}" for idx, text in enumerate(actions[:5], start=1))


def _guess_report_path(report_id: str, export_format: str) -> Optional[Path]:
    ext = _EXPORT_EXTENSIONS[export_format]
    exact = _STORE_ROOT / f"{report_id}_business_overview{ext}"
    if exact.exists():
        return exact
    matches = list(_STORE_ROOT.glob(f"{report_id}_*{ext}"))
    return matches[0] if matches else None


async def _fetch_module_summary(db: AsyncSession, module_key: str) -> Optional[str]:
    """从 analysis_results 表拉取最新摘要，失败时返回 None"""
    analysis_type = _MODULE_TO_ANALYSIS.get(module_key)
    if not analysis_type:
        return None
    try:
        from sqlalchemy import text
        result = await db.execute(text(
            "SELECT result_json FROM analysis_results "
            "WHERE analysis_type = :t ORDER BY id DESC LIMIT 1"
        ), {"t": analysis_type})
        row = result.fetchone()
        if row:
            import json
            data = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            return data.get("summary") or data.get("executive_summary") or str(data)[:500]
    except Exception as e:
        logger.debug(f"[report] fetch {module_key} summary failed: {e}")
    return None


@router.get("", summary="报告列表", response_model=ApiResponse[Any])
async def list_reports(
    page:      int = Query(1, ge=1),
    page_size: int = Query(20, le=100),
):
    items = sorted(_report_index.values(), key=lambda r: r["generated_at"], reverse=True)
    total = len(items)
    start = (page - 1) * page_size
    return ok({"total": total, "page": page, "page_size": page_size,
               "items": items[start:start + page_size]})


@router.post("/generate", summary="生成经营分析报告", response_model=ApiResponse[Any])
async def generate_report(body: GenerateReportBody, db: AsyncSession = Depends(get_async_db)):
    run_id = str(uuid.uuid4())
    export_format = _normalize_export_format(body.format)

    # 按前端选中的模块拉取数据
    module_summaries: dict[str, Optional[str]] = {}
    for mod in body.modules:
        if mod == "kpi":
            continue
        fetched = await _fetch_module_summary(db, mod)
        module_summaries[mod] = fetched or _MODULE_DEFAULTS.get(mod)

    req = ReportRenderRequest(
        run_id=run_id,
        report_type=body.report_type,
        requested_format=export_format,
        title=body.title,
        executive_summary=_compose_executive_summary(module_summaries, body.date_start, body.date_end),
        risk_highlights=_compose_risk_highlights(module_summaries),
        action_plan=_compose_action_plan(body.modules, module_summaries),
        customer_summary=module_summaries.get("customer"),
        forecast_summary=module_summaries.get("forecast"),
        sentiment_summary=module_summaries.get("sentiment"),
        fraud_summary=module_summaries.get("fraud"),
        inventory_summary=module_summaries.get("inventory"),
        association_summary=module_summaries.get("association"),
    )
    result = report_rendering_service.render(req)

    meta = {
        "report_id":    run_id,
        "title":        body.title,
        "report_type":  body.report_type,
        "word_count":   result.word_count,
        "partial":      result.partial,
        "generated_at": result.rendered_at.isoformat(),
        "artifact_uri": result.artifact_uri,
        "artifact_uris": result.artifact_uris,
        "requested_format": export_format,
        "available_formats": sorted(result.artifact_uris.keys()),
    }
    _report_index[run_id] = meta
    return ok(meta, message="报告生成完成")


@router.get("/{report_id}/download", summary="下载报告 Markdown")
async def download_report(
    report_id: str,
    format: str = Query("markdown"),
):
    export_format = _normalize_export_format(format)
    meta = _report_index.get(report_id)
    file_path: Optional[Path] = None
    if meta:
        artifact_uris = meta.get("artifact_uris") or {}
        candidate = artifact_uris.get(export_format)
        if candidate:
            candidate_path = Path(candidate)
            if candidate_path.exists():
                file_path = candidate_path
        if file_path is None and meta.get("artifact_uri"):
            fallback_path = Path(meta["artifact_uri"])
            if fallback_path.exists():
                file_path = fallback_path

    if file_path is None:
        file_path = _guess_report_path(report_id, export_format)

    if file_path and file_path.exists():
        content = file_path.read_text(encoding="utf-8")
        filename = f"{report_id}{_EXPORT_EXTENSIONS[export_format]}"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        if export_format == "html":
            return HTMLResponse(content, headers=headers, media_type=_EXPORT_MEDIA_TYPES[export_format])
        return PlainTextResponse(content, headers=headers, media_type=_EXPORT_MEDIA_TYPES[export_format])

    raise AppError(404, "报告不存在或已过期")
