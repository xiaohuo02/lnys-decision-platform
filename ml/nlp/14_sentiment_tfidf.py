# -*- coding: utf-8 -*-
"""14_sentiment_tfidf.py — TF-IDF + LinearSVC 情感分类（基准）"""
import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent.parent))
import pandas as pd, numpy as np, pickle
import jieba
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.pipeline import Pipeline, FeatureUnion
from sklearn.model_selection import train_test_split, GridSearchCV
from sklearn.metrics import accuracy_score, f1_score, classification_report
from ml.config import *

OUT = RES_NLP / "sentiment_tfidf_result.csv"
if OUT.exists(): print("SKIP"); exit(0)

print("[14] 读取评论数据...")
df = pd.read_csv(REVIEWS_CSV)
df = df[df["review"].notna() & (df["review"].str.len() >= 3)].copy()
print(f"  样本数: {len(df):,}")

print("[14] jieba 分词（约5分钟）...")
def tokenize(text):
    return " ".join(jieba.cut(str(text), cut_all=False))

df["tokens"] = df["review"].apply(tokenize)

X_tr, X_te, y_tr, y_te = train_test_split(
    df["tokens"], df["label"], test_size=0.2, random_state=42, stratify=df["label"])

print("[14] 构建词+字符双路 TF-IDF FeatureUnion...")
# 词级 n-gram (1,2) + 字符级 char_wb n-gram (2,4)
word_tfidf = TfidfVectorizer(analyzer="word",  max_features=30000, ngram_range=(1,2), min_df=3, sublinear_tf=True)
char_tfidf = TfidfVectorizer(analyzer="char_wb", max_features=20000, ngram_range=(2,4), min_df=5, sublinear_tf=True)

pipeline = Pipeline([
    ("features", FeatureUnion([
        ("word", word_tfidf),
        ("char", char_tfidf),
    ])),
    ("clf", LinearSVC(max_iter=3000)),
])

print("[14] GridSearchCV 搜索最优 C...")
param_grid = {"clf__C": [0.1, 0.5, 1.0, 3.0, 5.0]}
gs = GridSearchCV(pipeline, param_grid, cv=5, scoring="f1_macro", n_jobs=1, verbose=1)
gs.fit(X_tr, y_tr)
print(f"  最优C={gs.best_params_}  CV-F1={gs.best_score_:.4f}")
best_pipe = gs.best_estimator_

pickle.dump(best_pipe, open(MODELS/"tfidf_sentiment.pkl","wb"))

pred = best_pipe.predict(X_te)
acc  = accuracy_score(y_te, pred)
f1   = f1_score(y_te, pred, average="macro")
print(f"[14] Accuracy={acc:.4f}  Macro-F1={f1:.4f}")
print(classification_report(y_te, pred, target_names=["负评","正评"]))

result = pd.DataFrame({"label":y_te.values,"pred":pred})
result.to_csv(OUT, index=False)
pd.DataFrame({"acc":[acc],"f1":[f1],"model":["TF-IDF+SVC"]}).to_csv(MODELS/"sentiment_tfidf_metrics.csv",index=False)
print(f"[14] ✅ TF-IDF 情感分类完成 → {OUT}")
import os; os._exit(0)
