# -*- coding: utf-8 -*-
"""11_fraud_iso.py — Isolation Forest + 规则引擎实时风控"""
import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent.parent))
import pandas as pd, numpy as np, pickle
from sklearn.ensemble import IsolationForest
from sklearn.metrics import roc_auc_score
from ml.config import *

OUT = RES_FRAUD / "fraud_iso_result.csv"
if OUT.exists(): print("SKIP"); exit(0)

print("[11] 读取欺诈数据...")
df = pd.read_csv(FRAUD_CSV)
v_cols = [c for c in df.columns if c.startswith("V")]
feat   = df[v_cols + ["amount_cny"]].values
labels = df["label"].values

actual_fraud_rate = float(labels.mean())
print(f"[11] 实际欺诈率: {actual_fraud_rate:.4f}")
print(f"[11] 拟合 Isolation Forest（n_estimators=300，contamination按实际欺诈率）...")
iso = IsolationForest(
    n_estimators=300,
    contamination=max(0.001, actual_fraud_rate),
    max_samples="auto",
    random_state=SEED, n_jobs=CPU_N_JOBS,
    bootstrap=True,
)
iso.fit(feat)
scores = -iso.score_samples(feat)

auc = roc_auc_score(labels, scores)
print(f"[11] Isolation Forest AUC={auc:.4f}")

# 规则引擎风险评分
def rule_score(row):
    score = 0
    if row.get("hour_of_day", 12) in range(0, 5): score += 20
    if row.get("amount_cny", 0) > 10000:          score += 40
    if row.get("device_type","") == "mobile":      score += 5
    return score

print("[11] 计算规则引擎分数...")
df["iso_score"]   = scores
df["rule_score"]  = df.apply(rule_score, axis=1)
df["total_risk"]  = (df["iso_score"] / df["iso_score"].max() * 60 + df["rule_score"]).clip(0, 100)
df["risk_level"]  = pd.cut(df["total_risk"], bins=[0,50,79,100], labels=["低风险","中风险","高风险"])

df[["transaction_id","label","iso_score","rule_score","total_risk","risk_level"]].to_csv(OUT, index=False)
pickle.dump(iso, open(MODELS/"iso_forest.pkl","wb"))
print(f"[11] ✅ 完成 → {OUT}")
print(df["risk_level"].value_counts().to_string())
