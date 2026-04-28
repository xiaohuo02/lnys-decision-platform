# -*- coding: utf-8 -*-
"""08_lstm.py — LSTM 销售预测（GPU加速）"""
import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent.parent))
import pandas as pd, numpy as np, os
import torch, torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from ml.config import *

OUT = RES_FORECAST / "lstm_result.csv"
if OUT.exists(): print("SKIP"); exit(0)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"[08] 使用设备: {device}")
if device.type == "cuda":
    torch.cuda.set_per_process_memory_fraction(GPU_MAX_MEM_GB / 8.0)

print("[08] 准备时序数据 (优化版)...")
df_raw = pd.read_csv(ORDERS_CSV, parse_dates=["order_date"], low_memory=False)
daily_df = df_raw.groupby(df_raw["order_date"].dt.date)["total_amount"].sum().reset_index()
daily_df.columns = ["ds","y"]
daily_df["ds"] = pd.to_datetime(daily_df["ds"])
daily_df = daily_df.set_index("ds").asfreq("D").fillna(0).reset_index()

TEST_DAYS = 30
y_raw = daily_df["y"].values.astype(np.float32)
y_log = np.log1p(y_raw)

# 用训练集周期归一化（除最后30天）
SEQ_LEN  = 28
train_y  = y_log[:-TEST_DAYS]
_mn  = train_y.mean()
_std = train_y.std() + 1e-8
y_norm = (y_log - _mn) / _std

# sin/cos 循环编码
dow   = daily_df["ds"].dt.dayofweek.values
month = daily_df["ds"].dt.month.values
sin_dow = np.sin(2 * np.pi * dow / 7).astype(np.float32)
cos_dow = np.cos(2 * np.pi * dow / 7).astype(np.float32)
sin_mon = np.sin(2 * np.pi * month / 12).astype(np.float32)
cos_mon = np.cos(2 * np.pi * month / 12).astype(np.float32)
data_arr = np.stack([y_norm, sin_dow, cos_dow, sin_mon, cos_mon], axis=1).astype(np.float32)
N_FEAT   = data_arr.shape[1]

# 训练序列：仅用除最后30天外的所有数据
train_data = data_arr[:-TEST_DAYS]
train_tgt  = y_norm[:-TEST_DAYS]

def make_sequences(data, target, seq_len):
    X, y = [], []
    for i in range(len(data) - seq_len):
        X.append(data[i:i+seq_len])
        y.append(target[i+seq_len])
    return np.array(X), np.array(y)

X_all, y_all = make_sequences(train_data, train_tgt, SEQ_LEN)
# 验证集用最后20%的训练序列用于 early stopping
split = int(len(X_all) * 0.85)
Xtr = torch.tensor(X_all[:split])
ytr = torch.tensor(y_all[:split]).unsqueeze(-1)
Xval = torch.tensor(X_all[split:])
yval = torch.tensor(y_all[split:]).unsqueeze(-1)

loader = DataLoader(TensorDataset(Xtr, ytr), batch_size=32, shuffle=True)

class GRUModel(nn.Module):
    def __init__(self, n_feat):
        super().__init__()
        self.gru1  = nn.GRU(n_feat, 96, num_layers=2, batch_first=True,
                            dropout=0.2, bidirectional=False)
        self.drop  = nn.Dropout(0.2)
        self.fc    = nn.Linear(96, 1)
    def forward(self, x):
        out, _ = self.gru1(x)
        return self.fc(self.drop(out[:, -1, :]))

model = GRUModel(N_FEAT).to(device)
opt   = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=150, eta_min=1e-5)
loss_fn = nn.HuberLoss(delta=1.0)

best_val, patience_cnt, PATIENCE = float("inf"), 0, 20
print("[08] 开始训练 GRU (优化版)...")
for epoch in range(1, 201):
    model.train()
    for xb, yb in loader:
        xb, yb = xb.to(device), yb.to(device)
        opt.zero_grad(); loss_fn(model(xb), yb).backward(); opt.step()
    sched.step()
    model.eval()
    with torch.no_grad():
        val_loss = loss_fn(model(Xval.to(device)), yval.to(device)).item()
    if epoch % 20 == 0:
        print(f"  epoch {epoch:3d}  val_loss={val_loss:.6f}")
    if val_loss < best_val:
        best_val = val_loss; patience_cnt = 0
        torch.save(model.state_dict(), MODELS/"lstm.pt")
    else:
        patience_cnt += 1
        if patience_cnt >= PATIENCE:
            print(f"  早停 epoch={epoch}"); break

model.load_state_dict(torch.load(MODELS/"lstm.pt", map_location=device, weights_only=False))
model.eval()

# 逐步预测最后30天：每步用真实历史窗口（teacher-forced），只预测下一步
# 与 SARIMA/HW 评估相同的30天，避免滚动误差累积
preds_norm = []
with torch.no_grad():
    for step in range(TEST_DAYS):
        t = len(data_arr) - TEST_DAYS + step
        inp = torch.tensor(data_arr[t - SEQ_LEN: t]).unsqueeze(0).to(device)
        p_norm = model(inp).item()
        preds_norm.append(p_norm)

pred_log = np.array(preds_norm) * _std + _mn
pred     = np.expm1(np.clip(pred_log, -10, 20)).clip(0)
actual   = y_raw[-TEST_DAYS:]

mask = actual > actual.mean() * 0.05
mape = (np.abs((pred[mask] - actual[mask]) / actual[mask])).mean() * 100
mae  = np.abs(pred - actual).mean()
print(f"[08] MAE={mae:.0f}  MAPE={mape:.2f}%")
pd.DataFrame({"actual": actual, "forecast": pred}).to_csv(OUT, index=False)
print(f"[08] ✅ LSTM 完成 → {OUT}")
import os; os._exit(0)
