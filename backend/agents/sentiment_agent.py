# -*- coding: utf-8 -*-
"""backend/agents/sentiment_agent.py — 舆情分析 Agent（BERT + LDA + TF-IDF）

Cascade 架构:
  bert_analyze()  → Tier 1 本地推断 (softmax 置信度)
  tfidf_analyze() → 当 BERT 不可用时的 fallback
"""
import math
import pickle
from typing import Any, Dict, Optional

from loguru import logger

from backend.agents.base_agent import BaseAgent
from backend.config import settings

_LABEL_MAP = {0: "负面", 1: "正面"}
_NEUTRAL_KW = {"一般", "还行", "马马虎虎", "凑合", "普通",
               "还可以", "一般般", "中等", "尚可", "soso"}


class SentimentAgent(BaseAgent):
    """加载 BERT-Chinese 微调模型 + LDA 主题模型 + TF-IDF 基准"""

    def __init__(self, redis):
        super().__init__("sentiment", redis)
        self.svc_model  = pickle.load(open(settings.ART_NLP / "svc_sentiment.pkl",   "rb"))
        self.tfidf_vec  = pickle.load(open(settings.ART_NLP / "tfidf_sentiment.pkl", "rb"))
        self.lda_dict   = pickle.load(open(settings.ART_NLP / "lda_dict.pkl",        "rb"))

        # BERT 模型（Transformers）— 启用
        self.bert_tokenizer = None
        self.bert_model = None
        self._torch = None
        try:
            import torch
            from transformers import BertForSequenceClassification, BertTokenizer
            bert_path = settings.ART_NLP / "bert_sentiment"
            if bert_path.exists():
                self.bert_tokenizer = BertTokenizer.from_pretrained(str(bert_path))
                self.bert_model = BertForSequenceClassification.from_pretrained(str(bert_path))
                self.bert_model.eval()
                self._torch = torch
                logger.info("[SentimentAgent] BERT-Chinese 加载成功")
            else:
                logger.warning(f"[SentimentAgent] BERT 路径不存在: {bert_path}")
        except ImportError:
            logger.warning("[SentimentAgent] torch/transformers 未安装，BERT 不可用")
        except Exception as e:
            logger.warning(f"[SentimentAgent] BERT 加载失败: {e}")

    @property
    def bert_available(self) -> bool:
        return self.bert_model is not None and self.bert_tokenizer is not None

    async def perceive(self, input_data: Any) -> dict:
        return {"input": input_data, "memory": await self.memory_read()}

    async def reason(self, context: dict) -> dict:
        return {"strategy": "bert_inference" if self.bert_available else "tfidf_inference"}

    async def act(self, plan: dict) -> dict:
        return {}

    async def reflect(self, result: dict) -> dict:
        neg_ratio = result.get("negative_ratio", 0)
        if neg_ratio > 0.3:
            await self.publish_event("agent:customer_action", {"trigger": "sentiment_negative"})
        return result

    async def output(self, result: dict) -> dict:
        await self.memory_write("latest_sentiment", result)
        return result

    def bert_analyze(self, text: str) -> Optional[Dict[str, Any]]:
        """BERT-Chinese 推断，返回 softmax 置信度"""
        if not self.bert_available:
            return None
        try:
            torch = self._torch
            inputs = self.bert_tokenizer(
                text, return_tensors="pt", truncation=True,
                max_length=256, padding=True,
            )
            with torch.no_grad():
                outputs = self.bert_model(**inputs)
                logits = outputs.logits[0]
                probs = torch.softmax(logits, dim=-1)
                label_idx = int(torch.argmax(probs).item())
                confidence = float(probs[label_idx].item())

            is_neutral = any(nk in text for nk in _NEUTRAL_KW)
            if is_neutral:
                label_str = "中性"
                confidence = 0.70
            else:
                label_str = _LABEL_MAP.get(label_idx, "中性")

            return {
                "label": label_str,
                "confidence": round(confidence, 4),
                "score": round(float(logits[label_idx].item()), 4),
                "model": "bert-chinese",
            }
        except Exception as e:
            logger.warning(f"[SentimentAgent] BERT 推断失败: {e}")
            return None

    def tfidf_analyze(self, text: str) -> Optional[Dict[str, Any]]:
        """TF-IDF + SVC 推断（fallback）"""
        try:
            pipeline = self.tfidf_vec
            label_idx = int(pipeline.predict([text])[0])
            try:
                features = pipeline.named_steps["features"].transform([text])
                score = float(pipeline.named_steps["clf"].decision_function(features)[0])
            except Exception:
                score = 0.0

            is_neutral = any(nk in text for nk in _NEUTRAL_KW)
            if is_neutral:
                label_str = "中性"
                conf = 0.70
            else:
                label_str = _LABEL_MAP.get(label_idx, "中性")
                conf = round(1.0 / (1.0 + math.exp(-1.2 * abs(score))), 3)

            return {
                "label": label_str,
                "confidence": conf,
                "score": round(score, 4),
                "model": "tfidf-svc",
            }
        except Exception as e:
            logger.warning(f"[SentimentAgent] TF-IDF 推断失败: {e}")
            return None

    def analyze(self, text: str) -> Optional[Dict[str, Any]]:
        """统一入口：BERT 优先，TF-IDF fallback"""
        result = self.bert_analyze(text)
        if result is not None:
            return result
        return self.tfidf_analyze(text)
