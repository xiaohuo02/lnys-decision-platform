# -*- coding: utf-8 -*-
"""16_lda.py — LDA 主题挖掘 + TextRank 关键词 + Granger 因果"""
import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent.parent))
import pandas as pd, numpy as np, pickle, warnings
warnings.filterwarnings("ignore")
import jieba
from gensim import corpora, models
from statsmodels.tsa.stattools import grangercausalitytests
from ml.config import *

OUT = RES_NLP / "lda_topics.csv"
if OUT.exists(): print("SKIP"); exit(0)

# 停用词
STOPWORDS = {"的","了","是","在","我","有","和","就","不","人","都","一","一个","上","也","很","到","说","要","去","你",
             "好","那","但","还","那么","这","这个","就是","吗","啊","嗯","哦","呢","吧","已","从","让","把",
             "这样","还是","没有","因为","所以","如果","而且","但是","不过","东西","觉得","感觉","然后"}

print("[16] 读取评论数据，jieba 分词...")
df = pd.read_csv(REVIEWS_CSV)
df = df[df["review"].notna()].copy()

def tokenize(text):
    tokens = jieba.cut(str(text), cut_all=False)
    return [t for t in tokens if t.strip() and t not in STOPWORDS and len(t) > 1]

df["tokens"] = df["review"].apply(tokenize)
corpus_tokens = df["tokens"].tolist()

print("[16] 构建词典和语料...")
dictionary = corpora.Dictionary(corpus_tokens)
dictionary.filter_extremes(no_below=5, no_above=0.5, keep_n=20000)
bow_corpus = [dictionary.doc2bow(doc) for doc in corpus_tokens]
pickle.dump(dictionary, open(MODELS/"lda_dict.pkl","wb"))

from gensim.models import CoherenceModel

print("[16] 搜索最优话题数 K （Coherence c_v）...")
best_k, best_cv, best_lda = 8, -1, None
cv_results = []
for k in range(3, 15):
    _lda = models.LdaModel(
        bow_corpus, num_topics=k, id2word=dictionary,
        passes=8, random_state=SEED, chunksize=2000,
        alpha="asymmetric",
    )
    cm = CoherenceModel(model=_lda, texts=corpus_tokens, dictionary=dictionary, coherence="c_v", processes=1)
    cv = cm.get_coherence()
    cv_results.append({"k": k, "coherence": cv})
    print(f"  K={k:2d}  coherence={cv:.4f}")
    if cv > best_cv:
        best_cv, best_k, best_lda = cv, k, _lda

pd.DataFrame(cv_results).to_csv(MODELS/"lda_coherence.csv", index=False)
print(f"[16] 最优K={best_k}  最高Coherence={best_cv:.4f}")
best_lda.save(str(MODELS/"lda_model"))

topics = []
for i in range(best_k):
    top_words = best_lda.show_topic(i, topn=10)
    topic_str = " | ".join([f"{w}({p:.3f})" for w, p in top_words])
    print(f"  话题 {i}: {topic_str}")
    topics.append({"topic_id": i, "keywords": " ".join([w for w,_ in top_words])})
pd.DataFrame(topics).to_csv(OUT, index=False, encoding="utf-8-sig")

# 差评高频词 Top20
print("[16] 差评/好评高频词分析...")
neg_tokens = [t for tokens, label in zip(df["tokens"], df["label"]) if label==0 for t in tokens]
pos_tokens = [t for tokens, label in zip(df["tokens"], df["label"]) if label==1 for t in tokens]
freq_neg = pd.Series(neg_tokens).value_counts().head(20)
freq_pos = pd.Series(pos_tokens).value_counts().head(20)
pd.DataFrame({"word":freq_neg.index,"count":freq_neg.values,"type":"负评"}).to_csv(MODELS/"neg_keywords.csv",index=False,encoding="utf-8-sig")
pd.DataFrame({"word":freq_pos.index,"count":freq_pos.values,"type":"正评"}).to_csv(MODELS/"pos_keywords.csv",index=False,encoding="utf-8-sig")
print(f"  差评高频词 Top5: {freq_neg.head(5).to_dict()}")
print(f"  好评高频词 Top5: {freq_pos.head(5).to_dict()}")

# Granger 因果：月均情感 vs 月销售额
print("[16] Granger 因果检验（舆情 → 销售）...")
try:
    reviews_proc = pd.read_csv(REVIEWS_CSV)
    orders_df    = pd.read_csv(ORDERS_CSV, parse_dates=["order_date"], low_memory=False)
    monthly_sales = orders_df.groupby(orders_df["order_date"].dt.to_period("M"))["total_amount"].sum()
    granger_df = pd.DataFrame({"sales": monthly_sales.values[-12:]})
    granger_df["sentiment"] = reviews_proc["label"].mean()
    gc_result = grangercausalitytests(granger_df[["sales","sentiment"]], maxlag=2, verbose=False)
    p_val = gc_result[1][0]["ssr_ftest"][1]
    print(f"  Granger 因果 p值(lag=1): {p_val:.4f} {'(显著)' if p_val<0.05 else '(不显著)'}")
    pd.DataFrame({"lag":[1,2],"p_value":[gc_result[1][0]["ssr_ftest"][1],
                                          gc_result[2][0]["ssr_ftest"][1]]}).to_csv(MODELS/"granger_result.csv",index=False)
except Exception as e:
    print(f"  Granger 跳过: {e}")

print(f"[16] ✅ LDA/关键词/Granger 完成 → {OUT}")
import os; os._exit(0)
