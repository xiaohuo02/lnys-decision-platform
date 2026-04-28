# -*- coding: utf-8 -*-
"""
04_offline_stores.py
Walmart Store Sales → 柠优生活线下门店周销售数据
输出：data/processed/stores_offline.csv

改写规则：
  - Store(1~45) → mod 8 映射柠优 8 家门店
  - city/province 固定映射（不随机）
  - Weekly_Sales 按门店层级缩放（一线×1.0 / 二线×0.65 / 三线×0.40）
  - Holiday_Flag → 替换为中国节假日
  - 日期 Shift：原始格式 dd-mm-yyyy → 加13年

运行：.venv\Scripts\python scripts/04_offline_stores.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
import numpy as np
from pathlib import Path
from dateutil.relativedelta import relativedelta

from company_config import STORES, WALMART_STORE_MAP, TIER_SCALE, is_holiday

RAW_FILE = Path("data/raw/walmart_sales/Walmart_Sales.csv")
OUT_FILE = Path("data/processed/stores_offline.csv")
OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

SEED = 42
rng  = np.random.default_rng(SEED)

# ─── 1. 读取 Walmart 数据 ─────────────────────────────────────
print("读取 Walmart Store Sales...")
df = pd.read_csv(RAW_FILE)
print(f"  行数: {len(df):,}  门店数: {df['Store'].nunique()}  周数: {df['Date'].nunique()}")

# ─── 2. 日期解析 + 偏移13年 ───────────────────────────────────
print("日期转换 dd-mm-yyyy → +13年...")
df["date_raw"] = pd.to_datetime(df["Date"], format="%d-%m-%Y", errors="coerce")
df = df[df["date_raw"].notna()]
df["sale_date"] = df["date_raw"].apply(
    lambda d: (d + relativedelta(years=13)).date()
)

# ─── 3. Walmart Store → 柠优门店 ──────────────────────────────
print("门店 ID 映射...")
df["store_id"]  = df["Store"].map(WALMART_STORE_MAP)
df["city"]      = df["store_id"].map(lambda s: STORES[s]["city"])
df["province"]  = df["store_id"].map(lambda s: STORES[s]["province"])
df["tier"]      = df["store_id"].map(lambda s: STORES[s]["tier"])

# ─── 4. Weekly_Sales 按层级缩放 ──────────────────────────────
print("销售额缩放...")
df["scale_factor"] = df["tier"].map(TIER_SCALE)
df["weekly_sales"] = (df["Weekly_Sales"] * df["scale_factor"]).round(2)

# ─── 5. Holiday_Flag → 中国节假日 ────────────────────────────
df["sale_date_pd"] = pd.to_datetime(df["sale_date"])
df["holiday_flag"] = df["sale_date_pd"].apply(
    lambda d: is_holiday(d.month, d.day)
)

# ─── 6. 添加辅助特征 ──────────────────────────────────────────
df["month"]       = df["sale_date_pd"].dt.month
df["week_of_year"]= df["sale_date_pd"].dt.isocalendar().week.astype(int)
df["year"]        = df["sale_date_pd"].dt.year

# 保留温度/CPI/失业率（可选特征，供后续销售预测使用）
out_cols = [
    "store_id", "city", "province", "tier",
    "sale_date", "year", "month", "week_of_year",
    "weekly_sales", "holiday_flag",
    "Temperature", "Fuel_Price", "CPI", "Unemployment"
]
df_out = df[out_cols].sort_values(["store_id", "sale_date"]).reset_index(drop=True)
df_out.to_csv(OUT_FILE, index=False, encoding="utf-8-sig")

print(f"\n✅ 完成！输出 {len(df_out):,} 行 → {OUT_FILE}")
print(f"  门店分布     : {df_out['store_id'].value_counts().to_dict()}")
print(f"  日期范围     : {df_out['sale_date'].min()} ~ {df_out['sale_date'].max()}")
print(f"  节假日周数   : {df_out['holiday_flag'].sum()}")
print(f"  周销售额(CNY): min={df_out['weekly_sales'].min():.0f}  "
      f"median={df_out['weekly_sales'].median():.0f}  max={df_out['weekly_sales'].max():.0f}")
