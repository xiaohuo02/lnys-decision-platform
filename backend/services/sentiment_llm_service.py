# -*- coding: utf-8 -*-
"""backend/services/sentiment_llm_service.py — LLM Cascade 舆情分析服务

Confidence-Gated Hybrid Cascade:
  Tier 1: BERT-Chinese 本地推断 (~5ms, 免费)
  Tier 2: LLM CoT 单次推理 (qwen3.5-plus-2026-02-15, ~1s)
  Tier 3: LLM Self-Consistency 三路投票 (qwen3.5-plus-2026-02-15 × 3)
  Tier 4: 标记 uncertain → HITL 人工审核
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List, Optional

from loguru import logger

_LLM_CLIENT = None  # lazy singleton


def _get_llm(temperature: float = 0.3):
    """延迟初始化 LLM 客户端（项目标准模式：langchain_openai.ChatOpenAI）"""
    global _LLM_CLIENT
    if _LLM_CLIENT is None:
        try:
            from langchain_openai import ChatOpenAI
            from backend.config import settings

            extra_kw = {}
            if "qwen" in settings.LLM_MODEL_NAME.lower():
                extra_kw["model_kwargs"] = {"extra_body": {"enable_thinking": True}}
            _LLM_CLIENT = ChatOpenAI(
                api_key=settings.LLM_API_KEY,
                base_url=settings.LLM_BASE_URL,
                model=settings.LLM_MODEL_NAME,
                temperature=temperature,
                max_tokens=2048,
                timeout=45,
                **extra_kw,
            )
        except Exception as e:
            logger.warning(f"[SentimentLLM] LLM 初始化失败: {e}")
    return _LLM_CLIENT


# ── System Prompt ────────────────────────────────────────────────

_SYSTEM_PROMPT = """你是一位专业的中文舆情分析师。你的任务是对用户提供的文本进行深度情感分析和实体级观点挖掘。

分析步骤：
1. 关键词识别：识别文本中的情感关键词和短语
2. 否定词分析：注意"不""没""无"等否定词对情感极性的翻转
3. 隐式情感：理解言外之意和暗示性表达（如"等了三天才发货"暗示不满）
4. 综合判定：给出整体情感结论
5. 实体方面提取（ASTE）：识别文本中提及的每一个实体（产品名/服务/品牌等），提取其对应的方面、观点表达和情感极性。不限数量，有多少提取多少。
6. 跨智能体信号：根据分析结果，判断是否需要通知其他业务智能体采取行动。

你必须严格按以下 JSON 格式输出，不要输出其他内容：
{
  "label": "正面" 或 "负面" 或 "中性",
  "confidence": 0.0到1.0之间的浮点数,
  "reasoning": [
    {"step": "关键词识别", "detail": "..."},
    {"step": "否定词分析", "detail": "..."},
    {"step": "隐式情感", "detail": "..."},
    {"step": "综合判定", "detail": "..."}
  ],
  "key_phrases": ["短语1", "短语2"],
  "entity_sentiments": [
    {"entity": "产品/服务名", "aspect": "方面", "opinion": "原文观点表达", "sentiment": "正面/负面/中性"}
  ],
  "intent_tags": ["quality_complaint", "repurchase_likely"],
  "agent_signals": [
    {"target_agent": "inventory/customer/association/operation", "signal_type": "quality_alert/churn_risk/co_mention", "entity": "相关实体", "severity": "low/medium/high", "suggestion": "建议描述"}
  ]
}

intent_tags 从以下枚举中选择（可多选，只要文本中存在对应语义就必须标注）：
- quality_complaint: 质量投诉（如"味道变了""不新鲜""有异味""缩水""发霉"）
- defect_report: 缺陷/损坏反馈（如"包装破损""瓶盖松动""漏液""碎了"）
- repurchase_likely: 复购意愿强（如"下次还买""回购""囤货""推荐给朋友"）
- repurchase_unlikely: 复购意愿弱（如"再也不买""不会回购""最后一次"）
- cross_product_compare: 多产品比较或竞品对比（如"比XX便宜""隔壁店才XX元""三只松鼠""A比B好"）
- service_praise: 服务好评（如"客服态度好""换货及时""处理很快""服务周到"）
- service_complaint: 服务投诉（如"客服态度差""不给退款""催了好几次"）
- price_sensitive: 价格敏感（如"价格偏高""太贵""性价比一般""便宜了一半""满减""打折""团购价""价格合理"）
- logistics_praise: 物流好评（如"第二天就到""冷链保鲜好""顺丰快"）
- logistics_complaint: 物流投诉（如"物流慢""配送慢""等了一周"）

