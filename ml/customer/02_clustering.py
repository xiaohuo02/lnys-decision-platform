# -*- coding: utf-8 -*-
"""02_clustering.py — K-Means + DBSCAN 客户分群"""
import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent.parent))
import os
import pandas as pd, numpy as np, pickle
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans, DBSCAN
from sklearn.metrics import silhouette_score
from ml.config import *

OUT = RES_CUSTOMER / "clustering_result.csv"
if OUT.exists(): print("SKIP"); import os; os._exit(0)

print("[02] 读取 RFM 数据...")
rfm = pd.read_csv(RES_CUSTOMER / "rfm_result.csv")
X = rfm[["Recency","Frequency","Monetary"]].copy()
# log1p 压缩 Frequency/Monetary 的长尾极端偶尔，再标准化
X["Frequency"] = np.log1p(X["Frequency"])
X["Monetary"]  = np.log1p(X["Monetary"])
scaler = StandardScaler()
Xs = scaler.fit_transform(X)
pickle.dump(scaler, open(MODELS/"scaler_rfm.pkl","wb"))

print("[02] KMeans 肘部法则 K=4~8...")
inertias, silhouettes = [], []
for k in range(4, 9):  
    km = KMeans(n_clusters=k, random_state=SEED, n_init=10)
    labels = km.fit_predict(Xs)
    inertias.append(km.inertia_)
    silhouettes.append(silhouette_score(Xs, labels))
    print(f"  K={k}  inertia={km.inertia_:.0f}  silhouette={silhouettes[-1]:.3f}")

best_k = np.argmax(silhouettes) + 4
print(f"[02] 最优 K={best_k}")
km_final = KMeans(n_clusters=best_k, random_state=SEED, n_init=20)
rfm["cluster"] = km_final.fit_predict(Xs)
pickle.dump(km_final, open(MODELS/"kmeans.pkl","wb"))

print("[02] DBSCAN 识别离群高价值客户...")
db = DBSCAN(eps=0.5, min_samples=5, n_jobs=CPU_N_JOBS)
rfm["dbscan_label"] = db.fit_predict(Xs)
outliers = rfm[rfm["dbscan_label"] == -1]
print(f"  DBSCAN 离群客户(高价值): {len(outliers)} 人")

rfm.to_csv(OUT, index=False, encoding="utf-8-sig")
print(f"[02] ✅ 聚类完成 → {OUT}")
print(rfm["cluster"].value_counts().to_string())
import os; os._exit(0)
