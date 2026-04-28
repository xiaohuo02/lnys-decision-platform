# -*- coding: utf-8 -*-
"""
08_quality_check.py
全数据集综合质检报告
运行：.venv\Scripts\python scripts/08_quality_check.py
"""

import pandas as pd
import numpy as np
from pathlib import Path

PROC = Path("data/processed")
GEN  = Path("data/generated")
RAW  = Path("data/raw")

PASS = "✅"
WARN = "⚠️ "
FAIL = "❌"

issues = []

def check(label, condition, detail="", level="WARN"):
    icon = PASS if condition else (WARN if level == "WARN" else FAIL)
    status = "OK" if condition else level
    print(f"  {icon} [{status:4s}] {label}")
    if detail:
        print(f"         {detail}")
    if not condition:
        issues.append((level, label, detail))

def sep(title):
    print(f"\n{'='*60}\n  {title}\n{'='*60}")

# ══════════════════════════════════════════════
# 1. orders_cn.csv
# ══════════════════════════════════════════════
sep("1. orders_cn.csv — 订单主体")
df_o = pd.read_csv(PROC / "orders_cn.csv", parse_dates=["order_date"])
n = len(df_o)

check("行数充足(>700000)",        n > 700_000,           f"实际: {n:,}")
check("无缺失值(关键列)",
      df_o[["order_id","customer_id","sku_code","order_date","total_amount"]].isnull().sum().sum() == 0,
      f"关键列缺失: {df_o[['order_id','customer_id','sku_code','order_date','total_amount']].isnull().sum().to_dict()}")
check("无重复 order_id",          df_o["order_id"].duplicated().sum() == 0,
      f"重复数: {df_o['order_id'].duplicated().sum()}")
check("total_amount > 0",         (df_o["total_amount"] > 0).all(),
      f"≤0行数: {(df_o['total_amount']<=0).sum()}")
check("total_amount 无极端值(p99<2万)", df_o["total_amount"].quantile(0.99) < 20_000,
      f"p99={df_o['total_amount'].quantile(0.99):.0f}  p999={df_o['total_amount'].quantile(0.999):.0f}")
check("日期范围 2022-2024",
      df_o["order_date"].min().year >= 2022 and df_o["order_date"].max().year <= 2025,
      f"{df_o['order_date'].min().date()} ~ {df_o['order_date'].max().date()}")
check("渠道分布合理(online 60-80%)",
      0.60 <= (df_o["channel"]=="online").mean() <= 0.80,
      f"online={( df_o['channel']=='online').mean()*100:.1f}%  offline={(df_o['channel']=='offline').mean()*100:.1f}%")
check("SKU分布(最大SKU占比<30%)",
      df_o["sku_code"].value_counts(normalize=True).iloc[0] < 0.30,
      f"top-SKU: {df_o['sku_code'].value_counts().index[0]} = {df_o['sku_code'].value_counts(normalize=True).iloc[0]*100:.1f}%")
print(f"  唯一客户: {df_o['customer_id'].nunique():,}  唯一SKU: {df_o['sku_code'].nunique()}")

# ══════════════════════════════════════════════
# 2. customers_cn.csv
# ══════════════════════════════════════════════
sep("2. customers_cn.csv — 客户档案")
df_c = pd.read_csv(PROC / "customers_cn.csv")
nc = len(df_c)

check("行数与订单客户数一致",      nc == df_o["customer_id"].nunique(),
      f"客户表:{nc:,}  订单唯一客户:{df_o['customer_id'].nunique():,}")
check("无缺失值",                  df_c.isnull().sum().sum() == 0,
      f"缺失: {df_c.isnull().sum()[df_c.isnull().sum()>0].to_dict()}")
check("性别分布均衡(40-60%)",
      0.40 <= (df_c["gender"]=="女").mean() <= 0.60,
      f"女:{(df_c['gender']=='女').mean()*100:.1f}%  男:{(df_c['gender']=='男').mean()*100:.1f}%")
