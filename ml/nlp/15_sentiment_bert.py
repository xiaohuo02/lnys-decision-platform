# -*- coding: utf-8 -*-
"""15_sentiment_bert.py — BERT-Chinese 微调情感分类（GPU）"""
import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent.parent))
import pandas as pd, numpy as np, os
import torch
from torch.utils.data import Dataset, DataLoader
from transformers import (BertTokenizer, BertForSequenceClassification,
                           get_linear_schedule_with_warmup)
from torch.optim import AdamW
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score
from ml.config import *

OUT_MODEL = ART_NLP / "bert_sentiment"
OUT_METRICS = RES_NLP / "sentiment_bert_metrics.csv"
if OUT_MODEL.exists(): print("SKIP"); exit(0)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"[15] 使用设备: {device}")
if device.type == "cuda":
    torch.cuda.set_per_process_memory_fraction(GPU_MAX_MEM_GB / 8.0)

print("[15] 读取评论数据...")
df = pd.read_csv(REVIEWS_CSV)
df = df[df["review"].notna()].copy()
df["review"] = df["review"].astype(str).str[:128]

train_df, test_df = train_test_split(df, test_size=0.1, random_state=SEED, stratify=df["label"])
print(f"  训练={len(train_df):,}  测试={len(test_df):,}")

MODEL_NAME = "bert-base-chinese"
print(f"[15] 加载 tokenizer: {MODEL_NAME}")
tokenizer  = BertTokenizer.from_pretrained(MODEL_NAME)

class ReviewDataset(Dataset):
    def __init__(self, texts, labels, max_len=128):  # 128字捕获更多上下文
        self.enc = tokenizer(texts.tolist(), truncation=True, padding="max_length",
                             max_length=max_len, return_tensors="pt")
        self.labels = torch.tensor(labels.values, dtype=torch.long)
    def __len__(self): return len(self.labels)
    def __getitem__(self, i):
        return {k: v[i] for k,v in self.enc.items()}, self.labels[i]

tr_ds = ReviewDataset(train_df["review"], train_df["label"])
te_ds = ReviewDataset(test_df["review"],  test_df["label"])
tr_ld = DataLoader(tr_ds, batch_size=32, shuffle=True,  num_workers=0)
te_ld = DataLoader(te_ds, batch_size=64, shuffle=False, num_workers=0)

print("[15] 加载 BERT 模型...")
model = BertForSequenceClassification.from_pretrained(MODEL_NAME, num_labels=2).to(device)

EPOCHS   = 4
BASE_LR  = 2e-5
DECAY    = 0.8  # LLRD: 每层学习率乘以 decay

# LLRD: 下层 BERT 得到更小学习率—保护预训练知识
import torch.nn as nn
param_groups = []
for i, layer in enumerate(model.bert.encoder.layer):
    lr = BASE_LR * (DECAY ** (11 - i))
    param_groups.append({"params": layer.parameters(), "lr": lr, "weight_decay": 0.01})
param_groups.append({"params": model.bert.embeddings.parameters(), "lr": BASE_LR * (DECAY ** 12), "weight_decay": 0.01})
param_groups.append({"params": model.bert.pooler.parameters(),     "lr": BASE_LR * 0.9, "weight_decay": 0.01})
param_groups.append({"params": model.classifier.parameters(),      "lr": BASE_LR,       "weight_decay": 0.0})
opt = AdamW(param_groups)

total_steps = len(tr_ld) * EPOCHS
sched  = get_linear_schedule_with_warmup(opt, num_warmup_steps=int(total_steps*0.1),
                                          num_training_steps=total_steps)

loss_fn = nn.CrossEntropyLoss(label_smoothing=0.1)  # 标签平滑减少过拟合

print(f"[15] 开始训练 {EPOCHS} 个 epoch...")
for epoch in range(1, EPOCHS + 1):
    model.train()
    total_loss = 0
    for step, (batch, labels) in enumerate(tr_ld):
        batch   = {k: v.to(device) for k, v in batch.items()}
        labels  = labels.to(device)
        outputs = model(**batch)
        loss    = loss_fn(outputs.logits, labels)
        loss.backward(); opt.step(); sched.step(); opt.zero_grad()
        total_loss += loss.item()
        if (step+1) % 100 == 0:
            print(f"  epoch {epoch} step {step+1}/{len(tr_ld)}  loss={total_loss/(step+1):.4f}")

    model.eval()
    all_preds, all_labels = [], []
    with torch.no_grad():
        for batch, labels in te_ld:
            batch = {k: v.to(device) for k,v in batch.items()}
            logits = model(**batch).logits
            preds  = logits.argmax(-1).cpu().numpy()
            all_preds.extend(preds); all_labels.extend(labels.numpy())
    acc = accuracy_score(all_labels, all_preds)
    f1  = f1_score(all_labels, all_preds, average="macro")
    print(f"  epoch {epoch}  acc={acc:.4f}  macro-F1={f1:.4f}")

OUT_MODEL.mkdir(parents=True, exist_ok=True)
model.save_pretrained(str(OUT_MODEL))
tokenizer.save_pretrained(str(OUT_MODEL))
pd.DataFrame({"acc":[acc],"f1":[f1],"model":["BERT-Chinese"]}).to_csv(OUT_METRICS, index=False)
print(f"[15] ✅ BERT 微调完成 → {OUT_MODEL}")
import os; os._exit(0)
