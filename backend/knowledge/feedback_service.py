# -*- coding: utf-8 -*-
"""§3.4 反馈闭环 · KB Feedback 服务层。

定位
----
独立于 ``KnowledgeBaseService``，专注 ``kb_feedback`` 表的 CRUD + 聚合。
后续 Phase γ 的 ``bad_case_collector`` self-monitor 自动打标也会写入同一张表，
通过 ``source`` 字段区分场景（biz_kb / admin_kb / copilot_biz_rag / api_external）。

设计要点
--------
* 写入：可选 upsert —— 同一 (user_id, trace_id) 24h 内已存在则更新，否则插入；
  没有 trace_id 时直接 insert（无幂等键不强求合并）。
* 列表：admin 用，按 rating/kb/source/起止时间过滤；分页。
* 聚合：窗口期内 positive/negative/neutral 数与 negative_rate；分库 / 分原因 / 分来源。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session


class KBFeedbackService:
    """单例服务，避免反复构造。"""

    _instance: Optional["KBFeedbackService"] = None

    @classmethod
    def get_instance(cls) -> "KBFeedbackService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── 写入 ────────────────────────────────────────────────────

    def submit(
        self,
        db: Session,
        *,
        user_id: str,
        query: str,
        rating: int,
        trace_id: Optional[str] = None,
        kb_id: Optional[str] = None,
        answer: Optional[str] = None,
        citations: Optional[List[Dict[str, Any]]] = None,
        rating_reason: Optional[str] = None,
        free_text: Optional[str] = None,
        source: str = "biz_kb",
    ) -> Dict[str, Any]:
        """写入或更新一条反馈。

        upsert 规则：当 ``trace_id`` 非空时，若同 (user_id, trace_id) 24h 内已存在，
        则覆盖 rating / rating_reason / free_text / answer / citations / kb_id。
        否则 insert 新行。返回 ``{"feedback_id": int, "action": "insert" | "update"}``。
        """
        citations_json = json.dumps(citations, ensure_ascii=False) if citations else None

        existing_id: Optional[int] = None
        if trace_id:
            row = db.execute(sa_text(
                "SELECT feedback_id FROM kb_feedback "
                "WHERE user_id=:uid AND trace_id=:tid "
                "  AND created_at >= NOW() - INTERVAL 1 DAY "
                "ORDER BY created_at DESC LIMIT 1"
            ), {"uid": user_id, "tid": trace_id}).fetchone()
            if row is not None:
                existing_id = int(row._mapping["feedback_id"])

        if existing_id is not None:
            db.execute(sa_text(
                "UPDATE kb_feedback SET "
                "  rating=:r, rating_reason=:rr, free_text=:ft, "
                "  answer=COALESCE(:a, answer), citations=COALESCE(:c, citations), "
                "  kb_id=COALESCE(:kid, kb_id), source=:src "
                "WHERE feedback_id=:fid"
            ), {
                "r": rating, "rr": rating_reason, "ft": free_text,
                "a": answer, "c": citations_json,
                "kid": kb_id, "src": source, "fid": existing_id,
            })
            db.commit()
            logger.info(f"[KBFeedback] update id={existing_id} user={user_id} rating={rating}")
            return {"feedback_id": existing_id, "action": "update"}

        result = db.execute(sa_text(
            "INSERT INTO kb_feedback "
            "(trace_id, user_id, kb_id, query, answer, citations, "
            " rating, rating_reason, free_text, source) "
            "VALUES (:tid, :uid, :kid, :q, :a, :c, "
            "        :r, :rr, :ft, :src)"
        ), {
            "tid": trace_id, "uid": user_id, "kid": kb_id,
            "q": query, "a": answer, "c": citations_json,
            "r": rating, "rr": rating_reason, "ft": free_text, "src": source,
        })
        db.commit()
        new_id = int(result.lastrowid) if hasattr(result, "lastrowid") and result.lastrowid else 0
        logger.info(f"[KBFeedback] insert id={new_id} user={user_id} rating={rating} src={source}")
        return {"feedback_id": new_id, "action": "insert"}

    # ── 列表 ────────────────────────────────────────────────────

    def list(
        self,
        db: Session,
        *,
        rating: Optional[int] = None,
        kb_id: Optional[str] = None,
        source: Optional[str] = None,
        days: int = 30,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """admin 用：分页列出最近 N 天的反馈。"""
        days = max(1, min(days, 365))
        limit = max(1, min(limit, 200))
        offset = max(0, offset)

        where = ["created_at >= NOW() - INTERVAL :days DAY"]
        params: Dict[str, Any] = {"days": days}
        if rating is not None:
            where.append("rating = :rating")
            params["rating"] = rating
        if kb_id:
            where.append("kb_id = :kb_id")
            params["kb_id"] = kb_id
        if source:
            where.append("source = :src")
            params["src"] = source
        where_sql = " AND ".join(where)

        total = db.execute(sa_text(
            f"SELECT COUNT(*) FROM kb_feedback WHERE {where_sql}"
        ), params).scalar() or 0

        params["limit"] = limit
        params["offset"] = offset
        rows = db.execute(sa_text(
            f"SELECT feedback_id, trace_id, user_id, kb_id, query, answer, citations, "
            f"       rating, rating_reason, free_text, source, created_at "
            f"FROM kb_feedback WHERE {where_sql} "
            f"ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
        ), params).fetchall()

        items: List[Dict[str, Any]] = []
        for r in rows:
            m = dict(r._mapping)
            if isinstance(m.get("citations"), str):
                try:
                    m["citations"] = json.loads(m["citations"])
                except Exception:
                    m["citations"] = None
            items.append(m)

        return {"total": int(total), "items": items, "limit": limit, "offset": offset}

    # ── 聚合 ────────────────────────────────────────────────────

    def stats(self, db: Session, *, days: int = 7) -> Dict[str, Any]:
        """聚合：window 内总数、正负/中性分布、分库/分原因/分来源。"""
        days = max(1, min(days, 365))

        base = db.execute(sa_text(
            "SELECT "
            "  COUNT(*)                                            AS total, "
            "  SUM(CASE WHEN rating= 1 THEN 1 ELSE 0 END)          AS positive, "
            "  SUM(CASE WHEN rating=-1 THEN 1 ELSE 0 END)          AS negative, "
            "  SUM(CASE WHEN rating= 0 THEN 1 ELSE 0 END)          AS neutral "
            "FROM kb_feedback WHERE created_at >= NOW() - INTERVAL :days DAY"
        ), {"days": days}).fetchone()
        m = dict(base._mapping) if base else {}
        total = int(m.get("total") or 0)
        positive = int(m.get("positive") or 0)
        negative = int(m.get("negative") or 0)
        neutral = int(m.get("neutral") or 0)
        negative_rate = round(negative / total, 4) if total > 0 else 0.0

        # 分 kb（左联 kb_libraries 拿 name）
        by_kb_rows = db.execute(sa_text(
            "SELECT f.kb_id AS kb_id, "
            "       COALESCE(l.name, '(unknown)') AS kb_name, "
            "       COUNT(*) AS total, "
            "       SUM(CASE WHEN f.rating=-1 THEN 1 ELSE 0 END) AS negative "
            "FROM kb_feedback f "
            "LEFT JOIN kb_libraries l ON l.kb_id = f.kb_id "
            "WHERE f.created_at >= NOW() - INTERVAL :days DAY "
            "GROUP BY f.kb_id, l.name "
            "ORDER BY negative DESC, total DESC"
        ), {"days": days}).fetchall()
        by_kb: List[Dict[str, Any]] = []
        for r in by_kb_rows:
            mm = dict(r._mapping)
            t = int(mm.get("total") or 0)
            n = int(mm.get("negative") or 0)
            by_kb.append({
                "kb_id": mm.get("kb_id"),
                "kb_name": mm.get("kb_name"),
                "total": t,
                "negative": n,
                "negative_rate": round(n / t, 4) if t > 0 else 0.0,
            })

        # 分 reason（仅 rating=-1）
        by_reason_rows = db.execute(sa_text(
            "SELECT COALESCE(rating_reason, '(none)') AS rating_reason, "
            "       COUNT(*) AS count "
            "FROM kb_feedback "
            "WHERE rating=-1 AND created_at >= NOW() - INTERVAL :days DAY "
            "GROUP BY rating_reason ORDER BY count DESC"
        ), {"days": days}).fetchall()
        by_reason = [dict(r._mapping) for r in by_reason_rows]
        for item in by_reason:
            item["count"] = int(item.get("count") or 0)

        # 分 source
        by_source_rows = db.execute(sa_text(
            "SELECT source, COUNT(*) AS total, "
            "       SUM(CASE WHEN rating=-1 THEN 1 ELSE 0 END) AS negative "
            "FROM kb_feedback "
            "WHERE created_at >= NOW() - INTERVAL :days DAY "
            "GROUP BY source ORDER BY total DESC"
        ), {"days": days}).fetchall()
        by_source: List[Dict[str, Any]] = []
        for r in by_source_rows:
            mm = dict(r._mapping)
            by_source.append({
                "source": mm.get("source"),
                "total": int(mm.get("total") or 0),
                "negative": int(mm.get("negative") or 0),
            })

        return {
            "window_days": days,
            "total": total,
            "positive": positive,
            "negative": negative,
            "neutral": neutral,
            "negative_rate": negative_rate,
            "by_kb": by_kb,
            "by_reason": by_reason,
            "by_source": by_source,
        }
