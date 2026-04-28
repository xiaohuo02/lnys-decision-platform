# -*- coding: utf-8 -*-
"""17_inventory.py — ABC-XYZ 矩阵 + EOQ + 动态安全库存"""
import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent.parent))
import pandas as pd, numpy as np
from ml.config import *

OUT = RES_OPS / "inventory_analysis.csv"
if OUT.exists(): print("SKIP"); exit(0)

print("[17] 读取库存和订单数据...")
df_inv = pd.read_csv(INVENTORY_CSV)
df_ord = pd.read_csv(ORDERS_CSV, parse_dates=["order_date"], low_memory=False)

# ABC 分析：按 SKU 总销售额贡献
sku_sales = df_ord.groupby("sku_code")["total_amount"].sum().sort_values(ascending=False)
cumsum_pct = sku_sales.cumsum() / sku_sales.sum()
abc = pd.cut(cumsum_pct, bins=[0, 0.70, 0.90, 1.0], labels=["A","B","C"])
abc_df = pd.DataFrame({"sku_code": sku_sales.index, "total_sales": sku_sales.values, "ABC": abc.values})

# XYZ 分析：按需求波动系数 (CV)
daily_sku = (df_ord.groupby([df_ord["order_date"].dt.date, "sku_code"])["quantity"]
             .sum().reset_index())
cv_df = (daily_sku.groupby("sku_code")["quantity"]
         .agg(mean_demand="mean", std_demand="std")
         .reset_index())
cv_df["CV"] = cv_df["std_demand"] / (cv_df["mean_demand"] + 1e-6)
cv_df["XYZ"] = pd.cut(cv_df["CV"], bins=[0,0.5,1.0,np.inf], labels=["X","Y","Z"])

# 合并 ABC-XYZ
result = abc_df.merge(cv_df, on="sku_code")
result["matrix"] = result["ABC"].astype(str) + result["XYZ"].astype(str)
print("[17] ABC-XYZ 矩阵:")
print(result.groupby("matrix").size().sort_index().to_string())

# EOQ 计算
ORDER_COST  = 200   # 每次订货固定成本（元）
HOLD_RATE   = 0.20  # 年持有成本率
for i, row in result.iterrows():
    price = df_ord[df_ord["sku_code"]==row["sku_code"]]["unit_price"].median()
    D = row["mean_demand"] * 365
    H = price * HOLD_RATE
    result.at[i, "eoq"] = round(np.sqrt(2 * D * ORDER_COST / (H + 1e-6)), 0)

# 动态安全库存
Z_SCORE   = 1.65
LEAD_TIME = 7
result["safety_stock"] = (Z_SCORE * result["std_demand"] * np.sqrt(LEAD_TIME)).round(0)
result["reorder_point"] = (result["mean_demand"] * LEAD_TIME + result["safety_stock"]).round(0)

# 缺货统计
stockout_rate = (df_inv["stock_qty"] == 0).mean()
print(f"\n[17] 整体缺货率: {stockout_rate*100:.2f}%")

result.to_csv(OUT, index=False, encoding="utf-8-sig")
print(f"[17] ✅ 库存分析完成 → {OUT}")
print(result[["sku_code","ABC","XYZ","matrix","eoq","safety_stock","reorder_point"]].head(10).to_string())
import os; os._exit(0)
