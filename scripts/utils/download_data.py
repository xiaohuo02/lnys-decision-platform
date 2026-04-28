# -*- coding: utf-8 -*-
"""
数据集下载脚本
运行前确保已配置 kaggle API：C:\Users\<用户名>\.kaggle\kaggle.json
运行方式：.venv\Scripts\python scripts/download_data.py
"""

import os
import sys
import zipfile
import subprocess
from pathlib import Path

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

KAGGLE_DATASETS = [
    # (kaggle数据集路径, 本地目标文件名, 说明)
    ("mashlyn/online-retail-ii-uci",                                    "online_retail_II",   "UCI Online Retail II（订单主体）"),
    ("mlg-ulb/creditcardfraud",                                         "creditcard",         "Credit Card Fraud 经典版（欺诈风控）"),
    ("nelgiriyewithana/credit-card-fraud-detection-dataset-2023",       "creditcard_2023",    "Credit Card Fraud 2023（欺诈补充）"),
    ("mikhail1681/walmart-sales",                                       "walmart_sales",      "Walmart Store Sales（线下门店）"),
    ("ankitverma2010/ecommerce-customer-churn-analysis-and-prediction", "ecommerce_churn",    "E-Commerce Customer Churn（客户流失）"),
    ("prachi13/customer-churn",                                         "ecommerce_shipping", "E-Commerce Shipping（物流分析）"),
]

def check_kaggle():
    """检查 kaggle 是否可用"""
    kaggle_bin = Path(__file__).parent.parent / ".venv" / "Scripts" / "kaggle.exe"
    if not kaggle_bin.exists():
        print("❌ 未找到 kaggle，请先运行：.venv\\Scripts\\pip install kaggle")
        sys.exit(1)
    kaggle_json = Path.home() / ".kaggle" / "kaggle.json"
    if not kaggle_json.exists():
        print("❌ 未找到 kaggle.json，请：")
        print("   1. 登录 kaggle.com → Settings → API → Create New Token")
        print(f"   2. 将 kaggle.json 放到：{kaggle_json}")
        sys.exit(1)
    return str(kaggle_bin)

def download_dataset(kaggle_bin: str, dataset: str, folder_name: str, desc: str):
    """下载单个 kaggle 数据集并解压"""
    target_dir = RAW_DIR / folder_name
    if target_dir.exists() and any(target_dir.iterdir()):
        print(f"  ✅ 已存在，跳过：{desc}")
        return
    target_dir.mkdir(exist_ok=True)
    print(f"  ⬇️  正在下载：{desc}")
    result = subprocess.run(
        [kaggle_bin, "datasets", "download", "-d", dataset, "-p", str(target_dir), "--unzip"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  ❌ 下载失败：{result.stderr.strip()}")
    else:
        files = list(target_dir.iterdir())
        print(f"  ✅ 完成，文件：{[f.name for f in files]}")

def download_chinese_nlp():
    """下载中文购物评论数据集（GitHub）"""
    import urllib.request
    target_dir = RAW_DIR / "chinese_reviews"
    target_file = target_dir / "online_shopping_10_cats.csv"
    if target_file.exists():
        print(f"  ✅ 已存在，跳过：ChineseNlpCorpus 中文评论")
        return
    target_dir.mkdir(exist_ok=True)
    print("  ⬇️  正在下载：ChineseNlpCorpus 中文购物评论（GitHub）")
    url = "https://raw.githubusercontent.com/SophonPlus/ChineseNlpCorpus/master/datasets/online_shopping_10_cats/online_shopping_10_cats.csv"
    try:
        urllib.request.urlretrieve(url, target_file)
        size_mb = target_file.stat().st_size / 1024 / 1024
        print(f"  ✅ 完成，大小：{size_mb:.1f} MB")
    except Exception as e:
        print(f"  ❌ 下载失败：{e}")
        print("  💡 可手动下载：https://github.com/SophonPlus/ChineseNlpCorpus")
        print(f"     放到：{target_file}")

def main():
    print("=" * 60)
    print("柠优生活 - 原始数据集下载")
    print(f"下载目标目录：{RAW_DIR}")
    print("=" * 60)

    kaggle_bin = check_kaggle()

    print("\n[1/7] Kaggle 数据集...")
    for dataset, folder, desc in KAGGLE_DATASETS:
        download_dataset(kaggle_bin, dataset, folder, desc)

    print("\n[7/7] GitHub 数据集...")
    download_chinese_nlp()

    print("\n" + "=" * 60)
    print("下载完成！目录结构：")
    for item in sorted(RAW_DIR.iterdir()):
        if item.is_dir():
            files = list(item.iterdir())
            total_mb = sum(f.stat().st_size for f in files if f.is_file()) / 1024 / 1024
            print(f"  📁 {item.name}/  ({len(files)} 个文件，{total_mb:.1f} MB)")

if __name__ == "__main__":
    main()
