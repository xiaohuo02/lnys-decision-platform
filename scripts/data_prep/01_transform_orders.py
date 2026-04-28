# -*- coding: utf-8 -*-
"""
01_transform_orders.py
UCI Online Retail II → 柠优生活订单数据（中国化）
输出：data/processed/orders_cn.csv

过滤规则：
  - 去除退货单（Invoice 以 C 开头）
  - 去除 Price ≤ 0 / Quantity ≤ 0
  - 去除 Customer ID 为空的匿名行
  - 去除重复行

字段改写：
  - InvoiceDate → order_date（+13年偏移）
  - Description+Price → sku_code（关键词/价格区间映射）
  - unit_price  → SKU 预设人民币价格
  - total_amount = unit_price × Quantity
  - 新增：channel / store_id / ship_city / ship_province / payment_method / member_level / customer_id

运行：.venv\Scripts\python scripts/01_transform_orders.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
import numpy as np
from pathlib import Path
from dateutil.relativedelta import relativedelta

from company_config import (
    STORES, STORE_IDS, ONLINE_CITIES, ONLINE_WEIGHTS, CITY_PROVINCE_MAP,
    PAYMENT_METHODS, PAYMENT_WEIGHTS, MEMBER_LEVELS, MEMBER_WEIGHTS,
    DATE_SHIFT_YEARS, map_description_to_sku, get_sku_price, SKUS
)

RAW_FILE   = Path("data/raw/online_retail_II/online_retail_II.csv")
OUT_FILE   = Path("data/processed/orders_cn.csv")
OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

SEED = 42
rng  = np.random.default_rng(SEED)

# ─── 1. 读取原始数据 ──────────────────────────────────────────
print("读取原始数据...")
df = pd.read_csv(RAW_FILE, encoding="utf-8", low_memory=False)
print(f"  原始行数: {len(df):,}")

# ─── 2. 过滤无效行 ────────────────────────────────────────────
df = df.drop_duplicates()
df = df[~df["Invoice"].astype(str).str.startswith("C")]   # 去退货单
df = df[df["Quantity"] > 0]
df = df[df["Price"] > 0]
df = df[df["Customer ID"].notna()]
print(f"  过滤后行数: {len(df):,}")

# ─── 3. 日期偏移（2009-2011 → 2022-2024）─────────────────────
print("日期偏移 +13年...")
df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"], errors="coerce")
df = df[df["InvoiceDate"].notna()]
df["order_date"] = df["InvoiceDate"].apply(
    lambda d: d + relativedelta(years=DATE_SHIFT_YEARS)
)

# ─── 4. 商品描述 → SKU + 人民币价格 ──────────────────────────
print("商品映射 → SKU...")
df["sku_code"] = df.apply(
    lambda r: map_description_to_sku(r["Description"], r["Price"]), axis=1
)
df["unit_price"]   = df["sku_code"].map(get_sku_price)
df["total_amount"] = (df["unit_price"] * df["Quantity"]).round(2)
df["sku_name"]     = df["sku_code"].map(lambda c: SKUS.get(c, {}).get("name", ""))
df["category"]     = df["sku_code"].map(lambda c: SKUS.get(c, {}).get("category", ""))

# ─── 5. 渠道分配（online 70% / offline 30%）─────────────────
n = len(df)
df["channel"] = rng.choice(["online", "offline"], size=n, p=[0.70, 0.30])

# ─── 6. 门店分配（offline 订单）──────────────────────────────
offline_mask = df["channel"] == "offline"
df["store_id"] = ""
df.loc[offline_mask, "store_id"] = rng.choice(STORE_IDS, size=offline_mask.sum())

# ─── 7. 收货城市 ──────────────────────────────────────────────
df["ship_city"]     = ""
df["ship_province"] = ""

# 线上：全国加权随机
online_mask = df["channel"] == "online"
online_cities = rng.choice(ONLINE_CITIES, size=online_mask.sum(), p=ONLINE_WEIGHTS)
df.loc[online_mask, "ship_city"]     = online_cities
df.loc[online_mask, "ship_province"] = pd.Series(online_cities).map(CITY_PROVINCE_MAP).values

# 线下：门店所在城市
for store_id, info in STORES.items():
    mask = df["store_id"] == store_id
    df.loc[mask, "ship_city"]     = info["city"]
    df.loc[mask, "ship_province"] = info["province"]

# ─── 8. 支付方式 & 会员等级 ───────────────────────────────────
df["payment_method"] = rng.choice(PAYMENT_METHODS, size=n, p=PAYMENT_WEIGHTS)
df["member_level"]   = rng.choice(MEMBER_LEVELS,   size=n, p=MEMBER_WEIGHTS)

# ─── 9. 标准化 Customer ID → LY + 6位 ────────────────────────
uid_map = {
    uid: f"LY{str(i+1).zfill(6)}"
    for i, uid in enumerate(sorted(df["Customer ID"].unique()))
}
df["customer_id"] = df["Customer ID"].map(uid_map)

# ─── 10. 生成 order_id ──────────────────────────────────────
df = df.reset_index(drop=True)
df["order_id"] = df.apply(
    lambda r: f"ORD{r['Invoice']}-{r.name:05d}", axis=1
)

# ─── 11. 输出 ──────────────────────────────────────────────
out_cols = [
    "order_id", "customer_id", "sku_code", "sku_name", "category",
    "quantity", "unit_price", "total_amount",
    "channel", "store_id", "ship_city", "ship_province",
    "payment_method", "member_level", "order_date"
]
df_out = df.rename(columns={"Quantity": "quantity"})[out_cols]
df_out.to_csv(OUT_FILE, index=False, encoding="utf-8-sig")

print(f"\n✅ 完成！输出 {len(df_out):,} 行 → {OUT_FILE}")
print(f"  唯一客户数    : {df_out['customer_id'].nunique():,}")
print(f"  日期范围      : {df_out['order_date'].min()} ~ {df_out['order_date'].max()}")
print(f"  渠道分布      : {df_out['channel'].value_counts().to_dict()}")
print(f"  SKU分布(top5) : {df_out['sku_code'].value_counts().head(5).to_dict()}")
print(f"  total_amount  : min={df_out['total_amount'].min()}  median={df_out['total_amount'].median():.1f}  max={df_out['total_amount'].max()}")
