# -*- coding: utf-8 -*-
"""
02_generate_customers.py
从 orders_cn.csv 提取唯一客户 → 生成中文客户档案
输出：data/processed/customers_cn.csv

运行：.venv\Scripts\python scripts/02_generate_customers.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import timedelta
from faker import Faker

from company_config import MEMBER_LEVELS, MEMBER_WEIGHTS, CITY_PROVINCE_MAP

ORDERS_FILE = Path("data/processed/orders_cn.csv")
OUT_FILE    = Path("data/processed/customers_cn.csv")

SEED = 42
fake = Faker("zh_CN")
Faker.seed(SEED)
rng  = np.random.default_rng(SEED)

# ─── 1. 读取订单数据 ──────────────────────────────────────────
print("读取订单数据...")
df = pd.read_csv(ORDERS_FILE, parse_dates=["order_date"], low_memory=False)
print(f"  订单行数: {len(df):,}，唯一客户: {df['customer_id'].nunique():,}")

# ─── 2. 每位客户的基础统计 ────────────────────────────────────
print("计算客户统计信息...")
cust_stats = (
    df.groupby("customer_id")
    .agg(
        first_order_date = ("order_date", "min"),
        last_order_date  = ("order_date", "max"),
        order_count      = ("order_id",   "nunique"),
        total_spend      = ("total_amount", "sum"),
        main_channel     = ("channel",  lambda x: x.mode()[0]),
        main_city        = ("ship_city", lambda x: x.mode()[0]),
        member_level     = ("member_level", lambda x: x.mode()[0]),
    )
    .reset_index()
)
print(f"  提取客户数: {len(cust_stats):,}")

# ─── 3. 用 faker 生成个人信息 ─────────────────────────────────
print("生成客户档案（faker zh_CN）...")
records = []
for _, row in cust_stats.iterrows():
    # register_date = 首次下单日 - 随机 0~180 天
    days_back     = int(rng.integers(0, 181))
    register_date = (row["first_order_date"] - timedelta(days=days_back)).date()

    # 城市/省份 来自该客户最常出现的 ship_city
    city     = row["main_city"]
    province = CITY_PROVINCE_MAP.get(city, "其他")

    records.append({
        "customer_id":   row["customer_id"],
        "name":          fake.name(),
        "phone":         fake.phone_number(),
        "email":         fake.free_email(),
        "gender":        rng.choice(["男", "女"], p=[0.48, 0.52]),
        "city":          city,
        "province":      province,
        "member_level":  row["member_level"],
        "register_date": register_date,
        "channel":       row["main_channel"],
        "order_count":   row["order_count"],
        "total_spend":   round(row["total_spend"], 2),
        "first_order":   row["first_order_date"].date(),
        "last_order":    row["last_order_date"].date(),
    })

df_out = pd.DataFrame(records)

# ─── 4. 输出 ─────────────────────────────────────────────────
df_out.to_csv(OUT_FILE, index=False, encoding="utf-8-sig")

print(f"\n✅ 完成！输出 {len(df_out):,} 行 → {OUT_FILE}")
print(f"  会员等级分布  : {df_out['member_level'].value_counts().to_dict()}")
print(f"  城市分布(top5): {df_out['city'].value_counts().head(5).to_dict()}")
print(f"  注册时间范围  : {df_out['register_date'].min()} ~ {df_out['register_date'].max()}")
