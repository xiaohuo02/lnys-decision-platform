# -*- coding: utf-8 -*-
"""backend/mock/customer_mock.py — 客户分析 Mock 数据

所有 Mock 数据集中于此，Service 层按需引用。
数据为固定示例，不使用 random，确保可复现且不误导决策。
"""

MOCK_RFM: list[dict] = [
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

MOCK_SEGMENTS: dict = {
    "segments": [
        {"name": "高价值",   "count": 840,  "pct": 20.0, "color": "#FF6B35"},
        {"name": "潜力成长", "count": 1260, "pct": 30.0, "color": "#4ECDC4"},
        {"name": "流失预警", "count": 1050, "pct": 25.0, "color": "#FFE66D"},
        {"name": "沉睡",     "count": 1050, "pct": 25.0, "color": "#95A5A6"},
    ],
    "silhouette_score": 0.42,
    "cluster_k": 4,
}

MOCK_CLV_TEMPLATE: dict = {
    "name":                   "张**",
    "predicted_purchases_90d": 4.2,
    "predicted_clv":          12800.00,
    "clv_tier":               "top10",
}


def generate_mock_clv(top_n: int = 50) -> list[dict]:
    """生成 CLV Mock 数据列表"""
    return [
        {
            "customer_id":            f"LY{i:06d}",
            "name":                   MOCK_CLV_TEMPLATE["name"],
            "member_level":           ["钻石", "金卡", "银卡"][i % 3],
            "predicted_purchases_90d": round(4.2 - i * 0.05, 1),
            "predicted_clv":          round(12800 - i * 120, 2),
            "clv_tier":               "top10" if i < 5 else ("mid40" if i < 25 else "bot50"),
        }
        for i in range(top_n)
    ]


def generate_mock_churn_risk(top_n: int = 50) -> list[dict]:
    """生成流失风险 Mock 数据列表"""
    return [
        {
            "customer_id":        f"LY{88 + i:06d}",
            "churn_probability":  round(0.95 - i * 0.008, 3),
            "risk_level":         "高" if i < 25 else "中",
            "top3_reasons":       ["客服呼叫次数↑", "终身价值↓", "购物车放弃率↑"],
            "recommended_action": "专属优惠券 + 电话回访",
        }
        for i in range(top_n)
    ]


# predict_churn 降级时的固定示例（不使用 random）
MOCK_CHURN_PREDICT_FALLBACK: dict = {
    "churn_probability":  0.65,
    "risk_level":         "中",
    "top3_reasons":       ["客服呼叫次数↑", "终身价值↓", "购物车放弃率↑"],
    "recommended_action": "专属优惠券 + 电话回访",
    "source":             "mock",
}
