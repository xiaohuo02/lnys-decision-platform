# -*- coding: utf-8 -*-
"""
05_generate_inventory.py
基于订单数据反推每日库存快照（26 SKU × 8 门店 × 730天）
输出：data/generated/inventory.csv

逻辑：
  - 初始库存 = SKU 定价 × 系数（高价低存 / 低价高存）
  - 每日消耗 = 从 orders_cn 统计线下日销量（按 sku+store）
  - 每月1~2次随机补货事件（补货量 = EOQ 估算）
  - 输出字段：date / store_id / sku_code / stock_qty / daily_sold / reorder_point / replenished

运行：.venv\Scripts\python scripts/05_generate_inventory.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
import numpy as np
from pathlib import Path

from company_config import STORE_IDS, SKUS, SKU_CODES

ORDERS_FILE = Path("data/processed/orders_cn.csv")
OUT_FILE    = Path("data/generated/inventory.csv")
OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

SEED = 42
rng  = np.random.default_rng(SEED)

START_DATE = pd.Timestamp("2022-12-01")
END_DATE   = pd.Timestamp("2024-12-09")
ALL_DATES  = pd.date_range(START_DATE, END_DATE, freq="D")

# ─── 1. 读取线下订单日销量 ─────────────────────────────────────
print("读取订单数据，统计线下日销量...")
df_orders = pd.read_csv(ORDERS_FILE, parse_dates=["order_date"], low_memory=False)
offline = df_orders[df_orders["channel"] == "offline"].copy()
offline["date"] = offline["order_date"].dt.date

daily_sales = (
    offline.groupby(["date", "store_id", "sku_code"])["quantity"]
    .sum()
    .reset_index()
    .rename(columns={"quantity": "daily_sold"})
)
daily_sales["date"] = pd.to_datetime(daily_sales["date"])
print(f"  线下日销量记录: {len(daily_sales):,}")

# ─── 2. 初始库存设定 ──────────────────────────────────────────
def init_stock(sku_code: str) -> int:
    price = SKUS[sku_code]["unit_price"]
    if price < 100:    return int(rng.integers(200, 400))
    elif price < 200:  return int(rng.integers(100, 200))
    elif price < 300:  return int(rng.integers(50,  120))
    else:              return int(rng.integers(20,   60))

# 安全库存系数（Z=1.65，简化：固定为平均日销量×lead_time天）
LEAD_TIME  = 7   # 补货周期（天）
Z_SCORE    = 1.65

# ─── 3. 模拟每日库存 ──────────────────────────────────────────
print("模拟库存快照（26 SKU × 8 门店 × ~730天）...")

records = []
for store_id in STORE_IDS:
    for sku_code in SKU_CODES:
        stock = init_stock(sku_code)

        # 该 sku+store 的历史日销量序列
        hist = daily_sales[
            (daily_sales["store_id"] == store_id) &
            (daily_sales["sku_code"] == sku_code)
        ].set_index("date")["daily_sold"]

        # 估算平均日销量和标准差（用于安全库存计算）
        if len(hist) > 7:
            avg_daily = hist.mean()
            std_daily = hist.std()
        else:
            avg_daily = max(1, rng.integers(1, 5))
            std_daily = avg_daily * 0.3

        reorder_point = int(avg_daily * LEAD_TIME + Z_SCORE * std_daily * (LEAD_TIME ** 0.5))
        reorder_point = max(reorder_point, 5)

        # 每月补货次数（1-2次），在月初随机抽取
        replenish_dates = set()
        for year in [2022, 2023, 2024]:
            for month in range(1, 13):
                n_events = int(rng.integers(1, 3))
                for _ in range(n_events):
                    day = int(rng.integers(1, 28))
                    try:
                        replenish_dates.add(pd.Timestamp(year, month, day))
                    except ValueError:
                        pass

        eoq = max(int(avg_daily * 30), 10)   # 简化 EOQ ≈ 30天用量

        for date in ALL_DATES:
            sold = int(hist.get(date, 0))

            # 补货
            replenished = 0
            if date in replenish_dates:
                replenished = int(rng.integers(int(eoq * 0.8), int(eoq * 1.2) + 1))
                stock += replenished

            # 消耗（不能低于0）
            sold = min(sold, stock)
            stock = max(stock - sold, 0)

            records.append({
                "date":          date.date(),
                "store_id":      store_id,
                "sku_code":      sku_code,
                "stock_qty":     stock,
                "daily_sold":    sold,
                "reorder_point": reorder_point,
                "replenished":   replenished,
            })

df_out = pd.DataFrame(records)
df_out.to_csv(OUT_FILE, index=False, encoding="utf-8-sig")

print(f"\n✅ 完成！输出 {len(df_out):,} 行 → {OUT_FILE}")
print(f"  日期范围     : {df_out['date'].min()} ~ {df_out['date'].max()}")
print(f"  补货事件总数 : {(df_out['replenished'] > 0).sum():,}")
print(f"  库存为0次数  : {(df_out['stock_qty'] == 0).sum():,} 次（缺货预警参考）")
print(f"  平均库存     : {df_out['stock_qty'].mean():.1f}")
