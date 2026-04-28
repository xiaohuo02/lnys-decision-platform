# -*- coding: utf-8 -*-
"""ml/config.py — 所有训练脚本共享配置"""
import os
from pathlib import Path

ROOT     = Path(__file__).parent.parent
PROC     = ROOT / "data" / "processed"
GEN      = ROOT / "data" / "generated"
RAW      = ROOT / "data" / "raw"
MODELS   = ROOT / "models"
LOGS     = ROOT / "logs"
CKPT_DIR = ROOT / "checkpoints"

# 分层模型目录（归档规范 v1.1）
ARTIFACTS = MODELS / "artifacts"
RESULTS   = MODELS / "results"

ART_CUSTOMER = ARTIFACTS / "customer"
ART_FORECAST = ARTIFACTS / "forecast"
ART_FRAUD    = ARTIFACTS / "fraud"
ART_NLP      = ARTIFACTS / "nlp"

RES_CUSTOMER = RESULTS / "customer"
RES_FORECAST = RESULTS / "forecast"
RES_FRAUD    = RESULTS / "fraud"
RES_NLP      = RESULTS / "nlp"
RES_OPS      = RESULTS / "ops"

for d in [MODELS, LOGS, CKPT_DIR,
          ART_CUSTOMER, ART_FORECAST, ART_FRAUD, ART_NLP,
          RES_CUSTOMER, RES_FORECAST, RES_FRAUD, RES_NLP, RES_OPS]:
    d.mkdir(parents=True, exist_ok=True)

# GPU/CPU 安全限制
GPU_MAX_UTIL   = 0.78   # GPU 利用率上限 78%
GPU_MAX_MEM_GB = 6.0    # GPU 显存上限 6GB（留 2GB 余量）
CPU_MAX_UTIL   = 0.72   # CPU 占用率上限 72%
CPU_N_JOBS     = 10     # 并发 CPU 核心数（共20线程，留余量）

SEED = 42

# 数据文件
ORDERS_CSV   = PROC / "orders_cn.csv"
CUSTOMERS_CSV= PROC / "customers_cn.csv"
FRAUD_CSV    = PROC / "fraud_cn.csv"
STORES_CSV   = PROC / "stores_offline.csv"
REVIEWS_CSV  = PROC / "reviews_cn.csv"
INVENTORY_CSV= GEN  / "inventory.csv"
DIALOGUES_CSV= GEN  / "dialogues.csv"
FAQ_CSV      = GEN  / "faq.csv"
CHURN_CSV    = RAW  / "churn_supplement" / "ecommerce_customer_churn_dataset.csv"