level_dist = df_c["member_level"].value_counts(normalize=True)
check("普通会员占比 40-70%",
      0.40 <= level_dist.get("普通", 0) <= 0.70,
      f"等级分布: {df_c['member_level'].value_counts().to_dict()}")
check("钻石会员占比 <15%",
      level_dist.get("钻石", 0) < 0.15,
      f"钻石占比: {level_dist.get('钻石',0)*100:.1f}%")
check("total_spend > 0",          (df_c["total_spend"] > 0).all(),
      f"≤0行: {(df_c['total_spend']<=0).sum()}")

# ══════════════════════════════════════════════
# 3. fraud_cn.csv
# ══════════════════════════════════════════════
sep("3. fraud_cn.csv — 欺诈风控")
df_f = pd.read_csv(PROC / "fraud_cn.csv")

check("行数充足(>280000)",         len(df_f) > 280_000,   f"实际: {len(df_f):,}")
check("label 只含 0/1",           set(df_f["label"].unique()).issubset({0,1}),
      f"唯一值: {df_f['label'].unique()}")
check("欺诈率在合理范围(0.1-5%)",
      0.001 <= df_f["label"].mean() <= 0.05,
      f"欺诈率: {df_f['label'].mean()*100:.4f}%")
check("含 sample_weight 列",       "sample_weight" in df_f.columns,
      f"列名: {list(df_f.columns[-3:])}")
check("amount_cny 范围合理(50-50000)",
      df_f["amount_cny"].between(10, 60_000).all(),
      f"min={df_f['amount_cny'].min():.0f}  max={df_f['amount_cny'].max():.0f}")
check("V1-V28 均无缺失",
      df_f[[c for c in df_f.columns if c.startswith("V")]].isnull().sum().sum() == 0)

# ══════════════════════════════════════════════
# 4. stores_offline.csv
# ══════════════════════════════════════════════
sep("4. stores_offline.csv — 线下门店")
df_s = pd.read_csv(PROC / "stores_offline.csv")

check("行数(6435)",                len(df_s) == 6435,     f"实际: {len(df_s)}")
check("Temperature 已转摄氏度",
      "temperature_c" in df_s.columns and "Temperature" not in df_s.columns,
      f"列名含 temperature_c: {'temperature_c' in df_s.columns}")
check("温度范围合理(-20~40°C)",
      df_s["temperature_c"].between(-20, 42).all(),
      f"min={df_s['temperature_c'].min()}  max={df_s['temperature_c'].max()}")
check("宏观列已加 _ref 后缀",
      all(c in df_s.columns for c in ["cpi_ref","unemployment_ref"]),
      f"列: {[c for c in df_s.columns if 'ref' in c or 'temp' in c]}")
check("8家门店均有数据",
      df_s["store_id"].nunique() == 8,
      f"门店数: {df_s['store_id'].nunique()}")
check("weekly_sales > 0",         (df_s["weekly_sales"] > 0).all(),
      f"≤0行: {(df_s['weekly_sales']<=0).sum()}")

# ══════════════════════════════════════════════
# 5. reviews_cn.csv
# ══════════════════════════════════════════════
sep("5. reviews_cn.csv — 中文评论")
df_r = pd.read_csv(PROC / "reviews_cn.csv")

check("行数充足(>40000)",          len(df_r) > 40_000,    f"实际: {len(df_r):,}")
check("无电子/酒店类别",
      not df_r["cat"].isin({"平板","手机","计算机","酒店","书籍"}).any(),
      f"剩余类别: {df_r['cat'].unique().tolist()}")
check("label 只含 0/1",           set(df_r["label"].unique()).issubset({0,1}))
check("正负比例均衡(40-60%)",
      0.40 <= df_r["label"].mean() <= 0.60,
      f"正评率: {df_r['label'].mean()*100:.1f}%")
check("无空评论",                  df_r["review"].isnull().sum() == 0,
      f"空评论: {df_r['review'].isnull().sum()}")
check("评论最短≥3字",
      (df_r["review"].str.len() >= 3).all(),
      f"<3字行数: {(df_r['review'].str.len()<3).sum()}")

