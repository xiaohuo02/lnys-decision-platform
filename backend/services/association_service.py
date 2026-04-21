# -*- coding: utf-8 -*-
"""backend/services/association_service.py — 关联分析业务逻辑"""
import re
from typing import Any

import pandas as pd
import redis.asyncio as aioredis
from sqlalchemy.orm import Session
from loguru import logger

from backend.config import settings
from backend.core.response import ok, degraded
from backend.core.exceptions import AppError
from backend.core.cache import redis_cached
from backend.agents.gateway import AgentGateway
from backend.services.inventory_service import _SKU_NAME_MAP

_RULES_CSV = settings.MODELS_ROOT / "results" / "ops" / "association_rules.csv"

# ── 展示列白名单 ──
_DISPLAY_COLS = [
    "antecedents", "consequents",
    "antecedent_names", "consequent_names",
    "support", "confidence", "lift",
    "leverage", "conviction",
]

_ROUND_COLS = {
    "support": 4, "confidence": 3, "lift": 2,
    "antecedent support": 4, "consequent support": 4,
    "leverage": 4, "conviction": 2, "zhangs_metric": 3,
    "jaccard": 3, "certainty": 3, "kulczynski": 3,
}


def _sku_to_name(code: str) -> str:
    return _SKU_NAME_MAP.get(code.strip(), code.strip())


def _names_col(codes_str: str) -> str:
    """'A002,D003' → '永春芦柑（3斤装）,蜂蜜柠檬片（150g）'"""
    return ",".join(_sku_to_name(c) for c in codes_str.split(","))


def _enrich_rules(df: pd.DataFrame) -> pd.DataFrame:
    """添加产品名称列、round 数值、精简输出列"""
    if "antecedents" in df.columns:
        df["antecedent_names"] = df["antecedents"].apply(_names_col)
    if "consequents" in df.columns:
        df["consequent_names"] = df["consequents"].apply(_names_col)
    for col, dec in _ROUND_COLS.items():
        if col in df.columns:
            df[col] = df[col].round(dec)
    out_cols = [c for c in _DISPLAY_COLS if c in df.columns]
    return df[out_cols]


def _parse_frozenset(val) -> str:
    """将 frozenset 字符串解析为逗号分隔的清洁格式，如 'D003,E002'"""
    if not isinstance(val, str):
        return str(val)
    m = re.search(r"\{(.+?)\}", val)
    if m:
        items = [s.strip().strip("'\"") for s in m.group(1).split(",")]
        return ",".join(sorted(items))
    return val

_MOCK_RULES = [
    {"antecedents": "LY-GR-001", "consequents": "LY-GR-003",
     "support": 0.045, "confidence": 0.72, "lift": 3.8},
    {"antecedents": "LY-GR-002", "consequents": "LY-FR-001",
     "support": 0.038, "confidence": 0.65, "lift": 3.2},
    {"antecedents": "LY-GR-001,LY-GR-002", "consequents": "LY-GR-004",
     "support": 0.021, "confidence": 0.81, "lift": 5.1},
    {"antecedents": "LY-FR-001", "consequents": "LY-GR-001",
     "support": 0.032, "confidence": 0.58, "lift": 2.9},
    {"antecedents": "LY-GR-003", "consequents": "LY-FR-002",
     "support": 0.028, "confidence": 0.62, "lift": 2.5},
    {"antecedents": "LY-FR-002", "consequents": "LY-GR-002",
     "support": 0.019, "confidence": 0.55, "lift": 2.1},
]


def _build_graph(rules: list, max_nodes: int = 100) -> dict:
    """将规则列表转换为 { nodes, edges } 图谱数据"""
    node_map: dict[str, dict] = {}
    edges: list[dict] = []

    for r in rules:
        ants = [s.strip() for s in str(r.get("antecedents", "")).split(",") if s.strip()]
        cons = [s.strip() for s in str(r.get("consequents", "")).split(",") if s.strip()]
        for sku in ants + cons:
            if sku not in node_map:
                node_map[sku] = {"id": sku, "name": _sku_to_name(sku), "frequency": 0}
            node_map[sku]["frequency"] += 1
        for a in ants:
            for c in cons:
                edges.append({
                    "source": a,
                    "target": c,
                    "lift": round(float(r.get("lift", 0)), 2),
                    "confidence": round(float(r.get("confidence", 0)), 3),
                    "support": round(float(r.get("support", 0)), 4),
                })

    nodes = sorted(node_map.values(), key=lambda n: n["frequency"], reverse=True)[:max_nodes]
    node_ids = {n["id"] for n in nodes}
    edges = [e for e in edges if e["source"] in node_ids and e["target"] in node_ids]
    return {"nodes": nodes, "edges": edges}


