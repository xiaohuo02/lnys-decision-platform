# -*- coding: utf-8 -*-
"""19_customer_service.py — 客服意图分类（TF-IDF+SVM + BERT向量检索）"""
import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent.parent))
import pandas as pd, numpy as np, pickle
import jieba
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
from ml.config import *

OUT = RES_OPS / "cs_intent_result.csv"
if OUT.exists(): print("SKIP"); exit(0)

print("[19] 读取对话数据...")
df  = pd.read_csv(DIALOGUES_CSV)
faq = pd.read_csv(FAQ_CSV)
print(f"  对话条数: {len(df):,}  意图类别: {df['intent'].nunique()}")

# 分词
def tok(text):
    return " ".join([t for t in jieba.cut(str(text)) if len(t.strip()) > 1])

print("[19] 分词...")
df["tokens"] = df["user_query"].apply(tok)

X_tr, X_te, y_tr, y_te = train_test_split(
    df["tokens"], df["intent"], test_size=0.2, random_state=SEED, stratify=df["intent"])

# TF-IDF + LinearSVC
tfidf = TfidfVectorizer(max_features=5000, ngram_range=(1,2))
Xtr_v = tfidf.fit_transform(X_tr)
Xte_v = tfidf.transform(X_te)
clf   = LinearSVC(C=1.0, max_iter=2000)
clf.fit(Xtr_v, y_tr)

pred = clf.predict(Xte_v)
acc  = accuracy_score(y_te, pred)
print(f"[19] TF-IDF+SVC 意图准确率: {acc:.4f}")
print(classification_report(y_te, pred))

pickle.dump(tfidf, open(MODELS/"cs_tfidf.pkl","wb"))
pickle.dump(clf,   open(MODELS/"cs_svc.pkl","wb"))

# BERT 向量 FAQ 检索（如果 sentence-transformers 已安装）
print("[19] BERT 语义向量 FAQ 检索...")
_bert_ok = False
try:
    import torch
    from sentence_transformers import SentenceTransformer
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model_name = "paraphrase-multilingual-MiniLM-L12-v2"
    st_model_dir = ART_NLP / "st_model"
    # 优先用本地缓存，避免网络请求
    if st_model_dir.exists():
        st_model = SentenceTransformer(str(st_model_dir), device=device)
    else:
        st_model = SentenceTransformer(model_name, device=device)
        st_model.save(str(st_model_dir))
    faq_vecs = st_model.encode(faq["question"].tolist(), show_progress_bar=False, batch_size=32)
    np.save(MODELS/"faq_vectors.npy", faq_vecs)
    faq.to_csv(MODELS/"faq_indexed.csv", index=False, encoding="utf-8-sig")
    test_q  = "我的订单什么时候发货"
    q_vec   = st_model.encode([test_q])
    sims    = (faq_vecs @ q_vec.T).flatten()
    top_idx = sims.argmax()
    print(f"  测试检索: '{test_q}' → '{faq.iloc[top_idx]['question']}'  相似度={sims[top_idx]:.3f}")
    _bert_ok = True
except Exception as e:
    print(f"  BERT检索跳过(需网络或本地模型): {str(e)[:80]}")

result = pd.DataFrame({"query":X_te.values,"label":y_te.values,"pred":pred})
result.to_csv(OUT, index=False, encoding="utf-8-sig")
print(f"[19] ✅ 客服意图分类完成 → {OUT}  准确率={acc:.4f}  BERT检索={'OK' if _bert_ok else '跳过'}")
import os; os._exit(0)
