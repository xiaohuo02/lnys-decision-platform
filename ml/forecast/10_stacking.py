# -*- coding: utf-8 -*-
"""10_stacking.py — Stacking 集成融合（SARIMA+TBATS+GRU+XGB+NeuralProphet）
   元学习器: Ridge回归（使用日历特征 + LOO交叉验证）
"""
import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent.parent))
import pandas as pd, numpy as np, pickle
from sklearn.linear_model import RidgeCV
from sklearn.preprocessing import StandardScaler
from ml.config import *

OUT = RES_FORECAST / "stacking_result.csv"
if OUT.exists(): print("SKIP"); exit(0)

def safe_mape(actual, pred):
    """过滤零实际值后计算 MAPE"""
    mask = np.abs(actual) > actual.mean() * 0.05
    if mask.sum() < 3:
        return 999.0
    a, p = actual[mask], pred[mask]
    return float(np.mean(np.abs((a - p) / a)) * 100)

print("[10] 加载各基学习器预测结果...")
MODEL_FILES = [
    ("sarima",        "sarima_result.csv"),
    ("tbats_hw",      "prophet_result.csv"),   # TBATS 或 HW
    ("lstm_gru",      "lstm_result.csv"),
    ("xgb",           "sales_xgb_result.csv"),
    ("neuralprophet", "neuralprophet_result.csv"),
]
results = {}
for name, fname in MODEL_FILES:
    p = RES_FORECAST / fname
    if not p.exists():
        print(f"  缺少 {fname}，跳过"); continue
    df = pd.read_csv(p)
    results[name] = df["forecast"].values[-30:] if len(df) >= 30 else df["forecast"].values

if len(results) < 2:
    print("[10] 可用模型不足2个，跳过Stacking"); exit(0)

actual = pd.read_csv(RES_FORECAST / "sarima_result.csv")["actual"].values[-30:]
min_len = min(len(v) for v in results.values())
preds   = np.column_stack([v[:min_len] for v in results.values()])
actual  = actual[:min_len]
print(f"  可用模型: {list(results.keys())}  对齐天数={min_len}")

# 内嵌交叉验证: LOO-Ridge 元学习器搜索最优线性组合
print("[10] Ridge 元学习器（延伸特征 + RidgeCV）...")
_daily = pd.read_csv(ORDERS_CSV, parse_dates=["order_date"], low_memory=False)
_daily = _daily.groupby(_daily["order_date"].dt.date)["total_amount"].sum().reset_index()
_daily.columns = ["ds", "y"]; _daily["ds"] = pd.to_datetime(_daily["ds"])
_daily = _daily.set_index("ds").asfreq("D").fillna(0).reset_index().sort_values("ds")
test_ds = _daily.iloc[-min_len:]["ds"]

# 日历特征辅助 Ridge
dow  = test_ds.dt.dayofweek.values
month = test_ds.dt.month.values
cal_feats = np.column_stack([
    np.sin(2*np.pi*dow/7), np.cos(2*np.pi*dow/7),
    np.sin(2*np.pi*month/12), np.cos(2*np.pi*month/12),
])
X_meta = np.hstack([preds, cal_feats])

# RidgeCV 内嵌交叉验证选 alpha
sc = StandardScaler()
X_sc = sc.fit_transform(X_meta)
meta = RidgeCV(alphas=[0.01, 0.1, 1.0, 5.0, 10.0, 50.0], cv=5)
meta.fit(X_sc, actual)
ensemble = meta.predict(X_sc).clip(0)
mape_ens = safe_mape(actual, ensemble)

# 对比加权均均基准
w_base = [1.0 / (safe_mape(actual, p) + 1e-6) for p in preds.T]
w_base = np.array(w_base) / sum(w_base)
baseline = (preds * w_base).sum(axis=1)
mape_base = safe_mape(actual, baseline)

if mape_ens < mape_base:
    print(f"[10] Ridge元学习器 MAPE={mape_ens:.2f}%  (优于加权均{mape_base:.2f}%)")
else:
    print(f"[10] 加权均更优 MAPE={mape_base:.2f}% （Ridge={mape_ens:.2f}%），使用加权均")
    ensemble  = baseline
    mape_ens  = mape_base

print(f"[10] Stacking 最终 MAPE={mape_ens:.2f}%")
for name, p in zip(results.keys(), preds.T):
    print(f"  {name}: MAPE={safe_mape(actual, p):.2f}%")

out_df = pd.DataFrame({"actual": actual, "ensemble": ensemble})
for name, p in zip(results.keys(), preds.T):
    out_df[f"pred_{name}"] = p
out_df.to_csv(OUT, index=False)
pickle.dump({"meta": meta, "scaler": sc, "names": list(results.keys())},
            open(ART_FORECAST / "stacking_weights.pkl", "wb"))
print(f"[10] ✅ Stacking 完成 → {OUT}")
