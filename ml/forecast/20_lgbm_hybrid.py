# -*- coding: utf-8 -*-
"""20_lgbm_hybrid.py — LightGBM + STL 分解混合预测
   方案来源: arxiv 2305.17201 "Improved Sales Forecasting using Trend and
             Seasonality Decomposition with LightGBM"
   核心思路: STL 分解出趋势/季节/残差分量，残差用 LGB 拟合，最终叠加回来
"""
import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent.parent))
import pandas as pd, numpy as np, pickle, warnings
warnings.filterwarnings("ignore")
from statsmodels.tsa.seasonal import STL
import lightgbm as lgb
from sklearn.metrics import mean_absolute_error
from ml.config import *

OUT = RES_FORECAST / "lgbm_hybrid_result.csv"
if OUT.exists(): print("SKIP"); exit(0)

print("[20] 读取日销售数据...")
df = pd.read_csv(ORDERS_CSV, parse_dates=["order_date"], low_memory=False)
daily = df.groupby(df["order_date"].dt.date)["total_amount"].sum().reset_index()
daily.columns = ["ds", "y"]
daily["ds"] = pd.to_datetime(daily["ds"])
daily = daily.set_index("ds").asfreq("D").fillna(0).reset_index()
daily = daily.sort_values("ds").reset_index(drop=True)
print(f"  总天数: {len(daily)}")

TEST_DAYS = 30
y_raw   = daily["y"].values.astype(np.float64)
y_log   = np.log1p(y_raw)
ds_arr  = daily["ds"].values
n       = len(y_raw)

train_y_log = y_log[:-TEST_DAYS]

# ── Step 1: STL 分解训练集（周期=7，鲁棒拟合）─────────────────────────────
print("[20] STL 分解训练数据（period=7, robust=True）...")
stl     = STL(train_y_log, period=7, robust=True)
stl_res = stl.fit()
trend_tr   = stl_res.trend       # T(t)
seasonal_tr = stl_res.seasonal   # S(t)
resid_tr   = stl_res.resid       # R(t) = y_log - T - S

# ── Step 2: 延伸趋势到测试期（线性外推最近14天斜率）──────────────────────
last_n = 14
slope = (trend_tr[-1] - trend_tr[-last_n]) / last_n
trend_test = np.array([trend_tr[-1] + slope * (i + 1) for i in range(TEST_DAYS)])

# 延伸季节（直接重复上一个完整周）
period = 7
seasonal_test = np.array([seasonal_tr[-(period - i % period)] for i in range(TEST_DAYS)])

print(f"  趋势斜率: {slope:.6f}/天  最后趋势值: {trend_tr[-1]:.4f}")

# ── Step 3: 构造残差特征并训练 LightGBM ──────────────────────────────────
from sys import path as _p; _p.insert(0, str(ROOT / "scripts"))
from company_config import is_holiday

def build_features(y_log_full, resid_full, ds_full, start, end):
    rows = []
    for t in range(start, end):
        d = pd.Timestamp(ds_full[t])
        row = {}
        for lag in [1, 2, 3, 7, 14, 21, 28]:
            row[f"lag_{lag}"]   = y_log_full[t - lag] if t - lag >= 0 else 0.0
            row[f"rlag_{lag}"]  = resid_full[t - lag] if t - lag >= 0 else 0.0
        for w in [7, 14]:
            sl = max(0, t - w)
            row[f"rmean_{w}"] = resid_full[sl:t].mean() if t > sl else 0.0
            row[f"rstd_{w}"]  = resid_full[sl:t].std()  if t > sl else 0.0
        row["sin_dow"] = np.sin(2 * np.pi * d.dayofweek / 7)
        row["cos_dow"] = np.cos(2 * np.pi * d.dayofweek / 7)
        row["sin_mon"] = np.sin(2 * np.pi * d.month / 12)
        row["cos_mon"] = np.cos(2 * np.pi * d.month / 12)
        row["is_holiday"]   = float(is_holiday(d.month, d.day))
        row["is_month_end"] = float(d.is_month_end)
        rows.append(row)
    return pd.DataFrame(rows)

# 需要足够的 lag 数据，从第 28 天开始
min_start = 28
n_tr = len(train_y_log)
X_tr = build_features(y_log, resid_tr, ds_arr, min_start, n_tr)
y_tr_resid = resid_tr[min_start:]
print(f"[20] LightGBM 训练: {len(X_tr)} 条  特征: {X_tr.shape[1]}")

# 构建测试特征（用完整的 y_log 和 resid 延伸数组）
resid_ext = np.concatenate([resid_tr, np.zeros(TEST_DAYS)])  # 占位
X_te = build_features(y_log, resid_ext, ds_arr, n_tr, n)

# LightGBM
val_size = max(14, int(len(X_tr) * 0.15))
X_val, y_val_r = X_tr.iloc[-val_size:], y_tr_resid[-val_size:]
X_trn, y_trn_r = X_tr.iloc[:-val_size], y_tr_resid[:-val_size]

lgb_tr = lgb.Dataset(X_trn, label=y_trn_r)
lgb_va = lgb.Dataset(X_val, label=y_val_r, reference=lgb_tr)

params = dict(
    objective="regression", metric="mae",
    learning_rate=0.02, num_leaves=31,
    min_data_in_leaf=10, feature_fraction=0.8,
    bagging_fraction=0.8, bagging_freq=5,
    reg_alpha=0.1, reg_lambda=1.0,
    verbose=-1, seed=SEED,
)
print("[20] 训练 LightGBM 残差模型...")
cb = lgb.train(
    params, lgb_tr, num_boost_round=800,
    valid_sets=[lgb_va],
    callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(200)],
)
resid_pred = cb.predict(X_te)

# ── Step 4: 叠加预测 ─────────────────────────────────────────────────────
log_pred = trend_test + seasonal_test + resid_pred
pred     = np.expm1(np.clip(log_pred, -5, 20)).clip(0)
actual   = y_raw[-TEST_DAYS:]

mae  = mean_absolute_error(actual, pred)
mask = actual > actual.mean() * 0.05
mape = (np.abs((pred[mask] - actual[mask]) / actual[mask])).mean() * 100 if mask.sum() > 0 else 999
print(f"[20] LightGBM+STL  MAE={mae:.0f}  MAPE={mape:.2f}%")

out_df = pd.DataFrame({
    "ds":     ds_arr[-TEST_DAYS:],
    "actual": actual,
    "forecast": pred,
    "trend_fc": np.expm1(trend_test).clip(0),
    "seasonal_fc": seasonal_test,
    "resid_fc": resid_pred,
})
out_df.to_csv(OUT, index=False)
pickle.dump(cb, open(ART_FORECAST / "lgbm_hybrid.pkl", "wb"))
print(f"[20] ✅ LightGBM+STL 完成 → {OUT}  MAPE={mape:.2f}%")
import os; os._exit(0)
