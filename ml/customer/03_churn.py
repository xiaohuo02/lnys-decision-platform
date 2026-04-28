# -*- coding: utf-8 -*-
"""03_churn.py — XGBoost 客户流失预测 + SHAP"""
import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent.parent))
import pandas as pd, numpy as np, pickle
from sklearn.model_selection import train_test_split, GridSearchCV
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import roc_auc_score, f1_score, classification_report
import xgboost as xgb
import shap
from imblearn.over_sampling import SMOTE
from ml.config import *

OUT_MODEL  = ART_CUSTOMER / "churn_xgb.pkl"
OUT_RESULT = RES_CUSTOMER / "churn_result.csv"
if OUT_MODEL.exists(): print("SKIP"); exit(0)

print("[03] 读取流失数据集...")
df = pd.read_csv(CHURN_CSV)
target_col = [c for c in df.columns if "churn" in c.lower()][0]
df = df.rename(columns={target_col: "label"})

# 数值列填充中位数
num_cols = df.select_dtypes(include=np.number).columns.tolist()
num_cols = [c for c in num_cols if c != "label"]
for c in num_cols:
    df[c] = df[c].fillna(df[c].median())

# 类别列编码
for c in df.select_dtypes(include="object").columns:
    df[c] = LabelEncoder().fit_transform(df[c].astype(str))

X = df.drop(columns=["label"])
y = df["label"]
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=SEED, stratify=y)

print(f"[03] 训练集: {len(X_train)}  测试集: {len(X_test)}  流失率: {y.mean()*100:.1f}%")

print("[03] SMOTE 过采样处理类不均衡...")
smote = SMOTE(random_state=SEED, k_neighbors=5)
X_train_sm, y_train_sm = smote.fit_resample(X_train, y_train)
print(f"  SMOTE后: {len(X_train_sm)}  流失率: {y_train_sm.mean()*100:.1f}%")

model = xgb.XGBClassifier(
    n_estimators=500, max_depth=6, learning_rate=0.03,
    subsample=0.8, colsample_bytree=0.8,
    eval_metric="auc",
    random_state=SEED, n_jobs=CPU_N_JOBS,
    tree_method="hist", device="cuda",
    early_stopping_rounds=40,
)
model.fit(X_train_sm, y_train_sm, eval_set=[(X_test, y_test)], verbose=100)

y_pred_proba = model.predict_proba(X_test)[:,1]
y_pred       = model.predict(X_test)
auc = roc_auc_score(y_test, y_pred_proba)
f1  = f1_score(y_test, y_pred)
print(f"[03] AUC={auc:.4f}  F1={f1:.4f}")
print(classification_report(y_test, y_pred))

print("[03] 计算 SHAP 特征重要性...")
explainer   = shap.TreeExplainer(model)
shap_values = explainer.shap_values(X_test[:500])
importance  = pd.DataFrame({"feature": X.columns, "shap_mean": np.abs(shap_values).mean(0)})
importance  = importance.sort_values("shap_mean", ascending=False)
importance.to_csv(MODELS/"churn_shap.csv", index=False)
print(importance.head(10).to_string())

pickle.dump(model, open(OUT_MODEL,"wb"))
result = X_test.copy()
result["label"] = y_test.values
result["pred_proba"] = y_pred_proba
result.to_csv(OUT_RESULT, index=False)
print(f"[03] ✅ 流失预测完成 → {OUT_MODEL}")
