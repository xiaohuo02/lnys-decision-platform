# -*- coding: utf-8 -*-
"""
柠优生活 - 全量数据集 EDA 分析脚本
运行方式：.venv\Scripts\python scripts/eda_analysis.py
"""

import pandas as pd
import numpy as np
from pathlib import Path

RAW = Path("data/raw")
SEP = "=" * 68

def sep(title):
    print(f"\n{SEP}\n  {title}\n{SEP}")

def basic(df, sample_cats=8):
    print(f"  形状     : {df.shape[0]:,} 行 × {df.shape[1]} 列")
    print(f"  内存     : {df.memory_usage(deep=True).sum()/1e6:.1f} MB")
    print(f"  重复行   : {df.duplicated().sum():,}")
    print("\n  字段概览:")
    miss = df.isnull().sum()
    for col in df.columns:
        dtype = str(df[col].dtype)
        m = miss[col]
        mp = f"{m/len(df)*100:.1f}%" if m else "—"
        if pd.api.types.is_numeric_dtype(df[col]):
            extra = (f"min={df[col].min():.2g}  "
                     f"mean={df[col].mean():.2g}  "
                     f"max={df[col].max():.2g}  "
                     f"std={df[col].std():.2g}")
        elif pd.api.types.is_datetime64_any_dtype(df[col]):
            extra = f"min={df[col].min()}  max={df[col].max()}"
        else:
            nuniq = df[col].nunique()
            if nuniq <= sample_cats:
                vals = df[col].value_counts().head(sample_cats).to_dict()
                extra = f"nuniq={nuniq}  vals={vals}"
            else:
                top = df[col].value_counts().head(3).index.tolist()
                extra = f"nuniq={nuniq}  top3={top}"
        miss_tag = f"  缺失={mp}" if m else ""
        print(f"    {col:<35} [{dtype:>10}]{miss_tag}  {extra}")


# ──────────────────────────────────────────────
# 1. UCI Online Retail II
# ──────────────────────────────────────────────
sep("1. UCI Online Retail II  →  订单主体 / RFM / 销售预测")
df_oci = pd.read_csv(RAW / "online_retail_II/online_retail_II.csv", encoding="utf-8", low_memory=False)
basic(df_oci)
print("\n  日期范围:")
df_oci["InvoiceDate"] = pd.to_datetime(df_oci["InvoiceDate"], errors="coerce")
print(f"    {df_oci['InvoiceDate'].min()} ~ {df_oci['InvoiceDate'].max()}")
print(f"  唯一客户数 : {df_oci['Customer ID'].nunique():,}")
print(f"  唯一发票数 : {df_oci['Invoice'].nunique():,}")
print(f"  退货单(C开头): {df_oci['Invoice'].astype(str).str.startswith('C').sum():,}")
print(f"  Price≤0行数 : {(df_oci['Price']<=0).sum():,}")
print(f"  Quantity≤0行: {(df_oci['Quantity']<=0).sum():,}")
print(f"  Price分位数 : {df_oci['Price'].quantile([0,.25,.5,.75,.9,.99]).to_dict()}")
print(f"  Quantity分位: {df_oci['Quantity'].quantile([0,.25,.5,.75,.9,.99]).to_dict()}")
print(f"  国家分布(top5): {df_oci['Country'].value_counts().head(5).to_dict()}")


# ──────────────────────────────────────────────
# 2. Credit Card Fraud 经典版
# ──────────────────────────────────────────────
sep("2. Credit Card Fraud 经典版  →  欺诈风控")
df_cc = pd.read_csv(RAW / "creditcard/creditcard.csv")
basic(df_cc)
fraud_cnt = df_cc["Class"].value_counts()
print(f"\n  欺诈分布 : {fraud_cnt.to_dict()}")
print(f"  欺诈率   : {fraud_cnt[1]/len(df_cc)*100:.4f}%")
print(f"  Amount分位: {df_cc['Amount'].quantile([0,.25,.5,.75,.9,.99,.999]).round(2).to_dict()}")
print(f"  Time范围  : {df_cc['Time'].min():.0f} ~ {df_cc['Time'].max():.0f} 秒")
print(f"  特征列   : V1~V28 (PCA匿名) + Time + Amount + Class")


# ──────────────────────────────────────────────
# 3. Credit Card Fraud 2023
# ──────────────────────────────────────────────
sep("3. Credit Card Fraud 2023  →  欺诈风控补充")
df_cc23 = pd.read_csv(RAW / "creditcard_2023/creditcard_2023.csv")
basic(df_cc23)
fraud_cnt23 = df_cc23["Class"].value_counts()
print(f"\n  欺诈分布 : {fraud_cnt23.to_dict()}")
print(f"  欺诈率   : {fraud_cnt23[1]/len(df_cc23)*100:.4f}%")
print(f"  Amount分位: {df_cc23['Amount'].quantile([0,.25,.5,.75,.9,.99]).round(2).to_dict()}")
print(f"  列名对比(vs经典版): {set(df_cc23.columns) - set(df_cc.columns)}")


