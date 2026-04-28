# -*- coding: utf-8 -*-
"""04_clv.py — BG-NBD + Gamma-Gamma 客户终身价值预测"""
import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent.parent))
import pandas as pd, numpy as np
from lifetimes import BetaGeoFitter, GammaGammaFitter
from lifetimes.utils import summary_data_from_transaction_data
try:
    import dill as pickle
except ImportError:
    import pickle
from ml.config import *

OUT = RES_CUSTOMER / "clv_result.csv"
if OUT.exists(): print("SKIP"); exit(0)

print("[04] 读取订单数据...")
df = pd.read_csv(ORDERS_CSV, parse_dates=["order_date"], low_memory=False)
df = df[df["total_amount"] > 0]
snapshot = df["order_date"].max()

print("[04] 构建 BG-NBD 输入汇总表...")
summary = summary_data_from_transaction_data(
    df, "customer_id", "order_date", "total_amount",
    observation_period_end=snapshot
)
summary = summary[summary["frequency"] > 0]
print(f"  有效客户(复购≥1): {len(summary):,}")

print("[04] 拟合 BG-NBD 模型（预测购买次数）...")
bgf = BetaGeoFitter(penalizer_coef=0.001)
bgf.fit(summary["frequency"], summary["recency"], summary["T"], verbose=False)
summary["pred_purchases_90d"] = bgf.conditional_expected_number_of_purchases_up_to_time(
    90, summary["frequency"], summary["recency"], summary["T"]
)
try:
    import dill; dill.dump(bgf, open(MODELS/"bgf.pkl","wb"))
except Exception:
    pass  # bgf not serializable, skip

print("[04] 拟合 Gamma-Gamma 模型（预测客单价）...")
ggf = GammaGammaFitter(penalizer_coef=0.001)
ggf.fit(summary["frequency"], summary["monetary_value"], verbose=False)
summary["pred_avg_value"] = ggf.conditional_expected_average_profit(
    summary["frequency"], summary["monetary_value"]
)
try:
    import dill; dill.dump(ggf, open(MODELS/"ggf.pkl","wb"))
except Exception:
    pass  # ggf not serializable, skip

GROSS_MARGIN = 0.35
summary["clv_90d"] = (summary["pred_purchases_90d"] * summary["pred_avg_value"] * GROSS_MARGIN).round(2)
summary = summary.sort_values("clv_90d", ascending=False).reset_index()
summary.to_csv(OUT, index=False, encoding="utf-8-sig")
print(f"[04] ✅ CLV 完成 → {OUT}")
print(f"  CLV Top5:\n{summary[['customer_id','clv_90d','pred_purchases_90d']].head().to_string()}")
