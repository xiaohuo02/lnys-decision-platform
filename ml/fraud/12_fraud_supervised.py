# -*- coding: utf-8 -*-
"""12_fraud_supervised.py — LR/RF/XGB/LGB 欺诈对比实验"""
import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent.parent))
import pandas as pd, numpy as np, pickle
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score, f1_score, precision_score, recall_score
from sklearn.preprocessing import StandardScaler
import xgboost as xgb
import lightgbm as lgb
import shap
from ml.config import *

OUT = RES_FRAUD / "fraud_supervised_result.csv"
if OUT.exists(): print("SKIP"); exit(0)

print("[12] 读取欺诈数据...")
df  = pd.read_csv(FRAUD_CSV)
v_cols = [c for c in df.columns if c.startswith("V")]
feats  = v_cols + ["amount_cny","hour_of_day"]
feats  = [c for c in feats if c in df.columns]
X, y   = df[feats].values, df["label"].values
sw     = df["sample_weight"].values

X_tr, X_te, y_tr, y_te, sw_tr, sw_te = train_test_split(
    X, y, sw, test_size=0.2, random_state=SEED, stratify=y)
print(f"[12] 训练={len(X_tr):,}  测试={len(X_te):,}  欺诈率={y.mean()*100:.2f}%")

results = []

# --- LR ---
print("[12] 逻辑回归...")
sc  = StandardScaler(); X_tr_s = sc.fit_transform(X_tr); X_te_s = sc.transform(X_te)
lr  = LogisticRegression(max_iter=300, n_jobs=CPU_N_JOBS, C=0.1)
lr.fit(X_tr_s, y_tr, sample_weight=sw_tr)
p   = lr.predict_proba(X_te_s)[:,1]
results.append({"model":"LR", "auc":roc_auc_score(y_te,p), "f1":f1_score(y_te,p>.5),
                "precision":precision_score(y_te,p>.5), "recall":recall_score(y_te,p>.5)})
pickle.dump(lr, open(MODELS/"fraud_lr.pkl","wb"))

# --- RF ---
print("[12] 随机森林（n_jobs=10）...")
rf = RandomForestClassifier(n_estimators=80, max_depth=12, n_jobs=CPU_N_JOBS,
                             random_state=SEED, max_samples=0.7)
rf.fit(X_tr, y_tr, sample_weight=sw_tr)
p  = rf.predict_proba(X_te)[:,1]
results.append({"model":"RF", "auc":roc_auc_score(y_te,p), "f1":f1_score(y_te,p>.5),
                "precision":precision_score(y_te,p>.5), "recall":recall_score(y_te,p>.5)})
pickle.dump(rf, open(MODELS/"fraud_rf.pkl","wb"))

# --- XGB ---
print("[12] XGBoost (GPU)...")
xm = xgb.XGBClassifier(n_estimators=300, max_depth=6, learning_rate=0.05,
                        tree_method="hist", device="cuda",
                        scale_pos_weight=(y_tr==0).sum()/(y_tr==1).sum(),
                        random_state=SEED, eval_metric="auc", early_stopping_rounds=20)
xm.fit(X_tr, y_tr, sample_weight=sw_tr, eval_set=[(X_te,y_te)], verbose=100)
p = xm.predict_proba(X_te)[:,1]
results.append({"model":"XGB", "auc":roc_auc_score(y_te,p), "f1":f1_score(y_te,p>.5),
                "precision":precision_score(y_te,p>.5), "recall":recall_score(y_te,p>.5)})
pickle.dump(xm, open(MODELS/"fraud_xgb.pkl","wb"))

# --- LGB ---
print("[12] LightGBM (GPU)...")
lm = lgb.LGBMClassifier(n_estimators=300, max_depth=6, learning_rate=0.05,
                         device="cpu", random_state=SEED,
                         scale_pos_weight=(y_tr==0).sum()/(y_tr==1).sum(),
                         n_jobs=CPU_N_JOBS)
lm.fit(X_tr, y_tr, sample_weight=sw_tr,
       eval_set=[(X_te,y_te)], callbacks=[lgb.early_stopping(20), lgb.log_evaluation(100)])
p = lm.predict_proba(X_te)[:,1]
results.append({"model":"LGB", "auc":roc_auc_score(y_te,p), "f1":f1_score(y_te,p>.5),
                "precision":precision_score(y_te,p>.5), "recall":recall_score(y_te,p>.5)})
pickle.dump(lm, open(MODELS/"fraud_lgb.pkl","wb"))

res_df = pd.DataFrame(results)
print("\n[12] 模型对比结果:")
print(res_df.to_string(index=False))
res_df.to_csv(OUT, index=False)

# SHAP on best model
best_model_name = res_df.loc[res_df["auc"].idxmax(),"model"]
print(f"\n[12] SHAP 分析最优模型: {best_model_name}")
best_model = {"LR":lr,"RF":rf,"XGB":xm,"LGB":lm}[best_model_name]
try:
    exp = shap.TreeExplainer(best_model)
    sv  = exp.shap_values(X_te[:500])
    sv  = sv[1] if isinstance(sv, list) else sv
    imp = pd.DataFrame({"feature":feats,"shap_mean":np.abs(sv).mean(0)})
    imp.sort_values("shap_mean",ascending=False).to_csv(MODELS/"fraud_shap.csv",index=False)
    print("  SHAP保存完成")
except Exception as e:
    print(f"  SHAP跳过: {e}")

print(f"[12] ✅ 欺诈监督学习完成 → {OUT}")
import os; os._exit(0)
