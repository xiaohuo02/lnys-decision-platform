# -*- coding: utf-8 -*-
"""backend/knowledge/schemas.py — 知识库中台 Pydantic Schemas"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ════════════════════════════════════════════════════════════════════
#  KnowledgeBase
# ════════════════════════════════════════════════════════════════════

class KBLibraryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="唯一标识名")
    display_name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    domain: str = Field("enterprise", pattern=r"^(enterprise|sentiment|ops|general)$")
    chunk_strategy: str = Field("recursive", pattern=r"^(recursive|fixed|none)$")
    chunk_config: Optional[Dict[str, Any]] = None


class KBLibraryUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    chunk_strategy: Optional[str] = None
    chunk_config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class KBLibraryOut(BaseModel):
    kb_id: str
    name: str
    display_name: str
    description: Optional[str] = None
    domain: str
    collection_name: str
    embedding_model: str
    chunk_strategy: str
    chunk_config: Optional[Dict[str, Any]] = None
    doc_count: int = 0
    chunk_count: int = 0
    is_active: bool = True
    created_by: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ════════════════════════════════════════════════════════════════════
#  KnowledgeDocument
# ════════════════════════════════════════════════════════════════════

class KBDocumentCreate(BaseModel):
    """手动创建 FAQ 类文档（非文件上传）"""
    title: str = Field(..., min_length=1, max_length=500)
    content: str = Field(..., min_length=1)
    source_type: str = Field("faq_manual")
    group_name: Optional[str] = Field(None, description="兼容旧 FAQ 分组")


class KBDocumentOut(BaseModel):
    document_id: str
    kb_id: str
    title: str
    source_type: str
    source_uri: Optional[str] = None
    file_name: Optional[str] = None
    file_type: Optional[str] = None
    file_size: Optional[int] = None
    status: str
    version: int
    quality_score: Optional[float] = None
    chunk_count: int = 0
    error_msg: Optional[str] = None
    created_by: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class KBDocumentDetail(KBDocumentOut):
    """含完整文本内容的详情"""
    content_raw: Optional[str] = None
    content_clean: Optional[str] = None


# ════════════════════════════════════════════════════════════════════
#  KnowledgeChunk
# ════════════════════════════════════════════════════════════════════

class KBChunkOut(BaseModel):
    chunk_id: str
    document_id: str
    kb_id: str
    chunk_index: int
    content: str
    token_count: Optional[int] = None
    char_count: Optional[int] = None
    heading_path: Optional[str] = None
    chunk_type: str = "paragraph"
    embedding_status: str
    created_at: datetime

    class Config:
        from_attributes = True


# ════════════════════════════════════════════════════════════════════
#  Search
# ════════════════════════════════════════════════════════════════════

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    kb_ids: Optional[List[str]] = Field(None, description="指定知识库ID列表，None=全部活跃库")
    top_k: int = Field(5, ge=1, le=50)
    min_score: float = Field(0.3, ge=0.0, le=1.0)
    search_mode: str = Field("hybrid", pattern=r"^(hybrid|vector|keyword)$")


class SearchHit(BaseModel):
    chunk_id: str
    document_id: str
    kb_id: str
    kb_name: str = ""
    title: str = ""
    content: str = ""
    score: float = 0.0
    heading_path: Optional[str] = None
    chunk_type: str = "paragraph"
    search_mode: str = "hybrid"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AbstainCandidate(BaseModel):
    """候选卡片（供前端 abstain 卡片展示）。"""
    title: str
    kb_id: Optional[str] = None
    kb_name: Optional[str] = None
    kb_domain: Optional[str] = None
    document_id: Optional[str] = None
    score: float = 0.0
    snippet: Optional[str] = None


class AbstainSuggestion(BaseModel):
    """拒答时给用户的下一步建议。"""
    type: str  # action / nav
    label: str
    target: Optional[str] = None


class AbstainPayload(BaseModel):
    """§3.2 拒答载荷。abstain=True 时由 skill 短路返回。"""
    abstain: bool = True
    reason: str  # no_evidence / low_confidence / ambiguous / domain_forbidden / ungrounded_llm_output
    message: str
    confidence: Optional[str] = None
    confidence_score: Optional[float] = None
    ambiguous_reason: Optional[str] = None
    search_mode: Optional[str] = None
    degraded: bool = False
    candidates: List[AbstainCandidate] = Field(default_factory=list)
    disambiguate_options: List[AbstainCandidate] = Field(default_factory=list)
    suggestions: List[AbstainSuggestion] = Field(default_factory=list)
    partial_answer: Optional[str] = None


class SearchResponse(BaseModel):
    query: str
    hits: List[SearchHit] = Field(default_factory=list)
    total: int = 0
    search_mode: str = "hybrid"
    degraded: bool = False
    degraded_reason: Optional[str] = None
    reranked: bool = False
    confidence: str = "none"
    confidence_score: float = 0.0
    ambiguous: bool = False
    ambiguous_reason: Optional[str] = None
    suggestion: str = "transfer_human"
    elapsed_ms: float = 0.0
    abstain: Optional[AbstainPayload] = None


# ════════════════════════════════════════════════════════════════════
#  §3.4 Feedback
# ════════════════════════════════════════════════════════════════════

# rating_reason 受控值（前端下拉用；其它走 free_text）
FEEDBACK_REASONS = (
    "inaccurate",     # 答案不准确
    "irrelevant",     # 不相关
    "outdated",       # 过时
    "incomplete",     # 不完整
    "other",
)

# source 受控值
FEEDBACK_SOURCES = (
    "biz_kb",          # 业务前台直搜
    "admin_kb",        # 管理后台 KB Console
    "copilot_biz_rag", # 业务 Copilot RAG 答案
    "api_external",    # 外部 API 调用
)


class KBFeedbackIn(BaseModel):
    """§3.4 反馈写入入参。"""
    trace_id: Optional[str] = Field(None, max_length=64, description="原 answer/search 的 trace_id")
    kb_id: Optional[str] = Field(None, max_length=36, description="命中的主 kb_id")
    query: str = Field(..., min_length=1, max_length=2000)
    answer: Optional[str] = Field(None, max_length=8000, description="RAG 答案文本")
    citations: Optional[List[Dict[str, Any]]] = Field(None, description="hits 引用列表")
    rating: int = Field(..., ge=-1, le=1, description="1=👍 / -1=👎 / 0=中性")
    rating_reason: Optional[str] = Field(None, max_length=50)
    free_text: Optional[str] = Field(None, max_length=1000)
    source: str = Field("biz_kb", max_length=20)


class KBFeedbackOut(BaseModel):
    feedback_id: int
    trace_id: Optional[str] = None
    user_id: str
    kb_id: Optional[str] = None
    query: str
    answer: Optional[str] = None
    citations: Optional[List[Dict[str, Any]]] = None
    rating: int
    rating_reason: Optional[str] = None
    free_text: Optional[str] = None
    source: str
    created_at: datetime

    class Config:
        from_attributes = True


class KBFeedbackStats(BaseModel):
    """聚合统计：用于 admin Console 看本周/本月反馈分布。"""
    window_days: int = 7
    total: int = 0
    positive: int = 0          # rating=1
    negative: int = 0          # rating=-1
    neutral: int = 0           # rating=0
    negative_rate: float = 0.0  # negative / total
    by_kb: List[Dict[str, Any]] = Field(default_factory=list,
        description="[{kb_id, kb_name, total, negative, negative_rate}]")
    by_reason: List[Dict[str, Any]] = Field(default_factory=list,
        description="[{rating_reason, count}]，仅统计 rating=-1")
    by_source: List[Dict[str, Any]] = Field(default_factory=list,
        description="[{source, total, negative}]")