class AssociationService:
    def __init__(self, db: Session, redis: aioredis.Redis, agent: Any = None):
        self.db    = db
        self.redis = redis
        self.agent = agent
        self._rules_df = self._load_rules()

    def _load_rules(self) -> pd.DataFrame:
        if _RULES_CSV.exists():
            try:
                df = pd.read_csv(_RULES_CSV)
                # 解析 frozenset 格式为清洁字符串
                for col in ("antecedents", "consequents"):
                    if col in df.columns:
                        df[col] = df[col].apply(_parse_frozenset)
                return df
            except Exception as e:
                logger.warning(f"[association_svc] rules csv load failed: {e}")
        return pd.DataFrame()

    @redis_cached("association:rules", ttl=600)
    async def get_rules(self, top_n: int = 20, min_lift: float = 1.0) -> dict:
        if not self._rules_df.empty:
            df = self._rules_df.copy()
            if "lift" in df.columns:
                df = df[df["lift"] >= min_lift].nlargest(top_n, "lift")
            df = _enrich_rules(df.head(top_n))
            return ok(df.where(df.notna(), None).to_dict("records"))

        if settings.ENABLE_MOCK_DATA:
            return degraded(
                [r for r in _MOCK_RULES if r["lift"] >= min_lift][:top_n],
                "mock data",
            )
        raise AppError(503, "关联规则数据暂未就绪")

    async def recommend(self, sku_code: str, top_n: int = 5) -> dict:
        result = await AgentGateway.call(
            self.agent,
            {"sku_code": sku_code, "top_n": top_n},
            agent_name="association_agent",
        )
        if result is not None:
            return ok(result)

        if not self._rules_df.empty:
            mask = self._rules_df["antecedents"].str.contains(sku_code, na=False)
            top  = self._rules_df[mask].nlargest(top_n, "lift")
            recs = top[["consequents", "confidence", "lift"]].where(top[["consequents", "confidence", "lift"]].notna(), None).to_dict("records")
            for r in recs:
                r["sku_code"] = r["consequents"]
                r["sku_name"] = _names_col(r["consequents"])
                r["confidence"] = round(r["confidence"], 3) if r["confidence"] is not None else None
                r["lift"] = round(r["lift"], 2) if r["lift"] is not None else None
            return ok(recs)

        if settings.ENABLE_MOCK_DATA:
            recs = [
                {"sku_code": r["consequents"], "consequents": r["consequents"],
                 "confidence": r["confidence"], "lift": r["lift"]}
                for r in _MOCK_RULES if sku_code in r["antecedents"]
            ][:top_n]
            return degraded(recs, "mock data")
        raise AppError(503, "推荐数据暂未就绪")

    # ── 图谱数据 ──────────────────────────────────────────────

    @redis_cached("association:graph", ttl=600)
    async def get_graph(self, min_lift: float = 1.5, max_nodes: int = 100) -> dict:
        """将关联规则转换为图谱数据 { nodes, edges }"""
        if not self._rules_df.empty:
            df = self._rules_df.copy()
            if "lift" in df.columns:
                df = df[df["lift"] >= min_lift]

            node_map: dict[str, dict] = {}
            edges = []

            for _, row in df.iterrows():
                ants = [s.strip() for s in str(row.get("antecedents", "")).split(",") if s.strip()]
                cons = [s.strip() for s in str(row.get("consequents", "")).split(",") if s.strip()]
                for sku in ants + cons:
                    if sku not in node_map:
                        node_map[sku] = {"id": sku, "name": _sku_to_name(sku), "frequency": 0}
                    node_map[sku]["frequency"] += 1

                for a in ants:
                    for c in cons:
                        edges.append({
                            "source": a,
                            "target": c,
                            "lift": round(float(row.get("lift", 0)), 2),
                            "confidence": round(float(row.get("confidence", 0)), 3),
                            "support": round(float(row.get("support", 0)), 4),
                        })

            nodes = sorted(node_map.values(), key=lambda n: n["frequency"], reverse=True)[:max_nodes]
            node_ids = {n["id"] for n in nodes}
            edges = [e for e in edges if e["source"] in node_ids and e["target"] in node_ids]
            return ok({"nodes": nodes, "edges": edges})

        if settings.ENABLE_MOCK_DATA:
            return degraded(_mock_graph_data(), "mock data")
        raise AppError(503, "关联规则数据暂未就绪")

    # ── SKU 关联规则 ──────────────────────────────────────────

    async def get_sku_rules(self, sku_code: str, top_n: int = 20) -> dict:
        """返回指定 SKU 参与的所有关联规则（按 Lift 降序）"""
        if not self._rules_df.empty:
            mask = (
                self._rules_df["antecedents"].str.contains(sku_code, na=False)
                | self._rules_df["consequents"].str.contains(sku_code, na=False)
            )
            df = self._rules_df[mask].nlargest(top_n, "lift")
            df = _enrich_rules(df)
            return ok(df.where(df.notna(), None).to_dict("records"))

        if settings.ENABLE_MOCK_DATA:
            matched = [r for r in _MOCK_RULES if sku_code in r["antecedents"] or sku_code in r["consequents"]]
            return degraded(matched[:top_n], "mock data")
        raise AppError(503, "关联规则数据暂未就绪")


def _mock_graph_data() -> dict:
    """生成 Mock 图谱数据"""
    nodes = [
        {"id": "LY-GR-001", "name": "永春芦柑(3斤装)", "frequency": 5},
        {"id": "LY-GR-002", "name": "蜜柚(红心)", "frequency": 4},
        {"id": "LY-GR-003", "name": "脐橙(5斤)", "frequency": 3},
        {"id": "LY-GR-004", "name": "沃柑(精选)", "frequency": 3},
        {"id": "LY-FR-001", "name": "蜂蜜柠檬片(150g)", "frequency": 2},
        {"id": "LY-FR-002", "name": "陈皮梅(200g)", "frequency": 2},
    ]
    edges = [
        {"source": "LY-GR-001", "target": "LY-GR-003", "lift": 3.80, "confidence": 0.720, "support": 0.045},
        {"source": "LY-GR-002", "target": "LY-FR-001", "lift": 3.20, "confidence": 0.650, "support": 0.038},
        {"source": "LY-GR-001", "target": "LY-GR-004", "lift": 5.10, "confidence": 0.810, "support": 0.021},
        {"source": "LY-GR-002", "target": "LY-GR-004", "lift": 2.50, "confidence": 0.550, "support": 0.032},
        {"source": "LY-GR-003", "target": "LY-FR-002", "lift": 1.80, "confidence": 0.420, "support": 0.018},
        {"source": "LY-FR-001", "target": "LY-FR-002", "lift": 2.10, "confidence": 0.480, "support": 0.015},
    ]
    return {"nodes": nodes, "edges": edges}
