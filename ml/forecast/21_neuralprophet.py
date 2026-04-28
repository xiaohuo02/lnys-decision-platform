# -*- coding: utf-8 -*-
"""21_neuralprophet.py — NeuralProphet 神经时序预测
   NeuralProphet = PyTorch + Prophet 思路，无需 CmdStan，支持 AR 自回归
   参考: github.com/ourownstory/neural_prophet
"""
import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent.parent))
import pandas as pd, numpy as np, warnings
warnings.filterwarnings("ignore")
import logging; logging.getLogger("NP").setLevel(logging.WARNING)
from ml.config import *

OUT = RES_FORECAST / "neuralprophet_result.csv"
if OUT.exists(): print("SKIP"); exit(0)

from neuralprophet import NeuralProphet, set_log_level
set_log_level("ERROR")

print("[21] 读取日销售数据...")
df_raw = pd.read_csv(ORDERS_CSV, parse_dates=["order_date"], low_memory=False)
daily  = df_raw.groupby(df_raw["order_date"].dt.date)["total_amount"].sum().reset_index()
daily.columns = ["ds", "y"]
daily["ds"] = pd.to_datetime(daily["ds"])
daily  = daily.set_index("ds").asfreq("D").fillna(0).reset_index()
daily  = daily.sort_values("ds").reset_index(drop=True)
print(f"  总天数: {len(daily)}")

TEST_DAYS = 30
train_df  = daily.iloc[:-TEST_DAYS][["ds", "y"]].copy()
test_df   = daily.iloc[-TEST_DAYS:][["ds", "y"]].copy()

# NeuralProphet 配置：AR 自回归 + 双季节性 + 加速训练
print("[21] 训练 NeuralProphet（AR=14, 周+年季节性）...")
m = NeuralProphet(
    n_lags            = 14,           # 自回归窗口
    n_forecasts       = 1,            # 逐步预测
    yearly_seasonality = True,
    weekly_seasonality = True,
    daily_seasonality  = False,
    learning_rate     = 0.003,
    epochs            = 80,
    batch_size        = 64,
    trainer_config    = {"accelerator": "auto"},
)

metrics = m.fit(train_df, freq="D", progress="none")
print(f"  训练完成，最终 MAE={metrics['MAE'].iloc[-1]:.4f}")

# 逐步预测最后30天
print("[21] 预测最后30天...")
future   = m.make_future_dataframe(train_df, periods=TEST_DAYS, n_historic_predictions=False)
forecast = m.predict(future)
pred     = forecast["yhat1"].values[-TEST_DAYS:]
pred     = np.maximum(pred, 0)
actual   = test_df["y"].values

mae  = np.abs(pred - actual).mean()
mask = actual > actual.mean() * 0.05
mape = (np.abs((pred[mask] - actual[mask]) / actual[mask])).mean() * 100 if mask.sum() > 0 else 999
print(f"[21] NeuralProphet  MAE={mae:.0f}  MAPE={mape:.2f}%")

pd.DataFrame({"ds": test_df["ds"].values, "actual": actual, "forecast": pred}).to_csv(OUT, index=False)
print(f"[21] ✅ NeuralProphet 完成 → {OUT}  MAPE={mape:.2f}%")
import os; os._exit(0)