# ──────────────────────────────────────────────
# 4. E-Commerce Customer Churn
# ──────────────────────────────────────────────
sep("4. E-Commerce Customer Churn  →  客户流失预测")
df_churn = pd.read_excel(RAW / "ecommerce_churn/E Commerce Dataset.xlsx",
                         sheet_name=None)
print(f"  Sheet列表: {list(df_churn.keys())}")
df_churn = df_churn[list(df_churn.keys())[0]]
basic(df_churn)
if "Churn" in df_churn.columns:
    print(f"\n  流失分布 : {df_churn['Churn'].value_counts().to_dict()}")
    print(f"  流失率   : {df_churn['Churn'].mean()*100:.2f}%")


# ──────────────────────────────────────────────
# 5. E-Commerce Shipping (prachi13/customer-analytics)
# ──────────────────────────────────────────────
sep("5. E-Commerce Shipping  →  物流分析")
df_ship = pd.read_csv(RAW / "ecommerce_shipping/Train.csv")
basic(df_ship)
if "Reached.on.Time_Y.N" in df_ship.columns:
    print(f"\n  准时到达分布: {df_ship['Reached.on.Time_Y.N'].value_counts().to_dict()}")


# ──────────────────────────────────────────────
# 6. Walmart Store Sales
# ──────────────────────────────────────────────
sep("6. Walmart Store Sales  →  线下门店销售预测")
df_wmt = pd.read_csv(RAW / "walmart_sales/Walmart_Sales.csv")
basic(df_wmt)
print(f"\n  门店数   : {df_wmt['Store'].nunique()}")
print(f"  日期范围 : {df_wmt['Date'].min()} ~ {df_wmt['Date'].max()}")
print(f"  周数     : {df_wmt['Date'].nunique()}")
print(f"  Weekly_Sales分位: {df_wmt['Weekly_Sales'].quantile([0,.25,.5,.75,.9,.99]).round(0).to_dict()}")
print(f"  Holiday_Flag分布: {df_wmt['Holiday_Flag'].value_counts().to_dict()}")


# ──────────────────────────────────────────────
# 7. ChineseNlpCorpus 在线购物评论
# ──────────────────────────────────────────────
sep("7. ChineseNlpCorpus 在线购物评论  →  舆情情感分析")
df_rev = pd.read_csv(RAW / "chinese_reviews/online_shopping_10_cats.csv",
                     encoding="utf-8", low_memory=False)
basic(df_rev)
if "cat" in df_rev.columns:
    print(f"\n  商品类别分布:\n{df_rev['cat'].value_counts().to_string()}")
if "label" in df_rev.columns:
    print(f"\n  情感标签分布: {df_rev['label'].value_counts().to_dict()}")
    print(f"  正负比例    : {df_rev['label'].mean()*100:.1f}% 正评")
if "review" in df_rev.columns:
    rev_len = df_rev["review"].dropna().str.len()
    print(f"\n  评论长度(字符): min={rev_len.min()}  median={rev_len.median():.0f}  max={rev_len.max()}")
    print(f"  空评论数    : {df_rev['review'].isnull().sum()}")


# ──────────────────────────────────────────────
# 汇总
# ──────────────────────────────────────────────
sep("EDA 完成 — 汇总")
summaries = [
    ("UCI Online Retail II",     f"{len(df_oci):,}行",  "Invoice/InvoiceDate/Quantity/Price/Customer ID/Country"),
    ("Credit Card Fraud 经典",   f"{len(df_cc):,}行",   "Time/V1-V28/Amount/Class"),
    ("Credit Card Fraud 2023",   f"{len(df_cc23):,}行", f"V1-V28/Amount/Class  (欺诈率{fraud_cnt23[1]/len(df_cc23)*100:.2f}%)"),
    ("E-Commerce Churn",         f"{len(df_churn):,}行", "Churn标签+20特征"),
    ("E-Commerce Shipping",      f"{len(df_ship):,}行",  "10999条物流特征"),
    ("Walmart Sales",            f"{len(df_wmt):,}行",   "Store/Date/Weekly_Sales/Holiday_Flag/..."),
    ("ChineseNlp 购物评论",      f"{len(df_rev):,}行",   "cat(10类)/label(0/1)/review"),
]
for name, size, note in summaries:
    print(f"  ✅ {name:<25} {size:<12}  {note}")
