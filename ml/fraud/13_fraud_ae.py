# -*- coding: utf-8 -*-
"""13_fraud_ae.py — AutoEncoder 深度异常检测（GPU）"""
import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent.parent))
import pandas as pd, numpy as np
import torch, torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import IsolationForest
from sklearn.metrics import roc_auc_score
import pickle
from ml.config import *

OUT = RES_FRAUD / "fraud_ae_result.csv"
if OUT.exists(): print("SKIP"); exit(0)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"[13] 使用设备: {device}")
if device.type == "cuda":
    torch.cuda.set_per_process_memory_fraction(GPU_MAX_MEM_GB / 8.0)

print("[13] 读取欺诈数据...")
df    = pd.read_csv(FRAUD_CSV)
v_cols = [c for c in df.columns if c.startswith("V")]
feats = v_cols + ["amount_cny"]
feats = [c for c in feats if c in df.columns]
X, y  = df[feats].values.astype(np.float32), df["label"].values
sc    = StandardScaler(); X = sc.fit_transform(X)
pickle.dump(sc, open(MODELS/"ae_scaler.pkl","wb"))

X_normal = X[y == 0]
print(f"[13] 用正常样本训练: {len(X_normal):,}")

class AutoEncoder(nn.Module):
    def __init__(self, dim):
        super().__init__()
        self.enc = nn.Sequential(nn.Linear(dim,32),nn.ReLU(),nn.Linear(32,16),nn.ReLU(),nn.Linear(16,8))
        self.dec = nn.Sequential(nn.Linear(8,16), nn.ReLU(),nn.Linear(16,32),nn.ReLU(),nn.Linear(32,dim))
    def forward(self, x): return self.dec(self.enc(x))

dim   = X.shape[1]
model = AutoEncoder(dim).to(device)
opt   = torch.optim.Adam(model.parameters(), lr=1e-3)
loss_fn = nn.MSELoss()

tr_tensor = torch.tensor(X_normal)
loader    = DataLoader(TensorDataset(tr_tensor), batch_size=256, shuffle=True)
best_loss, patience, PATIENCE = float("inf"), 0, 10
print("[13] 训练 AutoEncoder...")
for epoch in range(1, 81):
    model.train()
    ep_loss = sum(loss_fn(model(xb[0].to(device)), xb[0].to(device)).item() for xb in loader) / len(loader)
    if epoch % 10 == 0: print(f"  epoch {epoch:3d}  loss={ep_loss:.6f}")
    if ep_loss < best_loss:
        best_loss = ep_loss; patience = 0
        torch.save(model.state_dict(), MODELS/"ae.pt")
    else:
        patience += 1
        if patience >= PATIENCE: print(f"  早停 epoch={epoch}"); break

model.load_state_dict(torch.load(MODELS/"ae.pt", map_location=device))
model.eval()
with torch.no_grad():
    X_t     = torch.tensor(X).to(device)
    recon   = model(X_t).cpu().numpy()
    recon_err = np.mean((X - recon)**2, axis=1)

auc_ae = roc_auc_score(y, recon_err)
print(f"[13] AutoEncoder AUC={auc_ae:.4f}")

# 混合 IsoForest 异常分数 → 提升组合 AUC
print("[13] 训练 IsoForest 进行混合集成...")
iso = IsolationForest(n_estimators=200, contamination=max(0.001, float(y.mean())),
                      random_state=SEED, n_jobs=CPU_N_JOBS, max_samples="auto")
iso.fit(X[y == 0])
iso_scores = -iso.score_samples(X)

# 分别归一化到 [0,1]
def minmax(arr): return (arr - arr.min()) / (arr.max() - arr.min() + 1e-10)
recon_norm = minmax(recon_err)
iso_norm   = minmax(iso_scores)

# 加权融合：AE 0.6 + IsoForest 0.4
hybrid = 0.6 * recon_norm + 0.4 * iso_norm
auc_hybrid = roc_auc_score(y, hybrid)
print(f"[13] 混合 AUC={auc_hybrid:.4f}  (笔 AE={auc_ae:.4f}，IsoForest={roc_auc_score(y, iso_scores):.4f})")

# 阈値与来源和  （90th 百分位作阈値）
threshold = np.percentile(hybrid[y == 0], 95)
flag = (hybrid > threshold).astype(int)
print(f"  阈値@95th: {threshold:.4f}  捕获欺诈={int((flag[y==1]).sum())}  误报={int((flag[y==0]).sum())}")

df_out = pd.DataFrame({"label":y, "recon_error":recon_err, "iso_score":iso_scores, "hybrid_score":hybrid})
df_out.to_csv(OUT, index=False)
print(f"[13] ✅ AutoEncoder+IsoForest 混合完成 → {OUT}")
auc = auc_hybrid
import os; os._exit(0)
