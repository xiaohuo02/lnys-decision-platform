# -*- coding: utf-8 -*-
"""05_cohort.py — Cohort 留存分析"""
import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent.parent))
import pandas as pd, numpy as np
from ml.config import *

OUT = RES_CUSTOMER / "cohort_retention.csv"
if OUT.exists(): print("SKIP"); exit(0)

print("[05] 读取订单数据...")
df = pd.read_csv(ORDERS_CSV, parse_dates=["order_date"], low_memory=False)
df["order_month"] = df["order_date"].dt.to_period("M")

first_order = df.groupby("customer_id")["order_month"].min().reset_index()
first_order.columns = ["customer_id","cohort_month"]
df = df.merge(first_order, on="customer_id")

df["period_number"] = (df["order_month"] - df["cohort_month"]).apply(lambda x: x.n)
cohort_data = df.groupby(["cohort_month","period_number"])["customer_id"].nunique().reset_index()
cohort_pivot = cohort_data.pivot(index="cohort_month", columns="period_number", values="customer_id")
cohort_size  = cohort_pivot.iloc[:,0]
retention    = cohort_pivot.divide(cohort_size, axis=0).round(3)

retention.to_csv(OUT, encoding="utf-8-sig")
print(f"[05] ✅ Cohort 完成 → {OUT}")
print(f"  队列数: {len(retention)}  最大追踪期: {retention.shape[1]} 个月")
print(f"  1月留存均值: {retention.get(1, pd.Series([0])).mean():.1%}")
print(f"  3月留存均值: {retention.get(3, pd.Series([0])).mean():.1%}")
print(f"  6月留存均值: {retention.get(6, pd.Series([0])).mean():.1%}")
