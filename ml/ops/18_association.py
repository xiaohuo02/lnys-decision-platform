# -*- coding: utf-8 -*-
"""18_association.py — FP-Growth + Apriori 关联规则挖掘"""
import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent.parent))
import pandas as pd, numpy as np
from mlxtend.frequent_patterns import fpgrowth, apriori, association_rules
from mlxtend.preprocessing import TransactionEncoder
from ml.config import *

OUT = RES_OPS / "association_rules.csv"
if OUT.exists(): print("SKIP"); exit(0)

print("[18] 读取订单数据，构建客户购物篮（按客户历史全部购买）...")
df = pd.read_csv(ORDERS_CSV, low_memory=False)
# 每单只有1个SKU，改用客户历史全量购买作为篮子
basket = df.groupby("customer_id")["sku_code"].apply(list).reset_index()
# 去除重复SKU（同客户买了多次同款，只保留一次）
basket["sku_code"] = basket["sku_code"].apply(lambda x: list(set(x)))
basket = basket[basket["sku_code"].apply(len) >= 2]  # 至少买过2个不同SKU
print(f"  有效客户篮数: {len(basket):,}")

# FP-Growth 全量（先跑，速度快且保存主要结果）
print("[18] FP-Growth 全量数据...")
te2   = TransactionEncoder()
te_arr2 = te2.fit_transform(basket["sku_code"].tolist())
df_enc  = pd.DataFrame(te_arr2, columns=te2.columns_)
freq_items = fpgrowth(df_enc, min_support=0.20, use_colnames=True, max_len=3)
print(f"  频繁项集数: {len(freq_items)}")
rules = association_rules(freq_items, metric="lift", min_threshold=1.0, num_itemsets=len(freq_items))
rules = rules.sort_values("lift", ascending=False)


print(f"  FP-Growth 规则数: {len(rules)}")
print(f"\n  Top 5 关联规则:")
for _, r in rules.head(5).iterrows():
    ant = list(r["antecedents"]); con = list(r["consequents"])
    print(f"    {ant} → {con}  conf={r['confidence']:.2f}  lift={r['lift']:.2f}")

rules.to_csv(OUT, index=False)
print(f"[18] ✅ 关联分析完成 → {OUT}")
import os; os._exit(0)
