# -*- coding: utf-8 -*-
"""backend/services/sentiment_service.py — 舆情分析业务逻辑"""
import hashlib
import json
import math
from datetime import date, timedelta
from typing import Any, Optional

import pandas as pd
import redis.asyncio as aioredis
from sqlalchemy.orm import Session
from loguru import logger

from backend.config import settings
from backend.core.response import ok, cached, degraded
from backend.core.exceptions import AppError
from backend.agents.gateway import AgentGateway
from backend.repositories.analysis_results_repo import AnalysisResultsRepo
from backend.schemas.sentiment_schemas import SentimentAnalyzeRequest

_RESULTS = settings.MODELS_ROOT / "results" / "nlp"


class SentimentService:
    def __init__(self, db: Session, redis: aioredis.Redis, agent: Any = None):
        self.db    = db
        self.redis = redis
        self.agent = agent
        self._repo = AnalysisResultsRepo(db)

    # ── 缓存读写帮助方法 ──────────────────────────────────────

    async def _read_result(self, redis_key: str, db_module: str) -> Optional[dict]:
        """Redis 热缓存 → DB 持久化层 → None"""
        try:
            val = await self.redis.get(redis_key)
            if val:
                return json.loads(val)
        except Exception as e:
            logger.warning(f"[sentiment_svc] redis get {redis_key}: {e}")
        result = self._repo.get_latest(db_module)
        if result is not None:
            try:
                await self.redis.setex(redis_key, 3600, json.dumps(result, ensure_ascii=False))
            except Exception:
                pass
        return result

    async def _set_result(self, redis_key: str, db_module: str, data: dict) -> None:
        """CSV 命中后回写 Redis + DB"""
        self._repo.save(db_module, data)
        try:
            await self.redis.setex(redis_key, 3600, json.dumps(data, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"[sentiment_svc] redis setex {redis_key}: {e}")

    async def get_overview(self) -> dict:
        # 1. Redis → DB
        hit = await self._read_result("sentiment:overview", "sentiment_overview")
        if hit is not None:
            return ok(hit)

        # 2. CSV
        path = _RESULTS / "sentiment_tfidf_result.csv"
        if path.exists():
            try:
                df = pd.read_csv(path)
                n  = len(df)
                label_col = "label" if "label" in df.columns else df.columns[0]
                pred_col  = "pred"  if "pred"  in df.columns else label_col

                # ── 三类分布：label 与 pred 一致=高确信，不一致=中性 ──
                agree = df[label_col] == df[pred_col]
                n_pos = int(((df[pred_col] == 1) & agree).sum())
                n_neg = int(((df[pred_col] == 0) & agree).sum())
                n_neu = int((~agree).sum())
                pos_pct = round(n_pos / max(n, 1) * 100, 1)
                neg_pct = round(n_neg / max(n, 1) * 100, 1)
                neu_pct = round(100 - pos_pct - neg_pct, 1)

                # ── avg_score_7d（pred 列正面率作情感得分）──
                avg_score = round(float(df[pred_col].mean()), 4)

                # ── trend_30d（等分 30 段模拟日趋势）──
                today = date.today()
                n_bins = min(30, n)
                trend_30d = []
                if n_bins > 0:
                    bins = [df[pred_col].iloc[i * n // n_bins:(i + 1) * n // n_bins]
                            for i in range(n_bins)]
                    for i, b in enumerate(bins):
                        trend_30d.append({
                            "date":      str(today - timedelta(days=n_bins - 1 - i)),
                            "avg_score": round(float(b.mean()), 4),
                        })

                dist = {
                    "positive_pct": pos_pct,
                    "negative_pct": neg_pct,
                    "neutral_pct":  neu_pct,
                    "avg_score_7d": avg_score,
                    "trend_30d":    trend_30d,
                    "alert":        neg_pct > 40,
                }
                await self._set_result("sentiment:overview", "sentiment_overview", dist)
                return ok(dist)
            except Exception as e:
                logger.warning(f"[sentiment_svc] overview csv error: {e}")

        # 3. Mock
        if settings.ENABLE_MOCK_DATA:
            today = date.today()
            mock = {
                "positive_pct":  62.3,
                "negative_pct":  24.1,
                "neutral_pct":   13.6,
                "avg_score_7d":  0.61,
                "trend_30d": [
                    {
                        "date":      str(today - timedelta(days=29 - i)),
                        "avg_score": round(0.55 + (i % 7) * 0.01, 2),
                    }
                    for i in range(30)
                ],
                "alert": False,
            }
            return degraded(mock, "mock data")
        raise AppError(503, "舆情概览数据暂未就绪")

    async def get_topics(self) -> dict:
        # 1. Redis → DB
        hit = await self._read_result("sentiment:topics", "sentiment_topics")
        if hit is not None:
            return ok(hit)

        # 2. CSV
        path = _RESULTS / "lda_topics.csv"
        if path.exists():
            try:
                df   = pd.read_csv(path)
                # keywords: 空格分隔字符串 → 数组
                if "keywords" in df.columns:
                    df["keywords"] = df["keywords"].apply(
                        lambda v: v.split() if isinstance(v, str) else []
                    )
                # topic_id → id（前端期望 id 字段）
                if "topic_id" in df.columns and "id" not in df.columns:
                    df = df.rename(columns={"topic_id": "id"})
                # 自动生成 label + category（根据关键词情感倾向推断）
                _POS_HINTS = {"好", "不错", "推荐", "满意", "优质", "棒", "好吃", "新鲜", "赞"}
                _NEG_HINTS = {"差", "烂", "难吃", "垃圾", "差评", "不好", "退货", "投诉"}
                _LOG_HINTS = {"送", "快递", "物流", "外卖", "配送", "送餐", "送到", "时间"}

                def _infer_label_cat(kws):
                    kw_set = set(kws) if isinstance(kws, list) else set()
                    if kw_set & _LOG_HINTS:
                        return "物流服务", "中性"
                    if kw_set & _NEG_HINTS:
                        return "负面反馈", "负面"
                    if kw_set & _POS_HINTS:
                        return "正面评价", "正面"
                    return "综合话题", "中性"

                if "label" not in df.columns:
                    df[["label", "category"]] = df["keywords"].apply(
                        lambda kws: pd.Series(_infer_label_cat(kws))
                    )
                elif "category" not in df.columns:
                    df["category"] = df["label"].map({
                        "正面评价": "正面", "负面反馈": "负面",
                        "物流服务": "中性", "综合话题": "中性",
                    }).fillna("中性")

                data = df.where(df.notna(), None).to_dict("records")

                # ── 去重：同一关键词只出现在一张卡片 ──
                # 中性/模糊词应归入综合话题，不留在正面/负面卡片
                _NEUTRAL_WORDS = {"一般", "有点", "特别", "可以", "非常",
                                  "什么", "不是", "不要", "一点", "怎么",
                                  "还行", "普通", "中等", "凑合", "马马虎虎",
                                  "还可以", "一般般", "尚可", "正常", "soso"}
                moved_neutral = []
                for d in data:
                    if d.get("label") == "综合话题":
                        continue
                    orig_kws = d.get("keywords", [])
                    keep, move = [], []
                    for kw in orig_kws:
                        if kw in _NEUTRAL_WORDS:
                            move.append(kw)
                        else:
                            keep.append(kw)
                    d["keywords"] = keep
                    moved_neutral.extend(move)

                # 收集所有已使用关键词
                used = set()
                for d in data:
                    used.update(d.get("keywords", []))

                # 构建综合话题：移入的中性词 + 补充词（去除已占用的）
                _EXTRA_NEUTRAL = ["还行", "普通", "中等", "凑合", "马马虎虎",
                                  "还可以", "一般般", "尚可", "正常", "soso"]
                neutral_pool = list(dict.fromkeys(moved_neutral + _EXTRA_NEUTRAL))
                neutral_kws = [kw for kw in neutral_pool if kw not in used]

                existing_labels = {d.get("label") for d in data}
                if "综合话题" not in existing_labels:
                    next_id = max((d.get("id", 0) for d in data), default=-1) + 1
                    data.append({
                        "id": next_id, "label": "综合话题", "category": "中性",
                        "keywords": neutral_kws[:10],
                    })
                else:
                    for d in data:
                        if d.get("label") == "综合话题":
                            d["keywords"] = neutral_kws[:10]
                wrapped = {"topics": data}
                await self._set_result("sentiment:topics", "sentiment_topics", wrapped)
                return ok(wrapped)
            except Exception as e:
                logger.warning(f"[sentiment_svc] topics csv error: {e}")

        # 3. Mock
        if settings.ENABLE_MOCK_DATA:
            mock = {
                "k": 4, "coherence": 0.531,
                "topics": [
                    {"id": 0, "label": "正面评价", "category": "正面",
                     "keywords": ["新鲜", "好吃", "推荐", "包装精美", "性价比高"]},
                    {"id": 1, "label": "负面反馈", "category": "负面",
                     "keywords": ["快递", "破损", "客服", "退款慢", "质量差"]},
                    {"id": 2, "label": "物流服务", "category": "中性",
                     "keywords": ["发货快", "隔日达", "冷链", "保温", "包装好"]},
                    {"id": 3, "label": "综合话题", "category": "中性",
                     "keywords": ["一般", "还行", "普通", "中等", "凑合",
                                  "马马虎虎", "还可以", "尚可", "正常", "soso"]},
                ],
            }
            return degraded(mock, "mock data")
        raise AppError(503, "LDA 话题数据暂未就绪")

    async def analyze(self, body: SentimentAnalyzeRequest) -> dict:
        """Confidence-Gated Hybrid Cascade 推断"""
        cache_key = f"sentiment:analyze:{hashlib.md5(body.text.encode()).hexdigest()}"
        try:
            cached_val = await self.redis.get(cache_key)
            if cached_val:
                return cached(json.loads(cached_val))
        except Exception as e:
            logger.warning(f"[sentiment_svc] redis get failed: {e}")

        from backend.services.sentiment_llm_service import cascade_analyze

        # ── Step 1: 获取 BERT / TF-IDF 本地推断结果 ──
        bert_result = None
        if self.agent is not None:
            try:
                bert_result = self.agent.analyze(body.text)
            except Exception as e:
                logger.warning(f"[sentiment_svc] agent.analyze() failed: {e}")

        # ── Step 2: Cascade 推断 ──
        try:
            cascade_result = await cascade_analyze(body.text, bert_result)
        except Exception as e:
            logger.warning(f"[sentiment_svc] cascade_analyze failed: {e}")
            cascade_result = None

        # ── Step 3: 如果 Cascade 失败 → 使用本地结果或关键词降级 ──
        if cascade_result is not None:
            label_str = cascade_result["label"]
            _TOPIC_MAP = {"负面": ["负面反馈"], "正面": ["正面评价"], "中性": ["综合话题"]}
            result = {
                "text":           body.text,
                "label":          label_str,
                "confidence":     cascade_result["confidence"],
                "model_used":     cascade_result.get("model_used", "cascade"),
                "topics":         _TOPIC_MAP.get(label_str, []),
                "reflect_passed": True,
                "reasoning":      cascade_result.get("reasoning"),
                "key_phrases":    cascade_result.get("key_phrases"),
                "aspects":        cascade_result.get("aspects"),
                "entity_sentiments": cascade_result.get("entity_sentiments"),
                "intent_tags":    cascade_result.get("intent_tags"),
                "agent_signals":  cascade_result.get("agent_signals"),
                "cascade_tier":   cascade_result.get("cascade_tier"),
                "cascade_trace":  cascade_result.get("cascade_trace"),
                "needs_review":   cascade_result.get("needs_review"),
            }

            # ── HITL: 自动入队 ──
            if cascade_result.get("needs_review"):
                await self._enqueue_review(body.text, result)
        elif bert_result and isinstance(bert_result, dict) and "label" in bert_result:
            label_str = bert_result["label"]
            _TOPIC_MAP = {"负面": ["负面反馈"], "正面": ["正面评价"], "中性": ["综合话题"]}
            result = {
                "text":           body.text,
                "label":          label_str,
                "confidence":     bert_result.get("confidence", 0.6),
                "model_used":     bert_result.get("model", "local-fallback"),
                "topics":         _TOPIC_MAP.get(label_str, []),
                "reflect_passed": True,
            }
        else:
            result = self._keyword_fallback(body.text)

        # ★ 知识库写入 + 跨 Agent 信号分发（先于缓存，确保 kb_id 入缓存）
        if settings.SENTIMENT_KB_ENABLED and cascade_result is not None:
            await self._ingest_and_dispatch(cache_key, body.text, result)

        try:
            await self.redis.setex(cache_key, 7200, json.dumps(result, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"[sentiment_svc] redis setex failed: {e}")

        return ok(result)

    # ── HITL 审核队列（基于 Redis，轻量级） ───────────────────

    async def _enqueue_review(self, text: str, result: dict) -> None:
        """将 uncertain 结果推入 Redis 审核队列"""
        import uuid
        from datetime import datetime
        review_id = str(uuid.uuid4())[:8]
        item = {
            "id": review_id,
            "text": text,
            "auto_label": result.get("label", "中性"),
            "confidence": result.get("confidence", 0),
            "model_used": result.get("model_used", ""),
            "created_at": datetime.now().isoformat(),
            "status": "pending",
        }
        try:
            await self.redis.lpush("sentiment:review_queue", json.dumps(item, ensure_ascii=False))
            await self.redis.ltrim("sentiment:review_queue", 0, 199)
            logger.info(f"[sentiment_svc] HITL enqueued: {review_id}")
        except Exception as e:
            logger.warning(f"[sentiment_svc] HITL enqueue failed: {e}")

    async def get_review_queue(self) -> dict:
        """获取待审核队列"""
        try:
            raw_list = await self.redis.lrange("sentiment:review_queue", 0, 49)
            items = []
            for raw in raw_list:
                item = json.loads(raw)
                if item.get("status") == "pending":
                    items.append(item)
            return ok({"items": items, "total": len(items)})
        except Exception as e:
            logger.warning(f"[sentiment_svc] get review queue failed: {e}")
            return ok({"items": [], "total": 0})

    async def resolve_review(self, review_id: str, human_label: str) -> dict:
        """人工审核裁决：更新队列中对应项状态"""
        try:
            raw_list = await self.redis.lrange("sentiment:review_queue", 0, 199)
            new_list = []
            resolved = False
            for raw in raw_list:
                item = json.loads(raw)
                if item.get("id") == review_id and item.get("status") == "pending":
                    item["status"] = "resolved"
                    item["human_label"] = human_label
                    resolved = True
                    # 更新对应的分析缓存
                    text_hash = hashlib.md5(item["text"].encode()).hexdigest()
                    cache_key = f"sentiment:analyze:{text_hash}"
                    try:
                        cached_val = await self.redis.get(cache_key)
                        if cached_val:
                            cached_result = json.loads(cached_val)
                            cached_result["label"] = human_label
                            cached_result["confidence"] = 1.0
                            cached_result["model_used"] = "human-review"
                            cached_result["needs_review"] = False
                            await self.redis.setex(cache_key, 7200, json.dumps(cached_result, ensure_ascii=False))
                    except Exception:
                        pass
                new_list.append(json.dumps(item, ensure_ascii=False))

            if resolved:
                pipe = self.redis.pipeline()
                await pipe.delete("sentiment:review_queue")
                for item_str in new_list:
                    await pipe.rpush("sentiment:review_queue", item_str)
                await pipe.execute()
                logger.info(f"[sentiment_svc] HITL resolved: {review_id} → {human_label}")

            return ok({"resolved": resolved, "review_id": review_id, "human_label": human_label})
        except Exception as e:
            logger.warning(f"[sentiment_svc] resolve review failed: {e}")
            return ok({"resolved": False, "error": str(e)})

    async def _ingest_and_dispatch(self, review_id: str, text: str, result: dict) -> None:
        """知识库写入 + 跨 Agent 信号分发 + 实体负面计数。非阻塞，异常不影响主流程。"""
        try:
            from backend.services.sentiment_kb_service import SentimentKBService
            kb_svc = SentimentKBService.get_instance()
            kb_id = await kb_svc.ingest(review_id, text, result)
            result["kb_id"] = kb_id
        except Exception as e:
            logger.warning(f"[sentiment_svc] KB ingest failed: {e}")

        # Redis Pub/Sub 分发高优信号
        signals = result.get("agent_signals") or []
        for sig in signals:
            if isinstance(sig, dict) and sig.get("severity") in ("medium", "high"):
                try:
                    channel = f"sentiment:signal:{sig.get('target_agent', 'unknown')}"
                    await self.redis.publish(
                        channel, json.dumps(sig, ensure_ascii=False)
                    )
                    logger.debug(f"[sentiment_svc] published signal to {channel}")
                except Exception as e:
                    logger.warning(f"[sentiment_svc] publish signal failed: {e}")

        # 实体级负面累积计数（7 天滑动窗口）
        for es in (result.get("entity_sentiments") or []):
            if isinstance(es, dict) and es.get("sentiment") == "负面":
                entity_name = es.get("entity", "")
                if entity_name:
                    try:
                        counter_key = f"sentiment:neg_count:{entity_name}:7d"
                        await self.redis.incr(counter_key)
                        await self.redis.expire(counter_key, 7 * 86400)
                    except Exception:
                        pass

    @staticmethod
    def _keyword_fallback(text: str) -> dict:
        """关键词规则降级，处理否定词翻转"""
        _NEGATIONS = ("不", "没", "无", "非", "别", "莫", "未", "甭")
        _NEUTRAL_KW = {"一般", "还行", "马马虎虎", "凑合", "普通",
                       "还可以", "一般般", "中等", "尚可", "soso"}
        neg_kw = ["差", "烂", "退货", "投诉", "不满", "失望", "假货",
                  "难吃", "难喝", "垃圾", "恶心", "糟糕", "坑"]
        pos_kw = ["好", "棒", "满意", "推荐", "优质", "快速", "完美",
                  "好吃", "好喝", "新鲜", "不错", "赞", "喜欢"]

        # 先检查中性关键词
        if any(nk in text for nk in _NEUTRAL_KW):
            return {
                "text": text, "label": "中性", "confidence": 0.70,
                "model_used": "keyword-rules", "topics": ["综合话题"],
                "reflect_passed": True,
            }

        neg, pos = 0, 0
        for kw in neg_kw:
            if kw in text:
                neg += 1
        for kw in pos_kw:
            idx = text.find(kw)
            while idx != -1:
                if idx > 0 and text[idx - 1] in _NEGATIONS:
                    neg += 1
                else:
                    pos += 1
                idx = text.find(kw, idx + len(kw))

        if neg > pos:
            label_str = "负面"
            conf = round(min(0.65 + neg * 0.05, 0.90), 3)
            topics = ["负面反馈"]
        elif pos > neg:
            label_str = "正面"
            conf = round(min(0.65 + pos * 0.05, 0.90), 3)
            topics = ["正面评价"]
        else:
            label_str, conf, topics = "中性", 0.55, ["综合话题"]
        return {
            "text":           text,
            "label":          label_str,
            "confidence":     conf,
            "model_used":     "keyword-rules",
            "topics":         topics,
            "reflect_passed": True,
        }
