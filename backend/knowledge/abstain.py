# -*- coding: utf-8 -*-
"""backend/knowledge/abstain.py — §3.2 Abstain 正确拒答判定

职责：基于 SearchEngine.search() 返回的结构化结果，判定是否应拒答，
并产出结构化 abstain payload 供 Copilot skill / API 短路返回。

四种应拒答场景（决策顺序）：
  1. no_evidence       — hits == []
  2. domain_forbidden  — 所有 hit 的 kb_domain 都不在 allowed_domains（简版，§7.3 完善）
  3. ambiguous         — confidence == "ambiguous"（优先于 low，保留澄清语义）
  4. low_confidence    — confidence ∈ {"low", "none"}

向后兼容：
  - 当 settings.KB_ABSTAIN_ENABLED=False 时 should_abstain() 永远返回 None
  - 对 high / medium 结果不干预，直接返回 None
  - 不修改 search_result 内容，只读

说明：
  - grounded_ratio < 0.8 触发的 "ungrounded_llm_output" 归 §3.1 Grounding，
    由后验校验环节调用 build_abstain(reason="ungrounded_llm_output", ...) 产出。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

ABSTAIN_REASONS = {
    "no_evidence",
    "low_confidence",
    "ambiguous",
    "domain_forbidden",
    # 预留：grounded_ratio 过低时由 §3.1 Grounding 触发
    "ungrounded_llm_output",
}


def should_abstain(
    search_result: Dict[str, Any],
    *,
    allowed_domains: Optional[Set[str]] = None,
    settings: Any = None,
) -> Optional[Dict[str, Any]]:
    """根据检索结果判定是否应拒答。

    参数：
        search_result: SearchEngine.search() 返回的 dict，至少含 hits/confidence 字段。
        allowed_domains: 当前用户允许访问的 kb_domain 集合；None 表示不做 domain 校验。
        settings: 注入的配置对象；None 时自动从 backend.config 取全局 settings。

    返回：
        None 或 abstain payload dict（见 _build_abstain）。
    """
    cfg = settings if settings is not None else _load_settings()
    if not getattr(cfg, "KB_ABSTAIN_ENABLED", True):
        return None

    hits: List[Dict[str, Any]] = list(search_result.get("hits") or [])
    confidence: str = search_result.get("confidence", "none") or "none"
    top_k = int(getattr(cfg, "KB_ABSTAIN_FALLBACK_SUGGEST_COUNT", 3))

    # 场景 1: 无证据
    if not hits:
        return _build_abstain(
            reason="no_evidence",
            message=getattr(cfg, "KB_ABSTAIN_MSG_NO_EVIDENCE", "现有资料未收录此信息。"),
            search_result=search_result,
            candidates=[],
        )

    # 场景 4: 越权（只有当 allowed_domains 明确提供时才做此判定）
    if allowed_domains is not None:
        hits_with_domain = [h for h in hits if h.get("kb_domain")]
        if hits_with_domain:
            forbidden = [h for h in hits_with_domain if h["kb_domain"] not in allowed_domains]
            # 只有当"所有带 domain 信息的 hits"全部越权时才拒答
            # 存在 allowed hits 则继续走后续流程（由用户筛选）
            if forbidden and len(forbidden) == len(hits_with_domain):
                return _build_abstain(
                    reason="domain_forbidden",
                    message=getattr(cfg, "KB_ABSTAIN_MSG_DOMAIN_FORBIDDEN",
                                    "你无权访问此类资料。"),
                    search_result=search_result,
                    candidates=[],
                )

    # 场景 3: 歧义（优先于 low_confidence，保留澄清语义）
    if confidence == "ambiguous":
        return _build_abstain(
            reason="ambiguous",
            message=getattr(cfg, "KB_ABSTAIN_MSG_AMBIGUOUS",
                            "找到多个可能相关的内容，请选择方向。"),
            search_result=search_result,
            disambiguate_options=_to_options(hits[:top_k]),
        )

    # 场景 2: 低置信（含 none 档）
    if confidence in ("low", "none"):
        return _build_abstain(
            reason="low_confidence",
            message=getattr(cfg, "KB_ABSTAIN_MSG_LOW_CONFIDENCE",
                            "未找到足够可靠的资料。"),
            search_result=search_result,
            candidates=_to_options(hits[:top_k]),
        )

    # high / medium 档不拒答
    return None


def build_abstain(
    reason: str,
    message: str,
    *,
    candidates: Optional[List[Dict[str, Any]]] = None,
    disambiguate_options: Optional[List[Dict[str, Any]]] = None,
    partial_answer: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """对外的 abstain payload 构造函数（非搜索路径也可复用）。

    供 §3.1 Grounding 后验校验、§3.3 Router 的 out_of_scope 场景调用。
    """
    if reason not in ABSTAIN_REASONS:
        raise ValueError(f"unknown abstain reason: {reason}")

    payload: Dict[str, Any] = {
        "abstain": True,
        "reason": reason,
        "message": message,
        "candidates": candidates or [],
        "disambiguate_options": disambiguate_options or [],
        "suggestions": _default_fallback_suggestions(reason),
    }
    if partial_answer:
        payload["partial_answer"] = partial_answer
    if extra:
        payload.update(extra)
    return payload


# ════════════════════════════════════════════════════════════════════
# 内部工具
# ════════════════════════════════════════════════════════════════════

def _build_abstain(
    *,
    reason: str,
    message: str,
    search_result: Dict[str, Any],
    candidates: Optional[List[Dict[str, Any]]] = None,
    disambiguate_options: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """从 search_result 提取 meta 再调用 build_abstain。"""
    payload = build_abstain(
        reason=reason,
        message=message,
        candidates=candidates,
        disambiguate_options=disambiguate_options,
    )
    # 附带检索层的 meta（便于前端 debug / 可观测性）
    payload["confidence"] = search_result.get("confidence", "none")
    payload["confidence_score"] = search_result.get("confidence_score", 0.0)
    payload["ambiguous_reason"] = search_result.get("ambiguous_reason")
    payload["search_mode"] = search_result.get("search_mode")
    payload["degraded"] = bool(search_result.get("degraded"))
    return payload


def _to_options(hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """把 hits 精简成给前端展示的候选卡片。"""
    options = []
    for h in hits:
        content = h.get("content") or ""
        options.append({
            "title": h.get("title") or h.get("kb_name") or "未命名",
            "kb_id": h.get("kb_id"),
            "kb_name": h.get("kb_name"),
            "kb_domain": h.get("kb_domain"),
            "document_id": h.get("document_id"),
            "score": round(float(h.get("rerank_score", h.get("score", 0)) or 0), 4),
            "snippet": content[:160],
        })
    return options


def _default_fallback_suggestions(reason: str) -> List[Dict[str, str]]:
    """通用 fallback 建议（给用户的下一步动作）。

    与方案 §3.2 "Abstain 不是甩手不管，要给下一步" 对齐。
    """
    base = [
        {"type": "action", "label": "换个问法重新提问"},
        {"type": "nav", "label": "浏览知识库目录", "target": "/console/knowledge-v2"},
    ]
    extra_map = {
        "no_evidence": [
            {"type": "action", "label": "联系知识库管理员补充资料"},
        ],
        "low_confidence": [
            {"type": "action", "label": "参考上述候选后精化提问"},
        ],
        "ambiguous": [
            {"type": "action", "label": "选择候选方向后继续提问"},
        ],
        "domain_forbidden": [
            {"type": "action", "label": "联系管理员申请权限"},
        ],
        "ungrounded_llm_output": [
            {"type": "action", "label": "仅参考可核验的部分回答"},
        ],
    }
    return base + extra_map.get(reason, [])


def _load_settings():
    """延迟加载全局 settings，避免模块导入期依赖。"""
    from backend.config import settings  # noqa: WPS433
    return settings