# ══════════════════════════════════════════════
# 6. inventory.csv
# ══════════════════════════════════════════════
sep("6. inventory.csv — 库存快照")
df_inv = pd.read_csv(GEN / "inventory.csv")

check("行数(26×8×730≈152000)",     len(df_inv) > 150_000,  f"实际: {len(df_inv):,}")
check("stock_qty ≥ 0",             (df_inv["stock_qty"] >= 0).all(),
      f"负库存行: {(df_inv['stock_qty']<0).sum()}")
check("缺货率 < 5%",
      (df_inv["stock_qty"] == 0).mean() < 0.05,
      f"缺货率: {(df_inv['stock_qty']==0).mean()*100:.2f}%")
check("日期范围覆盖2022-2024",
      pd.to_datetime(df_inv["date"]).min().year >= 2022,
      f"{df_inv['date'].min()} ~ {df_inv['date'].max()}")

# ══════════════════════════════════════════════
# 7. dialogues.csv + faq.csv
# ══════════════════════════════════════════════
sep("7. dialogues.csv + faq.csv — 客服数据")
df_d = pd.read_csv(GEN / "dialogues.csv")
df_faq = pd.read_csv(GEN / "faq.csv")

check("对话条数充足(>2000)",       len(df_d) > 2000,       f"实际: {len(df_d):,}")
check("覆盖7种意图",               df_d["intent"].nunique() == 7,
      f"意图: {df_d['intent'].unique().tolist()}")
check("每类意图均有300条",
      (df_d["intent"].value_counts() == 300).all(),
      f"分布: {df_d['intent'].value_counts().to_dict()}")
check("FAQ 条数 ≥ 150",           len(df_faq) >= 150,     f"实际: {len(df_faq)}")
check("无空问答",
      df_d[["user_query","standard_reply"]].isnull().sum().sum() == 0)

# ══════════════════════════════════════════════
# 8. churn_supplement.csv
# ══════════════════════════════════════════════
sep("8. ecommerce_customer_churn (流失补充)")
df_ch = pd.read_csv(RAW / "churn_supplement/ecommerce_customer_churn_dataset.csv")

check("行数充足(>45000)",          len(df_ch) > 45_000,    f"实际: {len(df_ch):,}")
churn_col = [c for c in df_ch.columns if "churn" in c.lower()][0]
check("流失率合理(20-40%)",
      0.20 <= df_ch[churn_col].mean() <= 0.40,
      f"流失率: {df_ch[churn_col].mean()*100:.1f}%  (列:{churn_col})")
miss_pct = df_ch.isnull().mean()
worst_miss = miss_pct.nlargest(3)
check("缺失值最严重列 < 15%",
      worst_miss.iloc[0] < 0.15,
      f"最高缺失: {worst_miss.index[0]}={worst_miss.iloc[0]*100:.1f}%  "
      f"{worst_miss.index[1]}={worst_miss.iloc[1]*100:.1f}%")

# ══════════════════════════════════════════════
# 汇总
# ══════════════════════════════════════════════
sep("质检汇总")
ok_cnt   = sum(1 for lv,_,_ in issues if False) if not issues else 0
warn_cnt = sum(1 for lv,_,_ in issues if lv == "WARN")
fail_cnt = sum(1 for lv,_,_ in issues if lv == "FAIL")

# 统计通过项（总项目数 - 问题数）
all_checks = 0
for line in open(__file__, encoding="utf-8"):
    if line.strip().startswith("check("):
        all_checks += 1

passed = all_checks - len(issues)
print(f"\n  总检查项: {all_checks}  通过: {passed}  警告: {warn_cnt}  失败: {fail_cnt}")
if issues:
    print("\n  未通过项：")
    for lv, label, detail in issues:
        icon = WARN if lv == "WARN" else FAIL
        print(f"    {icon} [{lv}] {label}")
        if detail:
            print(f"           {detail}")
else:
    print(f"\n  {PASS} 所有检查项全部通过！")
