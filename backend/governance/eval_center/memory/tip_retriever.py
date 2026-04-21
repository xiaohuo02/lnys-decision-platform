# -*- coding: utf-8 -*-
"""backend/governance/eval_center/memory/tip_retriever.py — Phase 3: 运行时检索 + 注入

两种检索策略：
  1. Cosine Similarity（快，推荐）: 零 LLM 调用
  2. LLM-Guided Selection（更准，贵）: 额外 1 次 LLM 调用

检索后将 Tips 注入 prompt 的 [Guidelines] 段。
"""
from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a < 1e-9 or norm_b < 1e-9:
        return 0.0
    return dot / (norm_a * norm_b)


class TipRetriever:
    """运行时 Tip 检索器

    Parameters:
        db:           DB session
        threshold:    cosine similarity 阈值（默认 0.6）
        top_k:        最多返回 Tips 数量（默认 5）
        use_llm:      是否使用 LLM 引导选择（默认 False，用 cosine）
    """

    def __init__(
        self,
        db=None,
        threshold: float = 0.6,
        top_k: int = 5,
        use_llm: bool = False,
    ):
        self.db = db
        self.threshold = threshold
        self.top_k = top_k
        self.use_llm = use_llm

    async def retrieve(
        self,
        task_description: str,
        task_type: Optional[str] = None,
        db=None,
    ) -> List[Dict[str, Any]]:
        """检索与当前任务相关的 Tips

        Args:
            task_description: 当前任务描述（用户问题）
            task_type:        任务类型过滤

        Returns:
            相关 Tips 列表（按相关度排序）
        """
        session = db or self.db

        if self.use_llm:
            return await self._llm_guided_retrieve(task_description, task_type, session)
        else:
            return await self._cosine_retrieve(task_description, task_type, session)

    async def _cosine_retrieve(
        self,
        task_description: str,
        task_type: Optional[str],
        db,
    ) -> List[Dict[str, Any]]:
        """Cosine similarity 快速检索"""
        import sqlalchemy

        all_tips = await self._fetch_active_tips(db, task_type=task_type, limit=200)

        if not all_tips:
            return []

        try:
            model = self._get_embedding_model()
            if model is None:
                return self._keyword_fallback(task_description, all_tips)

            # 编码任务描述
            query_emb = model.encode([task_description], normalize_embeddings=True)[0].tolist()

            # 编码所有 tips 的 content
            tip_texts = [t.get("content", "") for t in all_tips]
            tip_embs = model.encode(tip_texts, normalize_embeddings=True)

            # 计算相似度并排序
            scored: List[Tuple[float, Dict]] = []
            for i, tip in enumerate(all_tips):
                sim = _cosine_similarity(query_emb, tip_embs[i].tolist())
                if sim >= self.threshold:
                    tip["relevance_score"] = round(sim, 4)
                    scored.append((sim, tip))

            scored.sort(key=lambda x: x[0], reverse=True)
            results = [t for _, t in scored[:self.top_k]]

            logger.debug(f"[TipRetriever] cosine: {len(results)}/{len(all_tips)} tips matched")
            return results

        except Exception as exc:
            logger.warning(f"[TipRetriever] cosine 检索失败: {exc}, 降级到关键词匹配")
            return self._keyword_fallback(task_description, all_tips)

    async def _llm_guided_retrieve(
        self,
        task_description: str,
        task_type: Optional[str],
        db,
    ) -> List[Dict[str, Any]]:
        """LLM 引导选择（更精准但需额外 LLM 调用）"""
        from openai import AsyncOpenAI
        from backend.config import settings

        all_tips = await self._fetch_active_tips(db, task_type=task_type, limit=50)

        if not all_tips:
            return []

        tips_text = "\n".join([
            f"[{i}] ({t['tip_type']}) {t['content']}"
            for i, t in enumerate(all_tips)
        ])

        prompt = f"""从以下 Tips 中选择与当前任务最相关的（最多 {self.top_k} 条）。

## 当前任务
{task_description}

## 可用 Tips
{tips_text}

## 输出格式（JSON 数组，只包含序号）
[0, 3, 7]"""

        try:
            client = AsyncOpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL)
            response = await client.chat.completions.create(
                model=settings.LLM_MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=256,
            )
            content = response.choices[0].message.content or "[]"
            import re
            match = re.search(r'\[[\d,\s]*\]', content)
            if match:
                indices = json.loads(match.group(0))
                results = [all_tips[i] for i in indices if 0 <= i < len(all_tips)]
                return results[:self.top_k]
        except Exception as exc:
            logger.warning(f"[TipRetriever] LLM 引导检索失败: {exc}")

        return self._keyword_fallback(task_description, all_tips)

    @staticmethod
    async def _fetch_active_tips(db, task_type: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        """异步查询活跃 Tips（兼容 AsyncSession）"""
        import sqlalchemy

        if db is None:
            return []
        conditions = ["is_active = 1"]
        params: Dict[str, Any] = {"limit": limit}
        if task_type:
            conditions.append("source_task_type = :task_type")
            params["task_type"] = task_type
        where = " AND ".join(conditions)
        result = await db.execute(sqlalchemy.text(
            f"SELECT * FROM eval_agent_tips WHERE {where} "
            f"ORDER BY confidence DESC, reference_count DESC LIMIT :limit"
        ), params)
        return [dict(r._mapping) for r in result.fetchall()]

    @staticmethod
    def _keyword_fallback(query: str, tips: List[Dict]) -> List[Dict]:
        """关键词匹配降级方案"""
        query_lower = query.lower()
        scored = []
        for tip in tips:
            content = (tip.get("content", "") + " " + tip.get("trigger_desc", "")).lower()
            overlap = sum(1 for word in query_lower.split() if word in content)
            if overlap > 0:
                tip["relevance_score"] = round(overlap / max(len(query_lower.split()), 1), 4)
                scored.append((overlap, tip))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [t for _, t in scored[:5]]

    @staticmethod
    def _get_embedding_model():
        """懒加载 embedding 模型（复用 embedding_grader 的模型）"""
        try:
            from backend.governance.eval_center.graders.embedding_grader import _get_embedding_model
            model, _ = _get_embedding_model()
            return model
        except Exception:
            return None

    @staticmethod
    def inject_tips(base_prompt: str, tips: List[Dict[str, Any]]) -> str:
        """将检索到的 Tips 注入 prompt

        Args:
            base_prompt: 原始 prompt
            tips:        检索到的 Tips

        Returns:
            注入 Tips 后的 prompt
        """
        if not tips:
            return base_prompt

        guidelines = []
        for t in tips:
            tip_type = t.get("tip_type", "strategy")
            content = t.get("content", "")
            prefix = {"strategy": "✓ 策略", "recovery": "⚡ 恢复", "optimization": "⚙ 优化"}.get(tip_type, "💡")
            guidelines.append(f"- [{prefix}] {content}")

        tips_section = "\n".join(guidelines)
        return f"{base_prompt}\n\n【历史经验指南 — 基于过往执行轨迹自动提取】\n{tips_section}"
