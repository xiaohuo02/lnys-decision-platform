# -*- coding: utf-8 -*-
"""backend/governance/eval_center/memory/tip_manager.py — Phase 2: Tips 管理

负责 Tips 的持久化、泛化、聚类、合并：
  1. 入库：将提取的 Tips 写入 eval_agent_tips
  2. 泛化：抽象实体、归一化动作
  3. 聚类：cosine similarity 分组
  4. 合并：LLM 合并重复 Tips
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

import sqlalchemy
from loguru import logger


GENERALIZE_PROMPT = """将以下 Tip 描述泛化，使其适用于更广泛的场景：
1. 将具体实体名替换为通用占位符（如 "张三" → "客户"）
2. 归一化动作动词（如 "获取/拿到/检索" → "查询"）
3. 去掉时间、ID 等上下文限定词

原始 Tip: {content}
触发条件: {trigger}

输出格式（JSON）：
{{"generalized_content": "...", "generalized_trigger": "..."}}"""


class TipManager:
    """Tips 持久化与管理"""

    def __init__(self, db=None):
        self.db = db

    def save_tips(self, tips: List[Dict[str, Any]], db=None) -> int:
        """批量写入 Tips 到 DB"""
        session = db or self.db
        if session is None:
            raise ValueError("需要 DB session")

        count = 0
        for tip in tips:
            if not tip.get("content"):
                continue
            try:
                session.execute(sqlalchemy.text("""
                    INSERT INTO eval_agent_tips
                        (tip_id, tip_type, content, trigger_desc, steps,
                         source_trace_id, source_task_type, confidence, is_active)
                    VALUES
                        (:tid, :ttype, :content, :trigger, :steps,
                         :trace_id, :task_type, :conf, :active)
                """), {
                    "tid": tip.get("tip_id", str(uuid.uuid4())),
                    "ttype": tip.get("tip_type", "strategy"),
                    "content": tip["content"],
                    "trigger": tip.get("trigger_desc", ""),
                    "steps": tip.get("steps") if isinstance(tip.get("steps"), str) else json.dumps(tip.get("steps", []), ensure_ascii=False),
                    "trace_id": tip.get("source_trace_id"),
                    "task_type": tip.get("source_task_type"),
                    "conf": tip.get("confidence", 0.5),
                    "active": tip.get("is_active", 1),
                })
                count += 1
            except Exception as exc:
                logger.warning(f"[TipManager] 写入 Tip 失败: {exc}")

        session.commit()
        logger.info(f"[TipManager] 写入 {count} 条 Tips")
        return count

    def get_active_tips(
        self,
        tip_type: Optional[str] = None,
        task_type: Optional[str] = None,
        limit: int = 100,
        db=None,
    ) -> List[Dict[str, Any]]:
        """获取活跃的 Tips"""
        session = db or self.db
        if session is None:
            return []

        conditions = ["is_active = 1"]
        params: Dict[str, Any] = {"limit": limit}

        if tip_type:
            conditions.append("tip_type = :ttype")
            params["ttype"] = tip_type
        if task_type:
            conditions.append("source_task_type = :task_type")
            params["task_type"] = task_type

        where = " AND ".join(conditions)
        rows = session.execute(sqlalchemy.text(
            f"SELECT * FROM eval_agent_tips WHERE {where} "
            f"ORDER BY confidence DESC, reference_count DESC LIMIT :limit"
        ), params).fetchall()

        return [dict(r._mapping) for r in rows]

    def increment_reference(self, tip_ids: List[str], db=None) -> None:
        """增加 Tips 被引用计数"""
        session = db or self.db
        if session is None or not tip_ids:
            return

        for tid in tip_ids:
            session.execute(sqlalchemy.text(
                "UPDATE eval_agent_tips SET reference_count = reference_count + 1 WHERE tip_id = :tid"
            ), {"tid": tid})
        session.commit()

    def toggle_tip(self, tip_id: str, active: bool, db=None) -> None:
        """启用/禁用 Tip"""
        session = db or self.db
        if session is None:
            return

        session.execute(sqlalchemy.text(
            "UPDATE eval_agent_tips SET is_active = :active WHERE tip_id = :tid"
        ), {"active": 1 if active else 0, "tid": tip_id})
        session.commit()

    def get_stats(self, db=None) -> Dict[str, Any]:
        """获取 Tips 统计信息"""
        session = db or self.db
        if session is None:
            return {}

        row = session.execute(sqlalchemy.text("""
            SELECT
                COUNT(*) as total,
                SUM(is_active) as active,
                SUM(tip_type = 'strategy') as strategy_count,
                SUM(tip_type = 'recovery') as recovery_count,
                SUM(tip_type = 'optimization') as optimization_count,
                AVG(confidence) as avg_confidence,
                SUM(reference_count) as total_references
            FROM eval_agent_tips
        """)).fetchone()

        if row is None:
            return {}

        r = dict(row._mapping)
        return {
            "total": int(r.get("total") or 0),
            "active": int(r.get("active") or 0),
            "strategy_count": int(r.get("strategy_count") or 0),
            "recovery_count": int(r.get("recovery_count") or 0),
            "optimization_count": int(r.get("optimization_count") or 0),
            "avg_confidence": round(float(r.get("avg_confidence") or 0), 4),
            "total_references": int(r.get("total_references") or 0),
        }

    async def generalize_tip(self, content: str, trigger: str) -> Dict[str, str]:
        """泛化 Tip 描述（LLM 辅助）"""
        from openai import AsyncOpenAI
        from backend.config import settings

        prompt = GENERALIZE_PROMPT.format(content=content, trigger=trigger)
        try:
            client = AsyncOpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL)
            response = await client.chat.completions.create(
                model=settings.LLM_MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=512,
            )
            text = response.choices[0].message.content or ""
            result = json.loads(text) if text.strip().startswith("{") else {}
            return {
                "generalized_content": result.get("generalized_content", content),
                "generalized_trigger": result.get("generalized_trigger", trigger),
            }
        except Exception as exc:
            logger.warning(f"[TipManager] 泛化失败: {exc}")
            return {"generalized_content": content, "generalized_trigger": trigger}
