# -*- coding: utf-8 -*-
"""backend/copilot/context.py — 三层上下文管理器（AsyncSession + ORM）

借鉴 Claude Code 三层记忆架构:
  Layer 1 (In-Context):  Redis 对话历史 + 页面上下文
  Layer 2 (memory.md):   copilot_memory 表（Agent 自主维护）
  Layer 3 (CLAUDE.md):   copilot_rules 表（管理员静态配置）

所有 DB 查询通过 AsyncSession + ORM Model 实现，不阻塞事件循环。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.copilot.base_skill import SkillContext
from backend.models.copilot import CopilotRule, CopilotMemory, CopilotMessage


class ContextManager:
    """每次会话启动时构建完整上下文"""

    def __init__(self, redis=None, db=None):
        self._redis = redis
        self._db = db

    async def build(
        self,
        thread_id: str,
        user_id: str,
        user_role: str,
        mode: str,
        page_context: Optional[Dict[str, Any]] = None,
        source: str = "web",
    ) -> SkillContext:
        """构建完整的 SkillContext"""
        # Layer 3: 静态规则（每次会话必加载）
        rules = await self._load_rules(mode)

        # Layer 2: 用户记忆（按 importance 排序，取 top-K）
        memories = await self._load_top_memories(user_id, top_k=10)

        # Layer 1: 对话历史
        history = await self._load_thread_history(thread_id, max_turns=5)

        # 组装 system prompt
        system_prompt = self._compose_system_prompt(
            mode=mode,
            rules=rules,
            memories=memories,
            page_context=page_context or {},
        )

        return SkillContext(
            user_id=user_id,
            user_role=user_role,
            mode=mode,
            thread_id=thread_id,
            page_context=page_context or {},
            thread_history=history,
            system_prompt=system_prompt,
            source=source,
        )

    # ── Layer 3: 静态规则 ──

    async def _load_rules(self, mode: str) -> List[Dict[str, str]]:
        """从 copilot_rules 表加载静态规则"""
        if self._db is None:
            return self._default_rules(mode)
        try:
            stmt = (
                select(CopilotRule.title, CopilotRule.content)
                .where(
                    CopilotRule.scope.in_(["global", mode]),
                    CopilotRule.is_active == True,
                )
                .order_by(CopilotRule.priority.desc())
            )
            result = await self._db.execute(stmt)
            rows = result.all()
            if rows:
                return [{"title": r.title, "content": r.content} for r in rows]
        except Exception as e:
            logger.debug(f"[ContextManager] rules 表加载失败（可能不存在）: {e}")
        return self._default_rules(mode)

    @staticmethod
    def _default_rules(mode: str) -> List[Dict[str, str]]:
        """内置默认规则（copilot_rules 表不存在时使用）"""
        base = [
            {
                "title": "身份",
                "content": (
                    "你是柠优生活大数据智能决策平台的AI助手。"
                    "你的回答应该准确、专业、有数据支撑。"
                    "当用户询问你不确定的内容时，明确说明不确定而不是编造。"
                ),
            },
            {
                "title": "语言规则",
                "content": (
                    "默认使用中文回答用户。"
                    "即使用户用英文提问，也优先用中文回答，除非用户明确要求用英文。"
                    "代码、技术名词、英文缩写可保留原文。"
                ),
            },
            {
                "title": "输出格式",
                "content": (
                    "使用 Markdown 格式回答。"
                    "数据分析结果用表格或列表呈现。"
                    "关键数字用加粗标记。"
                    "给出分析结论和可操作建议。"
                ),
            },
        ]
        if mode == "ops":
            base.append({
                "title": "运维助手角色",
                "content": (
                    "你是运维助手，具有平台全部功能的访问权限。"
                    "你可以查询系统健康状态、Trace 跟踪、评测结果、Prompt 版本等运维信息。"
                    "你可以访问所有业务数据（客户洞察、销售预测、舆情分析、库存优化、欺诈检测等）。"
                    "你可以建议执行操作（如发送飞书通知），但需要用户确认。"
                ),
            })
        else:
            base.append({
                "title": "运营助手角色",
                "content": (
                    "你是运营助手，具有业务空间功能的访问权限。"
                    "你可以访问客户洞察、销售预测、舆情分析、库存优化、关联分析等业务数据。"
                    "你不能访问系统运维信息（Trace、评测、Prompt 管理等）。"
                    "你可以建议执行操作（如发送飞书通知），但需要用户确认。"
                ),
            })
        return base

    # ── Layer 2: 用户记忆 ──

    async def _load_top_memories(self, user_id: str, top_k: int = 10) -> List[Dict[str, str]]:
        """从 copilot_memory 表加载用户记忆"""
        if self._db is None:
            return []
        try:
            stmt = (
                select(CopilotMemory.domain, CopilotMemory.title, CopilotMemory.content)
                .where(
                    CopilotMemory.user_id == user_id,
                    CopilotMemory.is_active == True,
                )
                .order_by(CopilotMemory.importance.desc(), CopilotMemory.updated_at.desc())
                .limit(top_k)
            )
            result = await self._db.execute(stmt)
            rows = result.all()
            return [{"domain": r.domain, "title": r.title, "content": r.content} for r in rows]
        except Exception as e:
            logger.debug(f"[ContextManager] memory 表加载失败（可能不存在）: {e}")
            return []

    # ── Layer 1: 对话历史 ──

    async def _load_thread_history(self, thread_id: str, max_turns: int = 5) -> list:
        """从 Redis 加载最近 N 轮对话，Redis 为空时回退到 MySQL"""
        history = []
        # Layer 1: Redis (fast)
        if self._redis is not None:
            try:
                key = f"copilot:thread:{thread_id}"
                raw = await self._redis.lrange(key, -max_turns * 2, -1)
                if raw:
                    history = [json.loads(item) for item in raw]
            except Exception as e:
                logger.debug(f"[ContextManager] Redis 历史加载失败: {e}")

        # Fallback: MySQL (when Redis is empty, e.g. after restart or expired)
        if not history and self._db is not None:
            try:
                stmt = (
                    select(CopilotMessage.role, CopilotMessage.content)
                    .where(CopilotMessage.thread_id == thread_id)
                    .order_by(CopilotMessage.created_at.desc())
                    .limit(max_turns * 2)
                )
                result = await self._db.execute(stmt)
                rows = result.all()
                if rows:
                    history = [{"role": r.role, "content": r.content} for r in reversed(rows)]
                    # 回填到 Redis：单次 rpush 批量推送，避免 N 次网络往返
                    if self._redis is not None and history:
                        try:
                            key = f"copilot:thread:{thread_id}"
                            payloads = [
                                json.dumps(item, ensure_ascii=False) for item in history
                            ]
                            await self._redis.rpush(key, *payloads)
                            await self._redis.expire(key, 86400 * 7)
                        except Exception as e:
                            logger.debug(f"[ContextManager] Redis 回填失败: {e}")
            except Exception as e:
                logger.debug(f"[ContextManager] MySQL 历史回退失败: {e}")

        return history

    async def save_to_thread_history(
        self, thread_id: str, role: str, content: str
    ) -> None:
        """保存一条消息到 Redis 对话历史"""
        if self._redis is None:
            return
        try:
            key = f"copilot:thread:{thread_id}"
            item = json.dumps({"role": role, "content": content}, ensure_ascii=False)
            await self._redis.rpush(key, item)
            await self._redis.ltrim(key, -20, -1)  # 保留最近 20 条
            await self._redis.expire(key, 86400 * 7)  # 7 天过期
        except Exception as e:
            logger.warning(f"[ContextManager] Redis 保存失败: {e}")

    # ── System Prompt 组装 ──

    def _compose_system_prompt(
        self,
        mode: str,
        rules: List[Dict[str, str]],
        memories: List[Dict[str, str]],
        page_context: Dict[str, Any],
    ) -> str:
        parts = []

        # 规则部分
        for rule in rules:
            parts.append(f"## {rule['title']}\n{rule['content']}")

        # 记忆部分
        if memories:
            parts.append("\n## 你记得的关于当前用户的信息")
            for mem in memories:
                parts.append(f"- [{mem['domain']}] {mem['title']}: {mem['content']}")

        # 页面上下文
        if page_context:
            parts.append("\n## 当前页面上下文")
            for k, v in page_context.items():
                parts.append(f"- {k}: {v}")

            # 页面路由提示：引导 LLM 优先选择与当前页面匹配的 Skill
            page = page_context.get("page", "")
            _PAGE_SKILL_HINT = {
                "fraud": "fraud_skill",
                "inventory": "inventory_skill",
                "forecast": "forecast_skill",
                "sentiment": "sentiment_skill",
                "customer": "customer_intel_skill",
                "association": "association_skill",
            }
            hint_skill = _PAGE_SKILL_HINT.get(page)
            if hint_skill:
                parts.append(
                    f"\n## 路由提示\n"
                    f"用户当前在 **{page}** 页面，请优先使用 `{hint_skill}` 工具处理该页面相关问题。"
                    f"仅当问题明确与该页面无关时，才考虑其他工具。"
                )

        return "\n\n".join(parts)

    # ── 记忆调和 ──

    async def reconcile(self, user_id: str) -> Dict[str, Any]:
        """定期调和：清理过时/矛盾/低重要度记忆

        策略:
          1. 加载用户全部活跃记忆
          2. 降低 90 天未更新且 importance < 0.3 的记忆重要度
          3. 软删除 180 天未更新且 importance < 0.2 的记忆
          4. 合并相同 domain 下标题相似的记忆（LLM 辅助判断）
          5. 记录操作日志
        """
        if self._db is None:
            return {"status": "skipped", "reason": "no db"}

        try:
            stale_days_expr = func.datediff(func.now(), CopilotMemory.updated_at)
            stmt = (
                select(
                    CopilotMemory.id, CopilotMemory.domain, CopilotMemory.title,
                    CopilotMemory.content, CopilotMemory.importance,
                    stale_days_expr.label("stale_days"),
                )
                .where(
                    CopilotMemory.user_id == user_id,
                    CopilotMemory.is_active == True,
                )
                .order_by(CopilotMemory.domain, CopilotMemory.importance.desc())
            )
            result = await self._db.execute(stmt)
            rows = result.all()
            if not rows:
                return {"status": "ok", "reviewed": 0, "decayed": 0, "deleted": 0}

            decayed = 0
            deleted = 0

            for row in rows:
                mem_id = row.id
                title = row.title
                importance = row.importance
                stale_days = row.stale_days or 0

                # 策略 3: 软删除极老且不重要的记忆
                if stale_days > 180 and importance < 0.2:
                    await self._db.execute(
                        update(CopilotMemory)
                        .where(CopilotMemory.id == mem_id)
                        .values(is_active=False)
                    )
                    deleted += 1
                    logger.info(
                        f"[reconcile] deleted memory id={mem_id} "
                        f"title='{title}' stale={stale_days}d imp={importance}"
                    )

                # 策略 2: 衰减过时但不删除的记忆
                elif stale_days > 90 and importance < 0.3:
                    new_imp = max(importance * 0.7, 0.05)
                    await self._db.execute(
                        update(CopilotMemory)
                        .where(CopilotMemory.id == mem_id)
                        .values(importance=new_imp)
                    )
                    decayed += 1

            await self._db.commit()

            stats = {
                "status": "ok",
                "reviewed": len(rows),
                "decayed": decayed,
                "deleted": deleted,
            }
            logger.info(f"[reconcile] user={user_id} {stats}")
            return stats

        except Exception as e:
            await self._db.rollback()
            logger.error(f"[reconcile] user={user_id} error: {e}")
            return {"status": "error", "error": str(e)}

    async def get_all_active_user_ids(self) -> List[str]:
        """获取所有拥有活跃记忆的用户 ID"""
        if self._db is None:
            return []
        try:
            stmt = (
                select(CopilotMemory.user_id)
                .where(CopilotMemory.is_active == True)
                .distinct()
            )
            result = await self._db.execute(stmt)
            return [row[0] for row in result.all()]
        except Exception as e:
            logger.debug(f"[ContextManager] 获取用户列表失败: {e}")
            return []
