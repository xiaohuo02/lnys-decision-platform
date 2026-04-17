# -*- coding: utf-8 -*-
"""知识库 RAG Skill — 企业知识库 + 舆情知识库联合语义检索"""
from __future__ import annotations

from typing import AsyncGenerator

from backend.copilot.base_skill import BaseCopilotSkill, SkillContext
from backend.copilot.events import CopilotEvent, EventType


class KBRagSkill(BaseCopilotSkill):
    name = "kb_rag_skill"
    display_name = "知识库检索"
    description = "在向量化知识库中进行语义搜索，查询企业知识、舆情知识、经营报告模板、工作流程说明、业务规范。当用户询问报告内容建议、工作流分析、流程步骤解读、搜索知识库、查询文档、找资料、或问题需要知识库辅助回答时调用。注意：不要用此工具回答风控/欺诈/库存/销售/客户/舆情等有专用分析工具的问题。"
    required_roles = {
        # DB 真实角色：知识库是最基础的查询功能，所有真实角色都放行
        "platform_admin", "ops_analyst", "ml_engineer",
        "customer_service_manager", "risk_reviewer", "auditor", "employee",
        # legacy 兼容
        "super_admin", "business_admin", "biz_operator", "biz_viewer",
    }
    mode = {"ops", "biz"}
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索查询文本",
            },
            "top_k": {
                "type": "integer",
                "description": "返回最相似的K条结果",
                "default": 5,
            },
            "entity_filter": {
                "type": "string",
                "description": "实体过滤（可选）",
            },
        },
        "required": ["query"],
    }

    async def execute(self, question: str, context: SkillContext) -> AsyncGenerator[CopilotEvent, None]:
        query = context.tool_args.get("query", question)
        top_k = context.tool_args.get("top_k", 5)
        entity = context.tool_args.get("entity_filter")

        results = []
        search_result = None  # SearchEngine 原始返回，供 §3.2 Abstain 判定

        # 优先使用新统一 SearchEngine
        try:
            from backend.knowledge.service import KnowledgeBaseService
            svc = KnowledgeBaseService.get_instance()
            search_result = svc.search(query=query, top_k=top_k, mode="hybrid")
            for hit in search_result.get("hits", []):
                results.append({
                    "source": hit.get("kb_name", "unknown"),
                    "content": hit.get("content", ""),
                    "score": hit.get("score", 0),
                    "metadata": {
                        "doc_id": hit.get("document_id", ""),
                        "title": hit.get("title", ""),
                        "kb_id": hit.get("kb_id", ""),
                        "search_mode": hit.get("search_mode", ""),
                    },
                })
        except Exception:
            search_result = None

        # Fallback: 旧逻辑（逐库查询）
        if not results:
            try:
                from backend.services.enterprise_kb_service import EnterpriseKBService
                ent_kb = EnterpriseKBService.get_instance()
                ent_results = await ent_kb.search(query=query, top_k=top_k)
                for r in (ent_results or []):
                    results.append({
                        "source": "enterprise_faq",
                        "content": r.get("content", ""),
                        "score": r.get("similarity", 0),
                        "metadata": {
                            "doc_id": r.get("doc_id", ""),
                            "title": r.get("title", ""),
                            "group_name": r.get("group_name", ""),
                        },
                    })
            except Exception:
                pass

            try:
                from backend.services.sentiment_kb_service import SentimentKBService
                sent_kb = SentimentKBService.get_instance()
                raw = await sent_kb.search_similar(query=query, top_k=top_k)
                sent_items = raw.get("items", []) if isinstance(raw, dict) else (raw or [])
                for r in sent_items:
                    results.append({
                        "source": "sentiment_reviews",
                        "content": r.get("text", r.get("content", "")),
                        "score": r.get("similarity", r.get("score", 0)),
                        "metadata": {k: v for k, v in r.items() if k not in ("text", "content", "similarity", "score")},
                    })
            except Exception:
                pass

            # fallback 路径无 SearchEngine 元信息：若仍空，构造 no_evidence 占位供 abstain 判定
            if not results and search_result is None:
                search_result = {
                    "hits": [],
                    "confidence": "none",
                    "confidence_score": 0.0,
                    "ambiguous_reason": None,
                    "search_mode": "fallback",
                    "degraded": True,
                }

        # 按相似度降序排序，取 top_k
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        results = results[:top_k]

        # ── §3.2 Abstain 正确拒答判定 ───────────────────────────
        abstain_payload = None
        if search_result is not None:
            try:
                from backend.knowledge.abstain import should_abstain
                abstain_payload = should_abstain(search_result)
            except Exception:
                abstain_payload = None

        if abstain_payload:
            # 拒答分支：不走 LLM synthesize，由 engine 识别 data.abstain=True 短路
            yield CopilotEvent(
                type=EventType.ARTIFACT_START,
                artifact_type="abstain",
                metadata={
                    "title": "知识库未提供可靠答复",
                    "component": "AbstainCard",
                    "reason": abstain_payload.get("reason"),
                },
            )
            yield CopilotEvent(
                type=EventType.ARTIFACT_DELTA,
                content=abstain_payload,
            )
            yield CopilotEvent(type=EventType.ARTIFACT_END)

            # 文案流式（旧前端不识别 AbstainCard 时也能看到）
            yield CopilotEvent(
                type=EventType.TEXT_DELTA,
                content=abstain_payload.get("message", "未能提供可靠答复。"),
            )
            candidates = (
                abstain_payload.get("disambiguate_options")
                or abstain_payload.get("candidates")
                or []
            )
            if candidates:
                yield CopilotEvent(type=EventType.TEXT_DELTA, content="\n\n候选参考：\n")
                for idx, cand in enumerate(candidates, 1):
                    title = cand.get("title", "未命名")
                    kb_name = cand.get("kb_name") or ""
                    score = cand.get("score", 0) or 0
                    line = f"{idx}. {title}"
                    if kb_name:
                        line += f"（{kb_name}，得分 {score:.2f}）"
                    yield CopilotEvent(type=EventType.TEXT_DELTA, content=line + "\n")

            # Suggestions：把 abstain.suggestions 映射为 Copilot SUGGESTIONS 结构
            sug_items = []
            for s in abstain_payload.get("suggestions", []):
                item = {"label": s.get("label", "")}
                item["type"] = "nav" if s.get("type") == "nav" else "question"
                if s.get("target"):
                    item["target"] = s["target"]
                sug_items.append(item)
            if sug_items:
                yield CopilotEvent(type=EventType.SUGGESTIONS, items=sug_items)

            # TOOL_RESULT：关键字段 abstain=True 让 engine 跳过后续 synthesize
            yield CopilotEvent(
                type=EventType.TOOL_RESULT,
                data={
                    "abstain": True,
                    "reason": abstain_payload.get("reason"),
                    "message": abstain_payload.get("message"),
                    "confidence": abstain_payload.get("confidence"),
                    "confidence_score": abstain_payload.get("confidence_score"),
                    "ambiguous_reason": abstain_payload.get("ambiguous_reason"),
                    "candidates": abstain_payload.get("candidates", []),
                    "disambiguate_options": abstain_payload.get("disambiguate_options", []),
                    "query": query,
                    "total": len(results),
                    "hits": results[:top_k],  # 原始 hits 保留供 bad_case 回流
                },
            )
            return

        # ── 非拒答：原 results 路径 ───────────────────────────────
        # §3.1 L1：给每个 hit 分配稳定 cid，供 LLM 引用 + 后处理校验
        citations = []
        for idx, r in enumerate(results, 1):
            meta = r.get("metadata", {}) or {}
            citations.append({
                "cid": f"c_{idx:03d}",
                "chunk_id": meta.get("doc_id") or meta.get("chunk_id") or "",
                "doc_title": meta.get("title") or "",
                "kb_name": r.get("source") or "",
                "kb_id": meta.get("kb_id") or "",
                "content": r.get("content") or r.get("document") or "",
                "score": round(float(r.get("score", 0) or 0), 4),
            })

        yield CopilotEvent(
            type=EventType.ARTIFACT_START,
            artifact_type="search_results",
            metadata={
                "title": f"知识库检索 — '{query[:30]}' ({len(results)} 条结果)",
                "component": "SearchResultsArtifact",
            },
        )
        yield CopilotEvent(
            type=EventType.ARTIFACT_DELTA,
            content={
                "query": query,
                "results": [
                    {
                        "cid": citations[i]["cid"],
                        "content": r.get("content", r.get("document", "")),
                        "score": r.get("score", r.get("distance", 0)),
                        "metadata": r.get("metadata", {}),
                    }
                    for i, r in enumerate(results)
                ] if results else [],
            },
        )
        yield CopilotEvent(type=EventType.ARTIFACT_END)

        yield CopilotEvent(
            type=EventType.SUGGESTIONS,
            items=[
                {"type": "question", "label": "帮我总结这些检索结果"},
                {"type": "question", "label": "有没有相关的其他资料？"},
            ],
        )

        yield CopilotEvent(
            type=EventType.TOOL_RESULT,
            data={
                "query": query,
                "total": len(results) if results else 0,
                "results": results[:5] if results else [],
                "citations": citations,            # §3.1 L1 供 engine 注入引用规则
                "require_grounding": bool(citations),  # 非空才启用 grounding
            },
        )


kb_rag_skill = KBRagSkill()
