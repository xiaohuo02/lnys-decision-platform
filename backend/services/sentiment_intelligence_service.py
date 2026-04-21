# -*- coding: utf-8 -*-
"""backend/services/sentiment_intelligence_service.py

SentimentIntelligenceService — 舆情分析服务

╔══════════════════════════════════════════════════════════════════╗
║  Agent 契约                                                       ║
╠══════════════════════════════════════════════════════════════════╣
║  输入   : SentimentRequest（数据来源、负面预警阈值）               ║
║  输出   : SentimentResult（情感分布、负面占比、Top 负面主题 + ref）║
║  可调用 : models/results/nlp/*.csv 读取、TF-IDF/SVC 在线推断      ║
║  禁止   : 自动触发业务动作、直接写 DB                              ║
║  降级   : 无预计算结果时读原始评论 + TF-IDF 推断；全部失败返空      ║
║  HITL   : 不需要（高负面占比由 InsightComposerAgent 汇入摘要）     ║
║  依赖   : models/results/nlp/sentiment_result.csv（主路）         ║
║           models/results/nlp/lda_result.csv（主题）              ║
║           models/artifacts/nlp/svc_sentiment.pkl（fallback）     ║
║  Trace  : step_name="sentiment_intel"                            ║
║           output_summary=negative_ratio + top_themes            ║
╚══════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
from loguru import logger
from pydantic import BaseModel, Field

from backend.config import settings
from backend.schemas.artifact import ArtifactRef, ArtifactType


_RESULTS  = settings.MODELS_ROOT / "results" / "nlp"
_ARTIFACT = settings.ART_NLP
_DATA_ROOT = settings.MODELS_ROOT.parent / "data"


class SentimentRequest(BaseModel):
    run_id:              Optional[str] = None
    negative_threshold:  float = 0.3      # 超过该比例触发预警摘要
    top_n_themes:        int   = 5
    nrows:               Optional[int] = None


class ThemeSummary(BaseModel):
    theme:      str
    count:      int
    sample_phrases: List[str] = Field(default_factory=list)


class SentimentResult(BaseModel):
    run_id:          Optional[str]
    data_ready:      bool
    degraded:        bool = False

    positive_ratio:  float = 0.0
    neutral_ratio:   float = 0.0
    negative_ratio:  float = 0.0
    total_reviews:   int   = 0

    negative_alert:  bool  = False
    top_themes:      List[ThemeSummary] = Field(default_factory=list)

    artifact:        Optional[ArtifactRef] = None
    error_message:   Optional[str] = None
    analyzed_at:     datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SentimentIntelligenceService:

    def analyze(self, request: SentimentRequest) -> SentimentResult:
        result = SentimentResult(run_id=request.run_id, data_ready=False)

        ok_sent   = self._load_sentiment(result, request)
        ok_themes = self._load_lda_themes(result, request)

        if not ok_sent:
            ok_sent = self._infer_sentiment_fallback(result, request)

        result.data_ready = ok_sent
        result.degraded   = ok_sent and not ok_themes

        if result.data_ready:
            result.negative_alert = result.negative_ratio >= request.negative_threshold
            result.artifact = ArtifactRef(
                artifact_type=ArtifactType.SENTIMENT,
                summary=(
                    f"舆情分析: 评价 {result.total_reviews} 条, "
                    f"负面 {result.negative_ratio:.1%}"
                    + ("⚠️" if result.negative_alert else "")
                ),
            )

        logger.info(
            f"[SentimentService] total={result.total_reviews} "
            f"neg={result.negative_ratio:.2%} alert={result.negative_alert} "
            f"data_ready={result.data_ready}"
        )
        return result

    def _load_sentiment(self, result: SentimentResult, request: SentimentRequest) -> bool:
        path = _RESULTS / "sentiment_tfidf_result.csv"
        if not path.exists():
            return False
        try:
            df = pd.read_csv(path, nrows=request.nrows)
            if "label" not in df.columns and "pred_label" not in df.columns:
                return False
            col = "pred_label" if "pred_label" in df.columns else "label"
            total = len(df)
            result.total_reviews  = total
            result.positive_ratio = round(float((df[col] == 2).sum() / total), 4)
            result.neutral_ratio  = round(float((df[col] == 1).sum() / total), 4)
            result.negative_ratio = round(float((df[col] == 0).sum() / total), 4)
            return True
        except Exception as e:
            logger.warning(f"[SentimentService] sentiment_result 加载失败: {e}")
            return False

    def _load_lda_themes(self, result: SentimentResult, request: SentimentRequest) -> bool:
        path = _RESULTS / "lda_topics.csv"
        if not path.exists():
            return False
        try:
            df = pd.read_csv(path)
            # 兼容两种列名格式: topic/topic_id, text/keywords
            topic_col = "topic_id" if "topic_id" in df.columns else "topic"
            text_col = "keywords" if "keywords" in df.columns else "text"
            if topic_col not in df.columns:
                return False
            for _, row in df.head(request.top_n_themes).iterrows():
                keywords_str = str(row.get(text_col, ""))
                sample_phrases = [w.strip() for w in keywords_str.split()[:5]] if keywords_str else []
                result.top_themes.append(ThemeSummary(
                    theme=f"主题{row[topic_col]}",
                    count=1,
                    sample_phrases=sample_phrases,
                ))
            return True
        except Exception as e:
            logger.warning(f"[SentimentService] lda_result 加载失败: {e}")
            return False

    def _infer_sentiment_fallback(self, result: SentimentResult, request: SentimentRequest) -> bool:
        """无预计算结果时，用 TF-IDF + SVC 对原始评论推断"""
        try:
            import pickle
            svc_path   = _ARTIFACT / "svc_sentiment.pkl"
            tfidf_path = _ARTIFACT / "tfidf_sentiment.pkl"
            reviews_csv = _DATA_ROOT / "processed" / "reviews_cn.csv"
            if not (svc_path.exists() and tfidf_path.exists() and reviews_csv.exists()):
                return False
            svc   = pickle.load(open(svc_path,   "rb"))
            tfidf = pickle.load(open(tfidf_path, "rb"))
            df    = pd.read_csv(reviews_csv, nrows=request.nrows or 2000)
            if "review_text" not in df.columns:
                return False
            texts  = df["review_text"].fillna("").tolist()
            X      = tfidf.transform(texts)
            labels = svc.predict(X)
            total  = len(labels)
            result.total_reviews  = total
            result.positive_ratio = round(float((labels == 2).sum() / total), 4)
            result.neutral_ratio  = round(float((labels == 1).sum() / total), 4)
            result.negative_ratio = round(float((labels == 0).sum() / total), 4)
            result.degraded = True
            return True
        except Exception as e:
            logger.warning(f"[SentimentService] fallback 推断失败: {e}")
            return False


sentiment_intelligence_service = SentimentIntelligenceService()
