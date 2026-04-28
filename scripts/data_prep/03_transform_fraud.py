# -*- coding: utf-8 -*-
"""
03_transform_fraud.py
Credit Card Fraud 经典版(0.17%) + 2023版(50%平衡) → 柠优欺诈数据
输出：data/processed/fraud_cn.csv

改写规则：
  - Amount 分位数映射到中国支付金额分布
  - 新增：payment_method / city / device_type / merchant_category / hour_of_day
  - 2023版(平衡集)：下采样至约1:10比例后合并，扩充欺诈样本多样性

运行：.venv\Scripts\python scripts/03_transform_fraud.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
import numpy as np
from pathlib import Path

from company_config import (
    ONLINE_CITIES, ONLINE_WEIGHTS, CITY_PROVINCE_MAP,
    PAYMENT_METHODS, SKUS
)

RAW_CLASSIC = Path("data/raw/creditcard/creditcard.csv")
RAW_2023    = Path("data/raw/creditcard_2023/creditcard_2023.csv")
OUT_FILE    = Path("data/processed/fraud_cn.csv")
OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

SEED = 42
rng  = np.random.default_rng(SEED)

# 中国支付金额分位数目标分布
CN_AMOUNT_QUANTILES = {
    0.60: (50,   500),    # 日常消费
    0.85: (500,  2000),   # 中等消费
    0.99: (2000, 8000),   # 大额
    1.00: (8000, 50000),  # 超大额
}

def map_amount_to_cny(series: pd.Series) -> pd.Series:
    """将原始 Amount 按分位数映射到人民币区间"""
    quantiles = series.quantile([0.60, 0.85, 0.99, 1.00])
    result = pd.Series(index=series.index, dtype=float)
    for thresh, (lo, hi) in zip([0.60, 0.85, 0.99, 1.00],
                                 [(50, 500), (500, 2000), (2000, 8000), (8000, 50000)]):
        if thresh == 0.60:
            mask = series <= quantiles[thresh]
        elif thresh == 1.00:
            mask = series > quantiles[0.99]
        else:
            prev_thresh = [0.60, 0.85, 0.99, 1.00][[0.60, 0.85, 0.99, 1.00].index(thresh) - 1]
            mask = (series > quantiles[prev_thresh]) & (series <= quantiles[thresh])
        n = mask.sum()
        if n > 0:
            result[mask] = rng.uniform(lo, hi, size=n).round(2)
    return result

def add_cn_fields(df: pd.DataFrame) -> pd.DataFrame:
    n = len(df)
    df["amount_cny"]         = map_amount_to_cny(df["Amount"])
    df["payment_method"]     = rng.choice(
        ["支付宝", "微信支付", "银行卡"], size=n, p=[0.50, 0.35, 0.15]
    )
    df["city"]               = rng.choice(ONLINE_CITIES, size=n, p=ONLINE_WEIGHTS)
    df["province"]           = df["city"].map(CITY_PROVINCE_MAP)
    df["device_type"]        = rng.choice(
        ["mobile", "PC", "POS"], size=n, p=[0.65, 0.25, 0.10]
    )
    merchant_cats = [s["category"] for s in SKUS.values()]
    df["merchant_category"]  = rng.choice(merchant_cats, size=n)
    df["hour_of_day"]        = (df["Time"] % 86400 / 3600).astype(int) if "Time" in df.columns \
                                else rng.integers(0, 24, size=n)
    return df

# ─── 1. 读取经典版（0.17%真实欺诈率）────────────────────────
print("读取 Credit Card Fraud 经典版...")
df_classic = pd.read_csv(RAW_CLASSIC)
print(f"  行数: {len(df_classic):,}  欺诈率: {df_classic['Class'].mean()*100:.4f}%")
df_classic = add_cn_fields(df_classic)
df_classic["source"] = "classic"

# ─── 2. 读取 2023版（50%平衡集）──────────────────────────────
print("读取 Credit Card Fraud 2023 版...")
df_2023 = pd.read_csv(RAW_2023)
print(f"  行数: {len(df_2023):,}  欺诈率: {df_2023['Class'].mean()*100:.2f}%")

# 2023版下采样：取欺诈样本全部 + 等量非欺诈样本（约1:1用于补充）
# 只补充2万条（1万欺诈+1万正常）扩充欺诈多样性
fraud_2023    = df_2023[df_2023["Class"] == 1].sample(10000, random_state=SEED)
normal_2023   = df_2023[df_2023["Class"] == 0].sample(10000, random_state=SEED)
df_2023_sub   = pd.concat([fraud_2023, normal_2023]).sample(frac=1, random_state=SEED)
df_2023_sub   = add_cn_fields(df_2023_sub)
df_2023_sub["source"] = "2023"
print(f"  2023版子集: {len(df_2023_sub):,}  欺诈={df_2023_sub['Class'].sum()}")

# ─── 3. 合并 ─────────────────────────────────────────────────
df_all = pd.concat([df_classic, df_2023_sub], ignore_index=True)
df_all = df_all.sample(frac=1, random_state=SEED).reset_index(drop=True)

# ─── 4. 生成 transaction_id ──────────────────────────────────
df_all["transaction_id"] = [f"TXN{i:08d}" for i in range(len(df_all))]

# ─── 5. 输出 ─────────────────────────────────────────────────
v_cols = [c for c in df_all.columns if c.startswith("V")]
out_cols = (
    ["transaction_id"] + v_cols +
    ["amount_cny", "payment_method", "city", "province",
     "device_type", "merchant_category", "hour_of_day", "Class", "source"]
)
df_out = df_all[out_cols].rename(columns={"Class": "label"})
df_out.to_csv(OUT_FILE, index=False, encoding="utf-8-sig")

fraud_rate = df_out["label"].mean() * 100
print(f"\n✅ 完成！输出 {len(df_out):,} 行 → {OUT_FILE}")
print(f"  欺诈率        : {fraud_rate:.4f}%")
print(f"  金额分布(CNY) : min={df_out['amount_cny'].min():.0f}  "
      f"median={df_out['amount_cny'].median():.0f}  max={df_out['amount_cny'].max():.0f}")
print(f"  来源分布      : {df_out['source'].value_counts().to_dict()}")
