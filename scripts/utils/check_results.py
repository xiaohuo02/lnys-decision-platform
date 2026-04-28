# -*- coding: utf-8 -*-
"""检查所有已完成算法的训练结果和质量指标"""
import pandas as pd, numpy as np, pickle, warnings
warnings.filterwarnings("ignore")
from pathlib import Path

ROOT = Path(".")
M    = ROOT / "models"
RES  = M / "results"
ART  = M / "artifacts"
RC   = RES / "customer"
RF   = RES / "forecast"
RFR  = RES / "fraud"
RN   = RES / "nlp"
RO   = RES / "ops"
AN   = ART / "nlp"

BAR = "=" * 58

def sep(title):
    print(f"\n{BAR}\n  {title}\n{BAR}")

def safe_read(path_obj):
    if not path_obj.exists():
        print(f"  ⚠ 文件不存在: {path_obj.name}")
        return None
    return pd.read_csv(path_obj)

# ── 01 RFM ───────────────────────────────────────────────
sep("01  RFM 客户价值分析")
df = safe_read(RC/"rfm_result.csv")
if df is not None:
    print(f"  客户总数: {len(df):,}")
    if "segment" in df.columns:
        print(df["segment"].value_counts().to_string())
    print(f"  R均值={df['Recency'].mean():.1f}天  F均值={df['Frequency'].mean():.1f}次  M均值={df['Monetary'].mean():.0f}元")

# ── 02 K-Means ───────────────────────────────────────────
sep("02  K-Means 客户聚类")
df = safe_read(RC/"clustering_result.csv")
if df is not None:
    print(f"  客户数: {len(df):,}  簇数: {df['cluster'].nunique()}  DBSCAN簇数: {df['dbscan_label'].nunique()}")
    dist = df["cluster"].value_counts().sort_index().rename("客户数")
    print(dist.to_string())
    if dist.min() < len(df)*0.02:
        print("  ⚠ 聚类分布极度不均衡，建议检查特征归一化或簇数参数")

# ── 03 流失预测 ──────────────────────────────────────────
sep("03  XGBoost 流失预测 + SHAP")
df = safe_read(RC/"churn_result.csv")
if df is not None:
    from sklearn.metrics import roc_auc_score, f1_score, precision_score, recall_score
    lbl, prob = df["label"], df["pred_proba"]
    pred = (prob > 0.5).astype(int)
    print(f"  样本={len(df):,}  流失率={lbl.mean()*100:.2f}%")
    print(f"  AUC={roc_auc_score(lbl,prob):.4f}  F1={f1_score(lbl,pred):.4f}")
    print(f"  Precision={precision_score(lbl,pred):.4f}  Recall={recall_score(lbl,pred):.4f}")

# ── 04 CLV ───────────────────────────────────────────────
sep("04  BG-NBD CLV 预测")
df = safe_read(RC/"clv_result.csv")
if df is not None:
    print(f"  客户数: {len(df):,}")
    print(f"  CLV(90天): 均值={df['clv_90d'].mean():.0f}  中位={df['clv_90d'].median():.0f}  Max={df['clv_90d'].max():.0f}")
    print(f"  预测购买次数(90天): 均值={df['pred_purchases_90d'].mean():.2f}  Max={df['pred_purchases_90d'].max():.2f}")

# ── 05 Cohort ────────────────────────────────────────────
sep("05  Cohort 留存分析")
df = safe_read(RC/"cohort_retention.csv")
if df is not None:
    vals = df.select_dtypes(include=np.number).values.flatten()
    vals = vals[~np.isnan(vals) & (vals > 0)]
    print(f"  Cohort矩阵: {df.shape[0]} 期")
    print(f"  留存率: 均值={vals.mean()*100:.1f}%  Max={vals.max()*100:.1f}%  Min={vals.min()*100:.1f}%")

# ── 06 SARIMA ────────────────────────────────────────────
sep("06  SARIMA 销售预测")
df = safe_read(RF/"sarima_result.csv")
if df is not None:
    a, f = df["actual"].values, df["forecast"].values
    mask = a > a.mean() * 0.05
    mape = np.mean(np.abs((f[mask]-a[mask])/a[mask]))*100
    mae  = np.abs(f-a).mean()
    print(f"  测试集={len(df)}天  MAE={mae:,.0f}  MAPE={mape:.1f}%")
    print(f"  实际范围: {a.min():,.0f} ~ {a.max():,.0f}")
    print(f"  预测范围: {f.min():,.0f} ~ {f.max():,.0f}")

