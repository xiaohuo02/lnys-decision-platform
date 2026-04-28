# -*- coding: utf-8 -*-
import pandas as pd
from pathlib import Path

PROC = Path("data/processed")

df = pd.read_csv(PROC / "customers_cn.csv")
before = len(df)
df = df[df["total_spend"] > 0].reset_index(drop=True)
df.to_csv(PROC / "customers_cn.csv", index=False, encoding="utf-8-sig")

level_dist = df["member_level"].value_counts().to_dict()
print(f"删除零消费客户: {before} -> {len(df)}  移除: {before - len(df)} 行")
print(f"会员等级分布: {level_dist}")
