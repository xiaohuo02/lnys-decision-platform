# -*- coding: utf-8 -*-
"""06_sarima.py — SARIMA 销售预测（线上+线下）"""
import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent.parent))
import pandas as pd, numpy as np, pickle, warnings
warnings.filterwarnings("ignore")
from statsmodels.tsa.stattools import adfuller
import pmdarima as pm
from ml.config import *

OUT = RES_FORECAST / "sarima_result.csv"
if OUT.exists(): print("SKIP"); exit(0)

print("[06] 准备日销售时序...")
df = pd.read_csv(ORDERS_CSV, parse_dates=["order_date"], low_memory=False)
daily = df.groupby(df["order_date"].dt.date)["total_amount"].sum().reset_index()
daily.columns = ["ds","y"]
daily["ds"] = pd.to_datetime(daily["ds"])
daily = daily.set_index("ds").asfreq("D").fillna(0)

# log1p 变换减小量级波动
daily["y_log"] = np.log1p(daily["y"])

train = daily.iloc[:-30]
test  = daily.iloc[-30:]
print(f"  训练集: {len(train)} 天  测试集: {len(test)} 天")

adf_result = adfuller(train["y_log"].values)
print(f"  ADF p値: {adf_result[1]:.4f} {'(平稳)' if adf_result[1]<0.05 else '(需差分)'}")

print("[06] auto_arima 自动选参（周季性m=7）...")
auto = pm.auto_arima(
    train["y_log"],
    m=7, seasonal=True,
    d=None, D=None,
    start_p=0, max_p=3,
    start_q=0, max_q=3,
    start_P=0, max_P=2,
    start_Q=0, max_Q=2,
    information_criterion="aic",
    stepwise=True, error_action="ignore",
    suppress_warnings=True, n_jobs=1
)
print(f"  最优阶数: {auto.order}  季节: {auto.seasonal_order}  AIC={auto.aic():.2f}")

forecast_log = auto.predict(n_periods=30)
forecast = np.expm1(forecast_log).clip(0)
actual   = test["y"].values
mae  = np.abs(forecast - actual).mean()
mask = actual > actual.mean() * 0.05
mape = (np.abs((forecast[mask] - actual[mask]) / actual[mask])).mean() * 100
print(f"  MAE={mae:.0f}  MAPE={mape:.2f}%")

out_df = pd.DataFrame({"ds": test.index, "actual": actual, "forecast": forecast})
out_df.to_csv(OUT, index=False, encoding="utf-8-sig")
pickle.dump(auto, open(MODELS/"sarima.pkl","wb"))
print(f"[06] ✅ SARIMA 完成 → {OUT}  MAPE={mape:.2f}%")
import os; os._exit(0)