# ── 07 Holt-Winters ──────────────────────────────────────
sep("07  Holt-Winters ETS 销售预测")
df = safe_read(RF/"prophet_result.csv")
if df is not None:
    a, f = df["actual"].values, df["forecast"].values
    mask = a > a.mean() * 0.05
    mape = np.mean(np.abs((f[mask]-a[mask])/a[mask]))*100
    mae  = np.abs(f-a).mean()
    print(f"  测试集={len(df)}天  MAE={mae:,.0f}  MAPE={mape:.1f}%")

# ── 08 LSTM ──────────────────────────────────────────────
sep("08  LSTM 销售预测")
df = safe_read(RF/"lstm_result.csv")
if df is not None:
    a, f = df["actual"].values, df["forecast"].values
    mape = np.mean(np.abs((f-a)/(a+1)))*100
    mae  = np.abs(f-a).mean()
    print(f"  样本={len(df)}  MAE={mae:,.0f}  MAPE={mape:.1f}%")

# ── 09 XGB 销售回归 ──────────────────────────────────────
sep("09  XGBoost 销售回归")
df = safe_read(RF/"sales_xgb_result.csv")
if df is not None:
    a, f = df["actual"].values, df["forecast"].values
    mask = a > a.mean() * 0.05
    mape = np.mean(np.abs((f[mask]-a[mask])/a[mask]))*100
    mae  = np.abs(f-a).mean()
    print(f"  样本={len(df)}  MAE={mae:,.0f}  MAPE={mape:.1f}%")

# ── 10 Stacking ──────────────────────────────────────────
sep("10  Stacking 集成融合")
df = safe_read(RF/"stacking_result.csv")
if df is not None:
    a, ens = df["actual"].values, df["ensemble"].values
    mask = a > a.mean() * 0.05
    mape = np.mean(np.abs((ens[mask]-a[mask])/a[mask]))*100
    print(f"  融合模型数: {len([c for c in df.columns if c.startswith('pred_')])}  Stacking MAPE={mape:.1f}%")
    for col in [c for c in df.columns if c.startswith("pred_")]:
        p = df[col].values
        m = np.mean(np.abs((p[mask]-a[mask])/a[mask]))*100
        print(f"    {col.replace('pred_','')}: MAPE={m:.1f}%")

# ── 11 IsolationForest ───────────────────────────────────
sep("11  Isolation Forest 欺诈检测")
df = safe_read(RFR/"fraud_iso_result.csv")
if df is not None:
    from sklearn.metrics import roc_auc_score
    auc = roc_auc_score(df["label"], df["iso_score"])
    high_risk = (df["risk_level"].isin(["高风险","极高风险"]) if "risk_level" in df.columns else df["total_risk"]>50).mean()
    print(f"  样本={len(df):,}  AUC={auc:.4f}  高风险标记率={high_risk*100:.2f}%")

# ── 12 监督学习对比 ──────────────────────────────────────
sep("12  LR/RF/XGB/LGB 欺诈对比")
df = safe_read(RFR/"fraud_supervised_result.csv")
if df is not None:
    print(df.to_string(index=False))

# ── 13 AutoEncoder ───────────────────────────────────────
sep("13  AutoEncoder 异常检测")
df = safe_read(RFR/"fraud_ae_result.csv")
if df is not None:
    from sklearn.metrics import roc_auc_score
    score_col = "hybrid_score" if "hybrid_score" in df.columns else "recon_error"
    auc = roc_auc_score(df["label"], df[score_col])
    print(f"  样本={len(df):,}  AUC={auc:.4f}  (分数列={score_col})")
    thr = df[df["label"]==0][score_col].quantile(0.95)
    pred = (df[score_col] > thr).astype(int)
    tp = ((pred==1)&(df["label"]==1)).sum()
    fp = ((pred==1)&(df["label"]==0)).sum()
    print(f"  阈值@95th: {thr:.4f}  捕获欺诈={tp}  误报={fp}")

