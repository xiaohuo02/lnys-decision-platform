# -*- coding: utf-8 -*-
"""backend/services/customer_service.py — 客户分析业务逻辑"""
import json
from typing import Optional, Any

import pandas as pd
import redis.asyncio as aioredis
from sqlalchemy.orm import Session
from loguru import logger

from backend.config import settings
from backend.core.response import ok, cached, degraded
from backend.core.exceptions import AppError
from backend.agents.gateway import AgentGateway
from backend.repositories.analysis_results_repo import AnalysisResultsRepo
from backend.schemas.customer_schemas import ChurnPredictRequest

_RESULTS  = settings.MODELS_ROOT / "results" / "customer"
_CACHE_TTL = 3600   # 分析结果缓存 TTL（1h）

# ── CSV 列名 → 前端字段名 映射 ──────────────────────────────────────────

_RFM_RENAME = {
    "Recency": "recency", "Frequency": "frequency", "Monetary": "monetary",
    "Recency_score": "r_score", "Frequency_score": "f_score",
    "Monetary_score": "m_score", "RFM_score": "rfm_total",
}

_CLV_RENAME = {
    "clv_90d": "predicted_clv",
    "pred_purchases_90d": "predicted_purchases_90d",
    "pred_avg_value": "predicted_avg_value",
    "monetary_value": "monetary",
}

_CHURN_SHAP_REASONS = {
    "Cart_Abandonment_Rate": "购物车放弃率↑",
    "Customer_Service_Calls": "客服呼叫次数↑",
    "Days_Since_Last_Purchase": "距上次购买天数↑",
    "Returns_Rate": "退货率↑",
    "Lifetime_Value": "终身价值↓",
    "Login_Frequency": "登录频率↓",
    "Session_Duration_Avg": "平均浏览时长↓",
    "Total_Purchases": "总购买次数↓",
    "Average_Order_Value": "客单价↓",
    "Social_Media_Engagement_Score": "社交互动↓",
}


def _normalize_rfm_columns(df: pd.DataFrame) -> pd.DataFrame:
    """将 CSV 的大写 / 全名列映射为前端期望的小写 / 缩写"""
    rename = {k: v for k, v in _RFM_RENAME.items() if k in df.columns}
    if rename:
        df = df.rename(columns=rename)
    # 派生 member_level：基于 rfm_total（3~15分）映射会员等级
    if "member_level" not in df.columns and "rfm_total" in df.columns:
        df["member_level"] = df["rfm_total"].apply(
            lambda s: "钻石" if s >= 13 else ("金卡" if s >= 10 else ("银卡" if s >= 7 else "普通"))
        )
    return df


def _normalize_clv_columns(df: pd.DataFrame) -> pd.DataFrame:
    """将 CLV CSV 列映射为前端期望的 predicted_clv 等"""
    rename = {k: v for k, v in _CLV_RENAME.items() if k in df.columns}
    if rename:
        df = df.rename(columns=rename)
    return df


def _normalize_churn_columns(df: pd.DataFrame) -> pd.DataFrame:
    """将流失 CSV（训练特征 + pred_proba）转为前端字段"""
    if "pred_proba" in df.columns:
        df = df.rename(columns={"pred_proba": "churn_probability"})
    # 生成 customer_id（如果缺失）
    if "customer_id" not in df.columns:
        df["customer_id"] = [f"LY{i:06d}" for i in range(1, len(df) + 1)]
    # 生成 risk_level
    if "churn_probability" in df.columns and "risk_level" not in df.columns:
        df["risk_level"] = df["churn_probability"].apply(
            lambda p: "高" if p > 0.7 else ("中" if p > 0.4 else "低")
        )
    # 生成 top3_reasons（基于特征重要性启发式排序）
    if "top3_reasons" not in df.columns:
        reason_cols = [c for c in _CHURN_SHAP_REASONS if c in df.columns]
        if reason_cols:
            def _top3(row):
                scored = sorted(reason_cols, key=lambda c: abs(row.get(c, 0)), reverse=True)[:3]
                return [_CHURN_SHAP_REASONS[c] for c in scored]
            df["top3_reasons"] = df.apply(_top3, axis=1)
        else:
            df["top3_reasons"] = [["数据不足"]] * len(df)
    # 生成 recommended_action
    if "recommended_action" not in df.columns:
        df["recommended_action"] = df["risk_level"].apply(
            lambda l: "专属优惠券 + 电话回访" if l == "高" else (
                "关怀短信 + 积分奖励" if l == "中" else "常规维护")
        ) if "risk_level" in df.columns else "常规维护"
    # 派生 member_level（基于 Membership_Years）
    if "member_level" not in df.columns and "Membership_Years" in df.columns:
        df["member_level"] = df["Membership_Years"].apply(
            lambda y: "钻石" if y >= 4 else ("金卡" if y >= 3 else ("银卡" if y >= 2 else "普通"))
        )
    # 派生 segment（基于 churn_probability）
    if "segment" not in df.columns and "churn_probability" in df.columns:
        df["segment"] = df["churn_probability"].apply(
            lambda p: "流失预警" if p > 0.7 else ("潜力成长" if p > 0.4 else "高价值")
        )
    # 只保留前端需要的列
    keep = ["customer_id", "churn_probability", "risk_level", "top3_reasons",
            "recommended_action", "member_level", "segment"]
    keep = [c for c in keep if c in df.columns]
    return df[keep]


