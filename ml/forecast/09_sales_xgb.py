# -*- coding: utf-8 -*-
"""09_sales_xgb.py — XGBoost 销售回归（特征工程）"""
import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent.parent))
import pandas as pd, numpy as np, pickle
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import TimeSeriesSplit
import xgboost as xgb
from ml.config import *

OUT = RES_FORECAST / "sales_xgb_result.csv"
if OUT.exists(): print("SKIP"); exit(0)

print("[09] 特征工程 (优化版)...")
df = pd.read_csv(ORDERS_CSV, parse_dates=["order_date"], low_memory=False)
daily = df.groupby(df["order_date"].dt.date)["total_amount"].sum().reset_index()
daily.columns = ["ds","y"]
daily["ds"] = pd.to_datetime(daily["ds"])
daily = daily.sort_values("ds").reset_index(drop=True)

# 滞后特征（不做 log 变换， XGBoost 能直接处理非线性）
for lag in [1, 2, 3, 7, 14, 21, 28, 30, 60, 90]:
    daily[f"lag_{lag}"] = daily["y"].shift(lag)

# 滚动统计
for w in [7, 14, 30, 60]:
    s = daily["y"].shift(1)
    daily[f"roll_mean_{w}"] = s.rolling(w).mean()
    daily[f"roll_std_{w}"]  = s.rolling(w).std()
    daily[f"roll_max_{w}"]  = s.rolling(w).max()
    daily[f"roll_min_{w}"]  = s.rolling(w).min()

# 日历特征
from sys import path as _p; _p.insert(0, str(ROOT/"scripts"))
from company_config import is_holiday
daily["dayofweek"]   = daily["ds"].dt.dayofweek
daily["month"]       = daily["ds"].dt.month
daily["dayofmonth"]  = daily["ds"].dt.day
daily["quarter"]     = daily["ds"].dt.quarter
daily["weekofyear"]  = daily["ds"].dt.isocalendar().week.astype(int)
daily["is_weekend"]  = (daily["dayofweek"] >= 5).astype(int)
daily["is_holiday"]  = daily["ds"].apply(lambda d: is_holiday(d.month, d.day))
daily["is_month_end"]   = daily["ds"].dt.is_month_end.astype(int)
daily["is_month_start"] = daily["ds"].dt.is_month_start.astype(int)

daily = daily.dropna().reset_index(drop=True)
feat_cols = [c for c in daily.columns if c not in ["ds","y"]]

# 最后30天作为 holdout（与 SARIMA/HW 一致）
holdout = 30
X_all, y_all = daily[feat_cols].values, daily["y"].values
X_train_full = X_all[:-holdout];  y_train_full = y_all[:-holdout]
X_test_final = X_all[-holdout:];  y_test_final = y_all[-holdout:]
print(f"  训练={len(X_train_full)}  最后{holdout}天测试  特征数={len(feat_cols)}")

# Walk-forward CV 评估模型泛化能力
print("[09] TimeSeriesSplit Walk-Forward CV (5折)...")
tscv = TimeSeriesSplit(n_splits=5)
cv_mapes = []
for fold, (tr_idx, va_idx) in enumerate(tscv.split(X_train_full)):
    Xf_tr, yf_tr = X_train_full[tr_idx], y_train_full[tr_idx]
    Xf_va, yf_va = X_train_full[va_idx], y_train_full[va_idx]
    _m = xgb.XGBRegressor(
        n_estimators=500, max_depth=5, learning_rate=0.03,
        subsample=0.8, colsample_bytree=0.7, min_child_weight=3,
        reg_alpha=0.1, tree_method="hist", device="cuda",
        random_state=SEED, n_jobs=CPU_N_JOBS, early_stopping_rounds=30,
        eval_metric="rmse",
    )
    _m.fit(Xf_tr, yf_tr, eval_set=[(Xf_va, yf_va)], verbose=False)
    _pred = _m.predict(Xf_va)
    _mask = yf_va > yf_va.mean() * 0.05
    _mape = (np.abs((_pred[_mask] - yf_va[_mask]) / yf_va[_mask])).mean() * 100 if _mask.sum() > 0 else 999
    cv_mapes.append(_mape)
    print(f"  Fold {fold+1}: MAPE={_mape:.2f}%")
print(f"  CV 均均 MAPE={np.mean(cv_mapes):.2f}%")

# 全量训练最终模型
model = xgb.XGBRegressor(
    n_estimators=1000, max_depth=5, learning_rate=0.02,
    subsample=0.8, colsample_bytree=0.7, min_child_weight=3,
    reg_alpha=0.1, reg_lambda=1.0,
    tree_method="hist", device="cuda",
    random_state=SEED, n_jobs=CPU_N_JOBS,
    early_stopping_rounds=50,
)
# 用最后20%训练数据作为早停验证集
_val_size = max(20, int(len(X_train_full)*0.15))
model.fit(X_train_full[:-_val_size], y_train_full[:-_val_size],
          eval_set=[(X_train_full[-_val_size:], y_train_full[-_val_size:])], verbose=200)

pred   = model.predict(X_test_final)
actual = y_test_final

mae  = mean_absolute_error(actual, pred)
mask = actual > actual.mean() * 0.05
mape = (np.abs((pred[mask] - actual[mask]) / actual[mask])).mean() * 100 if mask.sum() > 0 else 999
print(f"[09] 最后30天 MAE={mae:.0f}  MAPE={mape:.2f}%  (CV均={np.mean(cv_mapes):.2f}%)")

pd.DataFrame({"ds":daily["ds"].iloc[-holdout:].values, "actual":actual, "forecast":pred}).to_csv(OUT, index=False)
pickle.dump(model, open(MODELS/"sales_xgb.pkl","wb"))
print(f"[09] ✅ XGB销售预测完成 → {OUT}")
import os; os._exit(0)