# ── 14 TF-IDF 情感 ───────────────────────────────────────
sep("14  TF-IDF 情感分类")
df = safe_read(RN/"sentiment_tfidf_result.csv")
if df is not None:
    from sklearn.metrics import accuracy_score, f1_score
    acc = accuracy_score(df["label"], df["pred"])
    f1  = f1_score(df["label"], df["pred"], average="macro")
    print(f"  样本={len(df):,}  Accuracy={acc:.4f}  Macro-F1={f1:.4f}")

# ── 15 BERT ──────────────────────────────────────────────
sep("15  BERT-Chinese 情感微调")
p = AN / "bert_sentiment"
if p.exists():
    m = safe_read(RN/"sentiment_tfidf_metrics.csv")  # 用tfidf metrics作对比
    mf = RN / "sentiment_tfidf_metrics.csv"
    print(f"  模型目录: {p}  ({sum(1 for _ in p.iterdir())} 文件)")
    # 读bert metrics
    bm = AN / "bert_sentiment" / "metrics.csv" if (AN/"bert_sentiment"/"metrics.csv").exists() else None
    metrics_files = list(p.glob("*.csv"))
    if metrics_files:
        bdf = pd.read_csv(metrics_files[0])
        print(bdf.to_string(index=False))
    else:
        print("  (metrics文件不在bert_sentiment目录，查找...)")
        bm2 = list(RN.glob("*bert*metrics*"))
        for f in bm2:
            print(f"  {f.name}:", pd.read_csv(f).to_string(index=False))
else:
    print("  ⚠ BERT 模型未完成训练")

# ── 16 LDA ───────────────────────────────────────────────
sep("16  LDA 主题模型")
df = safe_read(RN/"lda_topics.csv")
if df is not None:
    print(f"  话题数: {len(df)}")
    for _, row in df.iterrows():
        print(f"  话题{row['topic_id']}: {row['keywords'][:60]}")
    neg = safe_read(RN/"neg_keywords.csv")
    pos = safe_read(RN/"pos_keywords.csv")
    if neg is not None:
        print(f"  差评高频词Top5: {neg.head(5)['word'].tolist()}")
    if pos is not None:
        print(f"  好评高频词Top5: {pos.head(5)['word'].tolist()}")
else:
    print("  ⚠ LDA 尚未完成")

# ── 17 库存分析 ──────────────────────────────────────────
sep("17  ABC-XYZ + EOQ 库存分析")
df = safe_read(RO/"inventory_analysis.csv")
if df is not None:
    print(f"  SKU数: {len(df):,}")
    print("  ABC分布:")
    print(df["ABC"].value_counts().to_string())
    print("  XYZ分布:")
    print(df["XYZ"].value_counts().to_string())
    print(f"  EOQ均值: {df['eoq'].mean():.0f}  安全库存均值: {df['safety_stock'].mean():.0f}")

# ── 18 FP-Growth 关联规则 ──────────────────────────────────
sep("18  FP-Growth 关联规则")
df = safe_read(RO/"association_rules.csv")
if df is not None:
    print(f"  规则总数: {len(df):,}")
    print(f"  support: 均值={df['support'].mean():.3f}  最大={df['support'].max():.3f}")
    print(f"  confidence: 均值={df['confidence'].mean():.3f}")
    print(f"  lift: 均值={df['lift'].mean():.3f}  最大={df['lift'].max():.3f}")
    import re
    def parse_fset(s):
        return re.findall(r"'([^']+)'", str(s))
    print(f"  Top5 高lift规则:")
    top = df.nlargest(5, 'lift')[['antecedents','consequents','support','confidence','lift']]
    for _, r in top.iterrows():
        ant = parse_fset(r['antecedents']); con = parse_fset(r['consequents'])
        print(f"    {ant} → {con}  lift={r['lift']:.2f}  conf={r['confidence']:.2f}")
else:
    print("  ⚠ 关联规则尚未完成")

# ── 19 客服意图 ──────────────────────────────────────────
sep("19  客服意图分类 + FAQ检索")
df = safe_read(RO/"cs_intent_result.csv")
if df is not None:
    from sklearn.metrics import accuracy_score, f1_score
    acc = accuracy_score(df["label"], df["pred"])
    f1  = f1_score(df["label"], df["pred"], average="macro")
    print(f"  样本={len(df):,}  Accuracy={acc:.4f}  Macro-F1={f1:.4f}")
    print(f"  意图类别数: {df['label'].nunique()}")

print(f"\n{'='*58}")
print("  汇总完毕")
print(f"{'='*58}")