class CustomerService:
    def __init__(self, db: Session, redis: aioredis.Redis, agent: Any = None):
        self.db    = db
        self.redis = redis
        self.agent = agent
        self._repo = AnalysisResultsRepo(db)

    # ── 缓存读写帮助方法 ────────────────────────────────────────────────

    async def _read_result(self, redis_key: str, db_module: str) -> Optional[dict]:
        """读取顺序：Redis 热缓存 → DB 持久化层 → None"""
        try:
            val = await self.redis.get(redis_key)
            if val:
                return json.loads(val)
        except Exception as e:
            logger.warning(f"[customer_svc] redis get {redis_key}: {e}")

        result = self._repo.get_latest(db_module)
        if result is not None:
            try:
                await self.redis.setex(redis_key, _CACHE_TTL,
                                       json.dumps(result, ensure_ascii=False))
            except Exception:
                pass
        return result

    async def _set_result(self, redis_key: str, db_module: str, data: dict) -> None:
        """写入 Redis + DB（CSV 命中后回写）"""
        self._repo.save(db_module, data)
        try:
            await self.redis.setex(redis_key, _CACHE_TTL,
                                   json.dumps(data, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"[customer_svc] redis setex {redis_key}: {e}")

    # ── GET endpoints ─────────────────────────────────────────────────────

    async def get_rfm(
        self,
        member_level: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        # 1. Redis → DB
        hit = await self._read_result("customer:rfm:all", "customer_rfm")
        if hit is not None:
            rows = hit.get("data", []) if isinstance(hit, dict) else hit
            # 兼容旧缓存：如果缓存数据缺少 member_level，根据 rfm_total 补充
            for r in rows:
                if "member_level" not in r and "rfm_total" in r:
                    s = r["rfm_total"]
                    r["member_level"] = "钻石" if s >= 13 else ("金卡" if s >= 10 else ("银卡" if s >= 7 else "普通"))
            if member_level:
                rows = [r for r in rows if r.get("member_level") == member_level]
            total = len(rows)
            start = (page - 1) * page_size
            return ok({"total": total, "page": page, "page_size": page_size,
                       "items": rows[start:start + page_size]})

        # 2. CSV
        path = _RESULTS / "rfm_result.csv"
        if path.exists():
            try:
                df    = pd.read_csv(path)
                df    = _normalize_rfm_columns(df)
                df    = df.where(df.notna(), None)
                rows  = df.to_dict("records")
                await self._set_result("customer:rfm:all", "customer_rfm", {"data": rows})
                if member_level and "member_level" in df.columns:
                    df = df[df["member_level"] == member_level]
                total = len(df)
                start = (page - 1) * page_size
                return ok({"total": total, "page": page, "page_size": page_size,
                           "items": df.iloc[start:start + page_size].to_dict("records")})
            except Exception as e:
                logger.warning(f"[customer_svc] rfm csv error: {e}")

        # 3. Mock
        if settings.ENABLE_MOCK_DATA:
            mock = [
                {
                    "customer_id":  f"LY{i:06d}",
                    "recency":      i * 3 % 90,
                    "frequency":    i % 15 + 1,
                    "monetary":     round(500 + i * 47.3, 2),
                    "r_score":      5 - i % 5,
                    "f_score":      i % 5 + 1,
                    "m_score":      (i * 3) % 5 + 1,
                    "rfm_total":    9,
                    "segment":      ["高价值", "潜力成长", "流失预警", "沉睡"][i % 4],
                    "member_level": ["普通", "银卡", "金卡", "钻石"][i % 4],
                }
                for i in range(1, 101)
            ]
            if member_level:
                mock = [r for r in mock if r["member_level"] == member_level]
            total = len(mock)
            start = (page - 1) * page_size
            return degraded(
                {"total": total, "page": page, "page_size": page_size,
                 "items": mock[start:start + page_size]},
                "mock data",
            )
        raise AppError(503, "RFM 数据暂未就绪，请先运行 ML 训练流水线")

    async def get_segments(self) -> dict:
        # 1. Redis → DB
        hit = await self._read_result("customer:segments", "customer_segments")
        if hit is not None:
            # 校验缓存格式：必须包含 segments 数组，否则视为旧格式、跳过
            if isinstance(hit, dict) and isinstance(hit.get("segments"), list):
                return ok(hit)

        # 2. CSV
        path = _RESULTS / "clustering_result.csv"
        if path.exists():
            try:
                df   = pd.read_csv(path)
                _COLORS = ["#FF6B35", "#4ECDC4", "#FFE66D", "#95A5A6",
                           "#6C5CE7", "#00B894", "#E17055", "#0984E3"]
                # 优先使用 segment 文字列（与 RFM 表格一致），回退到 cluster 数字列
                if "segment" in df.columns:
                    counts = df["segment"].value_counts()
                    total  = int(counts.sum())
                    segs = [
                        {
                            "name":  str(k),
                            "count": int(v),
                            "pct":   round(v / total * 100, 1) if total else 0,
                            "color": _COLORS[i % len(_COLORS)],
                        }
                        for i, (k, v) in enumerate(counts.items())
                    ]
                elif "cluster" in df.columns:
                    counts = df["cluster"].value_counts().sort_index()
                    total  = int(counts.sum())
                    _NAMES  = ["高价值", "潜力成长", "流失预警", "沉睡",
                               "新客", "忠诚", "低活跃", "其他"]
                    segs = [
                        {
                            "name":  _NAMES[i] if i < len(_NAMES) else f"簇{k}",
                            "count": int(v),
                            "pct":   round(v / total * 100, 1) if total else 0,
                            "color": _COLORS[i % len(_COLORS)],
                        }
                        for i, (k, v) in enumerate(counts.items())
                    ]
                else:
                    segs = []
                data = {
                    "segments":         segs,
                    "silhouette_score": None,
                    "cluster_k":        len(segs),
                }
                await self._set_result("customer:segments", "customer_segments", data)
                return ok(data)
            except Exception as e:
                logger.warning(f"[customer_svc] segments csv error: {e}")

        # 3. Mock
        if settings.ENABLE_MOCK_DATA:
            mock = {
                "segments": [
                    {"name": "高价值",   "count": 840,  "pct": 20.0, "color": "#FF6B35"},
                    {"name": "潜力成长", "count": 1260, "pct": 30.0, "color": "#4ECDC4"},
                    {"name": "流失预警", "count": 1050, "pct": 25.0, "color": "#FFE66D"},
                    {"name": "沉睡",     "count": 1050, "pct": 25.0, "color": "#95A5A6"},
                ],
                "silhouette_score": 0.42,
                "cluster_k": 4,
            }
            return degraded(mock, "mock data")
        raise AppError(503, "客群数据暂未就绪")

    async def get_clv(self, top_n: int = 50) -> dict:
        # 1. Redis → DB
        hit = await self._read_result("customer:clv:all", "customer_clv")
        if hit is not None:
            rows = hit.get("data", []) if isinstance(hit, dict) else hit
            return ok(rows[:top_n])

        # 2. CSV
        path = _RESULTS / "clv_result.csv"
        if path.exists():
            try:
                df  = pd.read_csv(path)
                df  = _normalize_clv_columns(df)
                col = "predicted_clv" if "predicted_clv" in df.columns else df.columns[-1]
                df  = df.where(df.notna(), None)
                all_rows = df.to_dict("records")
                await self._set_result("customer:clv:all", "customer_clv", {"data": all_rows})
                return ok(df.nlargest(top_n, col).to_dict("records"))
            except Exception as e:
                logger.warning(f"[customer_svc] clv csv error: {e}")

        # 3. Mock
        if settings.ENABLE_MOCK_DATA:
            mock = [
                {
                    "customer_id":            f"LY{i:06d}",
                    "name":                   "张**",
                    "member_level":           ["钻石", "金卡", "银卡"][i % 3],
                    "predicted_purchases_90d": round(4.2 - i * 0.05, 1),
                    "predicted_clv":          round(12800 - i * 120, 2),
                    "clv_tier":               "top10" if i < 5 else ("mid40" if i < 25 else "bot50"),
                }
                for i in range(top_n)
            ]
            return degraded(mock, "mock data")
        raise AppError(503, "CLV 数据暂未就绪")

    async def get_churn_risk(self, threshold: float = 0.7, top_n: int = 50) -> dict:
        # 1. Redis → DB——全量列表，在内存中过滤 threshold
        hit = await self._read_result("customer:churn_risk:all", "customer_churn_risk")
        if hit is not None:
            rows = hit.get("data", []) if isinstance(hit, dict) else hit
            rows = [r for r in rows
                    if r.get("churn_probability", r.get("pred_proba", 0)) >= threshold]
            rows = sorted(rows,
                          key=lambda r: r.get("churn_probability", r.get("pred_proba", 0)),
                          reverse=True)[:top_n]
            return ok({"total_high_risk": len(rows), "items": rows})

        # 2. CSV
        path = _RESULTS / "churn_result.csv"
        if path.exists():
            try:
                df       = pd.read_csv(path)
                df       = _normalize_churn_columns(df)
                df       = df.where(df.notna(), None)
                all_rows = df.to_dict("records")
                await self._set_result(
                    "customer:churn_risk:all", "customer_churn_risk", {"data": all_rows}
                )
                col = "churn_probability"
                if col in df.columns:
                    df = df[df[col] >= threshold].nlargest(top_n, col)
                return ok({"total_high_risk": len(df), "items": df.to_dict("records")})
            except Exception as e:
                logger.warning(f"[customer_svc] churn_risk csv error: {e}")

        # 3. Mock
        if settings.ENABLE_MOCK_DATA:
            mock = [
                {
                    "customer_id":        f"LY{88 + i:06d}",
                    "churn_probability":  round(0.95 - i * 0.008, 3),
                    "risk_level":         "高" if i < 25 else "中",
                    "top3_reasons":       ["客服呼叫次数↑", "终身价值↓", "购物车放弃率↑"],
                    "recommended_action": "专属优惠券 + 电话回访",
                    "member_level":       ["钻石", "金卡", "银卡", "普通"][i % 4],
                    "segment":            "流失预警" if i < 25 else "潜力成长",
                }
                for i in range(top_n)
            ]
            return degraded({"total_high_risk": len(mock), "items": mock}, "mock data")
        raise AppError(503, "流失风险数据暂未就绪")

    # ── POST inference endpoint ────────────────────────────────────────────

    async def predict_churn(self, body: ChurnPredictRequest) -> dict:
        cache_key = f"churn:predict:{body.customer_id}"
        try:
            cached_val = await self.redis.get(cache_key)
            if cached_val:
                return cached(json.loads(cached_val))
        except Exception as e:
            logger.warning(f"[customer_svc] redis get failed: {e}")

        result = await AgentGateway.call(
            self.agent, {"mode": "predict_single", "customer_data": body.model_dump()},
            agent_name="customer_agent",
        )

        if result is None:
            if not settings.ENABLE_MOCK_DATA:
                raise AppError(503, "流失预测模型暂未就绪，无法提供预测服务")
            import random
            prob   = round(random.uniform(0.1, 0.99), 4)
            result = {
                "customer_id":        body.customer_id,
                "churn_probability":  prob,
                "risk_level":         "高" if prob > 0.7 else ("中" if prob > 0.4 else "低"),
                "top3_reasons":       ["客服呼叫次数↑", "终身价值↓", "购物车放弃率↑"],
                "recommended_action": "专属优惠券 + 电话回访",
            }
            return degraded(result, "mock predict_churn: agent unavailable")

        try:
            await self.redis.setex(cache_key, 3600, json.dumps(result, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"[customer_svc] redis setex failed: {e}")

        return ok(result)
