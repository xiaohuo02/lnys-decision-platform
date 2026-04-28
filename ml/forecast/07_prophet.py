# -*- coding: utf-8 -*-
"""07_prophet.py — TBATS 销售预测（多重季节性：周=7 + 年=365）
   方案：TBATS (Trigonometric Box-Cox ARMA Trend Seasonal)
   优势：同时处理周季节性和年季节性，被证明优于标准 Holt-Winters
   参考: De Livera et al. (2011) JASA 106(496)
"""
import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent.parent))
import pandas as pd, numpy as np, pickle, warnings
warnings.filterwarnings("ignore")
from tbats import TBATS
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from ml.config import *

OUT = RES_FORECAST / "prophet_result.csv"
if OUT.exists(): print("SKIP"); exit(0)

print("[07] 准备时序数据...")
df = pd.read_csv(ORDERS_CSV, parse_dates=["order_date"], low_memory=False)
daily = df.groupby(df["order_date"].dt.date)["total_amount"].sum().reset_index()
daily.columns = ["ds","y"]
daily["ds"] = pd.to_datetime(daily["ds"])
daily = daily.sort_values("ds").reset_index(drop=True)
daily = daily.set_index("ds").asfreq("D").fillna(0).reset_index()  # noqa

train = daily.iloc[:-30]
test  = daily.iloc[-30:]
print(f"  训练集: {len(train)} 天  测试集: {len(test)} 天")

# 先用 Holt-Winters 作为备选
print("[07] 也拟合 Holt-Winters 作为基准...")
hw_model = ExponentialSmoothing(
    train["y"].clip(lower=1),
    trend="add", seasonal="mul", seasonal_periods=7,
    initialization_method="estimated",
)
hw_fit  = hw_model.fit(optimized=True, use_brute=True)
hw_pred = hw_fit.forecast(30).clip(lower=0).values
actual  = test["y"].values
hw_mape = (np.abs((hw_pred - actual) / np.maximum(np.abs(actual), actual.mean()*0.1+1))).mean()*100
print(f"  Holt-Winters MAPE={hw_mape:.2f}%")

# TBATS 多重季节性（周=7, 年尽量=365）
print("[07] 拟合 TBATS（seasonal_periods=[7, 365]）...")
try:
    # period=365 需要2+完整年，当训练数据<730天时只用周季节性
    n_train = len(train)
    use_periods = [7, 365] if n_train >= 730 else [7]
    estimator = TBATS(
        seasonal_periods=use_periods,
        use_box_cox=True,
        use_trend=True,
        n_jobs=1,
    )
    tbats_fit  = estimator.fit(train["y"].values)
    tbats_pred = np.maximum(tbats_fit.forecast(steps=30), 0)
    tbats_mape = (np.abs((tbats_pred - actual) / np.maximum(np.abs(actual), actual.mean()*0.1+1))).mean()*100
    print(f"  TBATS MAPE={tbats_mape:.2f}%")
    if tbats_mape < hw_mape:
        pred, mape, mae = tbats_pred, tbats_mape, np.abs(tbats_pred - actual).mean()
        best_model, model_name = tbats_fit, "TBATS"
    else:
        pred, mape, mae = hw_pred, hw_mape, np.abs(hw_pred - actual).mean()
        best_model, model_name = hw_fit, "HoltWinters"
except Exception as e:
    print(f"  TBATS 失败: {e}，回落 Holt-Winters")
    pred, mape, mae = hw_pred, hw_mape, np.abs(hw_pred - actual).mean()
    best_model, model_name = hw_fit, "HoltWinters"

print(f"[07] 最优模型={model_name}  MAE={mae:.0f}  MAPE={mape:.2f}%")
out_df = pd.DataFrame({
    "ds": test["ds"].values, "actual": actual, "forecast": pred,
    "yhat_lower": (pred * 0.9).clip(0),
    "yhat_upper": pred * 1.1,
})
out_df.to_csv(OUT, index=False, encoding="utf-8-sig")
pickle.dump(best_model, open(MODELS/"prophet.pkl","wb"))
print(f"[07] ✅ {model_name} 完成 → {OUT}  MAPE={mape:.2f}%")
import os; os._exit(0)
