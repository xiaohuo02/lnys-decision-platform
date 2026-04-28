# -*- coding: utf-8 -*-
"""
07_quality_fix.py
数据质量优化 — 修复 EDA 发现的所有问题

修复项：
  [FIX-1] orders_cn    — 过滤批发大单(total_amount>10000 且 quantity>200)
  [FIX-2] customers_cn — 按 total_spend 重新分配会员等级
  [FIX-3] fraud_cn     — 添加 sample_weight 列（平衡欺诈率标注）
  [FIX-4] stores_offline — Temperature 华氏→摄氏；CPI/Unemployment 标记为参考值
  [FIX-5] chinese_reviews — 过滤电子/酒店类，合并外卖评论，生成 reviews_cn.csv

运行：.venv\Scripts\python scripts/07_quality_fix.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
import numpy as np
from pathlib import Path

PROC  = Path("data/processed")
GEN   = Path("data/generated")
RAW   = Path("data/raw")

SEED = 42
rng  = np.random.default_rng(SEED)

# ═══════════════════════════════════════════════════════════════
# FIX-1: orders_cn — 过滤批发大单
# ═══════════════════════════════════════════════════════════════
print("=" * 60)
print("[FIX-1] orders_cn — 过滤批发大单")
df_orders = pd.read_csv(PROC / "orders_cn.csv", parse_dates=["order_date"])
before = len(df_orders)

# 同时满足 quantity > 200 AND total_amount > 10000 才认定为批发单
wholesale_mask = (df_orders["quantity"] > 200) & (df_orders["total_amount"] > 10_000)
df_orders = df_orders[~wholesale_mask].copy()
after = len(df_orders)

# 进一步检查：单价异常（unit_price 不在 SKUS 预设范围内已在转换时修正，这里只校验）
price_check = df_orders["unit_price"].between(30, 600)
print(f"  单价在合理区间(30-600)的比例: {price_check.mean()*100:.2f}%")

df_orders.to_csv(PROC / "orders_cn.csv", index=False, encoding="utf-8-sig")
print(f"  过滤前: {before:,}  过滤后: {after:,}  移除批发单: {before-after:,}")
print(f"  total_amount 分位: { df_orders['total_amount'].quantile([0.5,.9,.99,.999]).round(0).to_dict() }")

# ═══════════════════════════════════════════════════════════════
# FIX-2: customers_cn — 按 total_spend 重新分配会员等级
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("[FIX-2] customers_cn — 重新分配会员等级")
df_cust = pd.read_csv(PROC / "customers_cn.csv")

# 重新从 FIX-1 清洗后的订单统计 total_spend（去掉批发后更准）
spend_map = (
    df_orders.groupby("customer_id")["total_amount"]
    .sum()
    .reset_index()
    .rename(columns={"total_amount": "total_spend_fixed"})
)
df_cust = df_cust.merge(spend_map, on="customer_id", how="left")
df_cust["total_spend"] = df_cust["total_spend_fixed"].fillna(0).round(2)
df_cust.drop(columns=["total_spend_fixed"], inplace=True)

# 按分位数分配，目标分布：普通50% / 银卡30% / 金卡15% / 钻石5%
p50 = df_cust["total_spend"].quantile(0.50)
p80 = df_cust["total_spend"].quantile(0.80)
p95 = df_cust["total_spend"].quantile(0.95)

def assign_level(spend):
    if spend >= p95: return "钻石"
    if spend >= p80: return "金卡"
    if spend >= p50: return "银卡"
    return "普通"

df_cust["member_level"] = df_cust["total_spend"].apply(assign_level)
print(f"  分位阈值 → 银卡≥¥{p50:.0f}  金卡≥¥{p80:.0f}  钻石≥¥{p95:.0f}")
print(f"  修正前分布: {{ '普通':原92%, '钻石':原0.1% }}")
print(f"  修正后分布: { df_cust['member_level'].value_counts().to_dict() }")
print(f"  total_spend 分位: { df_cust['total_spend'].quantile([0.5,.75,.9,.99]).round(0).to_dict() }")

df_cust.to_csv(PROC / "customers_cn.csv", index=False, encoding="utf-8-sig")
print(f"  ✅ 保存 {len(df_cust):,} 行")

# ═══════════════════════════════════════════════════════════════
# FIX-3: fraud_cn — 添加 sample_weight（平衡欺诈率偏高问题）
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("[FIX-3] fraud_cn — 添加 sample_weight 用于 ML 训练")
df_fraud = pd.read_csv(PROC / "fraud_cn.csv")

fraud_rate_actual = df_fraud["label"].mean()
# 目标欺诈率：0.5%（介于真实0.17%和合并后3.44%之间，更贴近中国支付欺诈实际）
# sample_weight 调整：让 ML 模型按接近真实欺诈率的权重训练
TARGET_FRAUD_RATE = 0.005
n_fraud  = (df_fraud["label"] == 1).sum()
n_normal = (df_fraud["label"] == 0).sum()

# 权重公式：正常样本权重=1，欺诈样本权重 = (TARGET/(1-TARGET)) / (n_fraud/n_normal)
weight_fraud  = (TARGET_FRAUD_RATE / (1 - TARGET_FRAUD_RATE)) / (n_fraud / n_normal)
weight_fraud  = round(weight_fraud, 6)

df_fraud["sample_weight"] = np.where(df_fraud["label"] == 1, weight_fraud, 1.0)

print(f"  当前欺诈率  : {fraud_rate_actual*100:.4f}%")
print(f"  目标欺诈率  : {TARGET_FRAUD_RATE*100:.2f}%（sample_weight 校正）")
print(f"  欺诈样本权重: {weight_fraud}  正常样本权重: 1.0")
print(f"  等效加权欺诈率: {(df_fraud['sample_weight']*df_fraud['label']).sum() / df_fraud['sample_weight'].sum() * 100:.4f}%")

df_fraud.to_csv(PROC / "fraud_cn.csv", index=False, encoding="utf-8-sig")
print(f"  ✅ 保存 {len(df_fraud):,} 行")

# ═══════════════════════════════════════════════════════════════
# FIX-4: stores_offline — 温度华氏→摄氏，添加数据来源标注
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("[FIX-4] stores_offline — Temperature 华氏→摄氏")
df_stores = pd.read_csv(PROC / "stores_offline.csv")

# 华氏 → 摄氏：C = (F - 32) × 5/9
if "Temperature" in df_stores.columns:
    df_stores["temperature_c"] = ((df_stores["Temperature"] - 32) * 5 / 9).round(1)
    df_stores.drop(columns=["Temperature"], inplace=True)

rename_map = {k: v for k, v in {
    "CPI":          "cpi_ref",
    "Unemployment": "unemployment_ref",
    "Fuel_Price":   "fuel_price_ref",
}.items() if k in df_stores.columns}
if rename_map:
    df_stores.rename(columns=rename_map, inplace=True)

print(f"  温度范围(°C): {df_stores['temperature_c'].min():.1f} ~ {df_stores['temperature_c'].max():.1f}")
print(f"  宏观特征已加 _ref 后缀标注为参考数据")

df_stores.to_csv(PROC / "stores_offline.csv", index=False, encoding="utf-8-sig")
print(f"  ✅ 保存 {len(df_stores):,} 行  列: {list(df_stores.columns)}")

# ═══════════════════════════════════════════════════════════════
# FIX-5: 中文评论 — 过滤不相关类别 + 合并外卖，生成 reviews_cn.csv
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("[FIX-5] 中文评论 — 过滤 + 合并 → reviews_cn.csv")

# 不相关类别：电子类(平板/手机/计算机)、酒店、书籍（与柠优商品无关）
IRRELEVANT_CATS = {"平板", "手机", "计算机", "酒店", "书籍"}
RELEVANT_CATS   = {"洗发水", "水果", "衣服", "蒙牛", "热水器"}

df_shop = pd.read_csv(RAW / "chinese_reviews/online_shopping_10_cats.csv", low_memory=False)
print(f"  online_shopping_10_cats 原始: {len(df_shop):,}行")
print(f"  类别分布:\n{df_shop['cat'].value_counts().to_string()}")

df_relevant = df_shop[~df_shop["cat"].isin(IRRELEVANT_CATS)].copy()
df_relevant["source"] = "shopping_" + df_relevant["cat"]
print(f"\n  过滤后（保留相关类别）: {len(df_relevant):,}行")

# 外卖评论（食品/健康类相关）
df_waimai = pd.read_csv(RAW / "chinese_reviews/waimai_10k.csv")
df_waimai["cat"] = "外卖"
df_waimai["source"] = "waimai"
print(f"  waimai_10k: {len(df_waimai):,}行")

# 合并
df_combined = pd.concat([
    df_relevant[["cat", "label", "review", "source"]],
    df_waimai[["cat", "label", "review", "source"]]
], ignore_index=True)

# 清洗：去除空评论、去重
df_combined = df_combined[df_combined["review"].notna()].copy()
df_combined = df_combined[df_combined["review"].astype(str).str.strip().str.len() >= 3]
df_combined = df_combined.drop_duplicates(subset=["review"])
df_combined = df_combined.reset_index(drop=True)

out_reviews = PROC / "reviews_cn.csv"
df_combined.to_csv(out_reviews, index=False, encoding="utf-8-sig")

print(f"\n  合并后: {len(df_combined):,}行")
print(f"  类别分布:\n{df_combined['cat'].value_counts().to_string()}")
print(f"  情感分布: { df_combined['label'].value_counts().to_dict() }")
print(f"  正评率: {df_combined['label'].mean()*100:.1f}%")
print(f"  ✅ 保存 → {out_reviews}")

# ═══════════════════════════════════════════════════════════════
# 同步更新 customers_cn 的 member_level 到 orders_cn
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("[SYNC] 同步会员等级回 orders_cn")
level_map = df_cust.set_index("customer_id")["member_level"]
df_orders["member_level"] = df_orders["customer_id"].map(level_map).fillna("普通")
df_orders.to_csv(PROC / "orders_cn.csv", index=False, encoding="utf-8-sig")
print(f"  orders_cn 会员等级分布: { df_orders['member_level'].value_counts().to_dict() }")

print("\n" + "=" * 60)
print("✅ 全部质量优化完成！")