重要：如果文本中有任何涉及价格、折扣、性价比、促销的描述，必须标注 price_sensitive。
重要：如果文本中对比了不同产品、品牌、店铺，必须标注 cross_product_compare。
重要：如果文本中有对客服/售后的正面评价，必须标注 service_praise。

agent_signals 只在有明确业务价值时输出，无则留空数组。
- target_agent 可选: inventory(库存优化), customer(客户分析), association(关联分析), operation(经营分析)
- severity: low(仅记录), medium(建议关注), high(需立即处理)

entity_sentiments 规则：
1. 必须覆盖文本中提及的所有实体，不要遗漏。
2. 实体包括：具体产品名（如"黄岩蜜橘""福鼎白茶"）、产品品类（如"柑橘系列""茶叶""水产""零食"）、服务环节（如"客服""物流""包装"）。
3. 当文本用品类概称（如"你家茶叶""水产品""零食"）而非具体名称时，以品类作为实体名。
4. sentiment 字段必须严格为"正面""负面""中性"三选一，不允许附加任何注释或括号。
5. 同一实体多个方面应分行输出。"""

_USER_TEMPLATE = """请分析以下文本的情感倾向：

文本：{text}
{hint_section}
请严格按 JSON 格式输出分析结果。"""

_USER_TEMPLATE_WITH_HINT = """BERT 模型预判结果：{bert_label}（置信度 {bert_conf:.1%}）
请结合你自己的判断，BERT 结果仅供参考，可能有误。"""


# ── 核心 Cascade 逻辑 ───────────────────────────────────────────

async def llm_analyze_single(
    text: str,
    bert_label: Optional[str] = None,
    bert_conf: Optional[float] = None,
    temperature: float = 0.3,
) -> Optional[Dict[str, Any]]:
    """单次 LLM CoT 推断"""
    from langchain_core.messages import SystemMessage, HumanMessage

    llm = _get_llm()
    if llm is None:
        return None

    hint = ""
    if bert_label and bert_conf is not None:
        hint = _USER_TEMPLATE_WITH_HINT.format(
            bert_label=bert_label, bert_conf=bert_conf,
        )

    user_msg = _USER_TEMPLATE.format(text=text, hint_section=hint)

    _MAX_RETRIES = 2
    raw = None
    for _attempt in range(_MAX_RETRIES):
      try:
        # 临时覆盖 temperature
        llm_instance = llm.bind(temperature=temperature)
        response = await llm_instance.ainvoke([
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=user_msg),
        ])

        raw = response.content.strip()
        break  # 成功则跳出重试
      except Exception as _retry_err:
        if _attempt < _MAX_RETRIES - 1:
            logger.info(f"[SentimentLLM] attempt {_attempt+1} failed: {_retry_err}, retrying...")
            await asyncio.sleep(1)
        else:
            logger.warning(f"[SentimentLLM] all {_MAX_RETRIES} attempts failed: {_retry_err}")
            return None

    if not raw:
        return None

    try:
        # 提取 JSON 块
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        parsed = json.loads(raw)

        # 校验必要字段
        if parsed.get("label") not in ("正面", "负面", "中性"):
            logger.warning(f"[SentimentLLM] invalid label: {parsed.get('label')}")
            return None

        conf = parsed.get("confidence", 0.8)
        if not (0 <= conf <= 1):
            conf = 0.8

        # 清洗 entity_sentiments — LLM 可能输出带注释的 sentiment 如 "负面（xxx）"
        _VALID_SENT = {"正面", "负面", "中性"}
        entity_sents = []
        _seen_pairs = set()
        for es in parsed.get("entity_sentiments", []):
            if not isinstance(es, dict):
                continue
            raw_sent = es.get("sentiment", "中性")
            # 提取前两个字符即可匹配 正面/负面/中性
            clean_sent = raw_sent[:2] if raw_sent[:2] in _VALID_SENT else "中性"
            es["sentiment"] = clean_sent
            # 按 (entity, aspect) 去重，防止 LLM 输出重复实体
            dedup_key = (es.get("entity", ""), es.get("aspect", ""))
            if dedup_key in _seen_pairs:
                continue
            _seen_pairs.add(dedup_key)
            entity_sents.append(es)

        # 从 entity_sentiments 聚合生成向后兼容的 aspects
        aspects = parsed.get("aspects", {})
        if entity_sents and not aspects:
            _ASPECT_MAP = {"口味": "质量", "品质": "质量", "味道": "质量", "新鲜": "质量",
                           "速度": "物流", "配送": "物流", "快递": "物流", "发货": "物流",
                           "客服": "服务", "售后": "服务", "态度": "服务",
                           "价格": "价格", "性价比": "价格", "价位": "价格"}
            aspects = {"质量": "无关", "物流": "无关", "服务": "无关", "价格": "无关"}
            for es in entity_sents:
                mapped = _ASPECT_MAP.get(es.get("aspect", ""), "")
                if mapped and aspects.get(mapped) == "无关":
                    aspects[mapped] = es.get("sentiment", "中性")

        return {
            "label": parsed["label"],
            "confidence": round(conf, 3),
            "reasoning": parsed.get("reasoning", []),
            "key_phrases": parsed.get("key_phrases", []),
            "aspects": aspects,
            "entity_sentiments": entity_sents,
            "intent_tags": parsed.get("intent_tags", []),
            "agent_signals": parsed.get("agent_signals", []),
        }
    except json.JSONDecodeError as e:
        logger.warning(f"[SentimentLLM] JSON parse error: {e}, raw: {raw[:200] if raw else 'empty'}")
        return None
    except Exception as e:
        logger.warning(f"[SentimentLLM] call failed: {e}")
        return None


async def llm_self_consistency(
    text: str,
    bert_label: Optional[str] = None,
    bert_conf: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """三路并行 LLM 调用 + 多数投票"""
    temps = [0.2, 0.5, 0.8]
    tasks = [
        llm_analyze_single(text, bert_label, bert_conf, t)
        for t in temps
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    valid = [r for r in results if isinstance(r, dict) and r.get("label")]

    if len(valid) < 2:
        return None

    # 多数投票
    from collections import Counter
    labels = [r["label"] for r in valid]
    counter = Counter(labels)
    winner, count = counter.most_common(1)[0]

    if count < 2:
        # 无多数一致
        return None

    # 取票数最多标签中置信度最高的结果
    best = max((r for r in valid if r["label"] == winner),
               key=lambda r: r["confidence"])

    best["model_used"] = "llm-self-consistency"
    best["vote_detail"] = {l: c for l, c in counter.items()}
    return best


async def cascade_analyze(
    text: str,
    bert_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    完整 Cascade 推断流水线。

    返回 dict 包含:
      label, confidence, model_used, reasoning, key_phrases, aspects,
      entity_sentiments, intent_tags, agent_signals,
      cascade_tier (1-4), cascade_trace (每层决策记录)
    """
    t0 = time.time()
    trace: List[Dict[str, Any]] = []

    bert_label = bert_result.get("label") if bert_result else None
    bert_conf = bert_result.get("confidence", 0) if bert_result else 0
    bert_score = bert_result.get("score", 0) if bert_result else 0

    # ── Tier 1: BERT 高置信直出 ──
    # 仅对极短文本 (<20字且无逗号/句号) 真正跳过 LLM；
    # 复杂文本即使 BERT 高置信，仍调 LLM 做 ASTE 实体抽取，但保留 BERT 标签。
    _is_simple = len(text) < 20 and not any(c in text for c in "，。；！、")
    if bert_result and bert_conf >= 0.92 and _is_simple:
        trace.append({
            "tier": 1, "model": "bert-chinese", "decision": "direct_return",
            "label": bert_label, "confidence": bert_conf, "ms": round((time.time() - t0) * 1000),
        })
        return {
            "label": bert_label,
            "confidence": bert_conf,
            "model_used": "bert-chinese",
            "reasoning": [{"step": "BERT 高置信直出", "detail": f"score={bert_score}, conf={bert_conf:.3f}"}],
            "key_phrases": [],
            "aspects": {},
            "entity_sentiments": [],
            "intent_tags": [],
            "agent_signals": [],
            "cascade_tier": 1,
            "cascade_trace": trace,
        }

    trace.append({
        "tier": 1, "model": "bert-chinese",
        "decision": "defer_to_llm" if bert_result else "not_available",
        "label": bert_label, "confidence": bert_conf,
        "ms": round((time.time() - t0) * 1000),
    })

    # ── Tier 2: LLM CoT 单次推理 ──
    t1 = time.time()
    llm_result = await llm_analyze_single(text, bert_label, bert_conf)

    if llm_result:
        llm_label = llm_result["label"]
        llm_conf = llm_result["confidence"]

        # BERT 与 LLM 一致 → 直接返回
        if bert_label and llm_label == bert_label:
            trace.append({
                "tier": 2, "model": "llm-cot", "decision": "agree_with_bert",
                "label": llm_label, "confidence": llm_conf,
                "ms": round((time.time() - t1) * 1000),
            })
            # 一致时取两者置信度均值提升可信度
            merged_conf = round(min((bert_conf + llm_conf) / 2 + 0.05, 0.99), 3)
            llm_result["confidence"] = merged_conf
            llm_result["model_used"] = "bert+llm-cot"
            llm_result["cascade_tier"] = 2
            llm_result["cascade_trace"] = trace
            return llm_result

        # BERT 与 LLM 不一致 → 检查 LLM 置信度
        if llm_conf >= 0.80:
            trace.append({
                "tier": 2, "model": "llm-cot", "decision": "override_bert",
                "label": llm_label, "confidence": llm_conf,
                "ms": round((time.time() - t1) * 1000),
            })
            llm_result["model_used"] = "llm-cot"
            llm_result["cascade_tier"] = 2
            llm_result["cascade_trace"] = trace
            return llm_result

        trace.append({
            "tier": 2, "model": "llm-cot", "decision": "low_conf_defer",
            "label": llm_label, "confidence": llm_conf,
            "ms": round((time.time() - t1) * 1000),
        })
    else:
        trace.append({
            "tier": 2, "model": "llm-cot", "decision": "failed",
            "ms": round((time.time() - t1) * 1000),
        })

    # ── Tier 3: Self-Consistency 三路投票 ──
    t2 = time.time()
    sc_result = await llm_self_consistency(text, bert_label, bert_conf)

    if sc_result:
        trace.append({
            "tier": 3, "model": "llm-self-consistency", "decision": "majority_vote",
            "label": sc_result["label"], "confidence": sc_result["confidence"],
            "vote_detail": sc_result.get("vote_detail", {}),
            "ms": round((time.time() - t2) * 1000),
        })
        sc_result["cascade_tier"] = 3
        sc_result["cascade_trace"] = trace
        return sc_result

    trace.append({
        "tier": 3, "model": "llm-self-consistency", "decision": "no_majority",
        "ms": round((time.time() - t2) * 1000),
    })

    # ── Tier 4: 标记 uncertain (HITL) ──
    # 使用 LLM 单次结果（如果有）或 BERT 结果作为初步标签
    fallback_result = llm_result or (bert_result if bert_result else None)
    fallback_label = fallback_result["label"] if fallback_result else "中性"
    fallback_conf = fallback_result.get("confidence", 0.5) if fallback_result else 0.5

    trace.append({
        "tier": 4, "model": "hitl", "decision": "mark_uncertain",
        "ms": round((time.time() - t0) * 1000),
    })

    return {
        "label": fallback_label,
        "confidence": fallback_conf,
        "model_used": "uncertain-hitl",
        "reasoning": (fallback_result or {}).get("reasoning", [
            {"step": "不确定标记", "detail": "多模型无法达成一致，标记为需人工审核"}
        ]),
        "key_phrases": (fallback_result or {}).get("key_phrases", []),
        "aspects": (fallback_result or {}).get("aspects", {}),
        "entity_sentiments": (fallback_result or {}).get("entity_sentiments", []),
        "intent_tags": (fallback_result or {}).get("intent_tags", []),
        "agent_signals": (fallback_result or {}).get("agent_signals", []),
        "cascade_tier": 4,
        "cascade_trace": trace,
        "needs_review": True,
    }
