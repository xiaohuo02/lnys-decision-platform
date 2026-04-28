# -*- coding: utf-8 -*-
"""01_rfm.py — RFM 客户价值分析"""
import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent.parent))
import pandas as pd
import numpy as np
import pickle
from ml.config import *

OUT = RES_CUSTOMER / "rfm_result.csv"
if OUT.exists():
    print("SKIP: rfm_result.csv already exists"); exit(0)

print("[01] 读取订单数据...")
df = pd.read_csv(ORDERS_CSV, parse_dates=["order_date"], low_memory=False)
snapshot = df["order_date"].max() + pd.Timedelta(days=1)

print("[01] 计算 RFM...")
rfm = df.groupby("customer_id").agg(
    Recency   = ("order_date",   lambda x: (snapshot - x.max()).days),
    Frequency = ("order_id",     "nunique"),
    Monetary  = ("total_amount", "sum"),
).reset_index()

for col in ["Recency","Frequency","Monetary"]:
    labels = [5,4,3,2,1] if col=="Recency" else [1,2,3,4,5]
    rfm[f"{col}_score"] = pd.qcut(rfm[col], q=5, labels=labels, duplicates="drop")

rfm["RFM_score"] = (rfm["Recency_score"].astype(int)
                  + rfm["Frequency_score"].astype(int)
                  + rfm["Monetary_score"].astype(int))

def segment(score):
    if score >= 12: return "高价值客户"
    if score >= 9:  return "潜力成长客户"
    if score >= 6:  return "流失预警客户"
    return "沉睡客户"

rfm["segment"] = rfm["RFM_score"].apply(segment)
rfm.to_csv(OUT, index=False, encoding="utf-8-sig")
print(f"[01] ✅ RFM完成 → {OUT}")
print(rfm["segment"].value_counts().to_string())
