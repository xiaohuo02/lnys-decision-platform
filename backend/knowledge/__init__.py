# -*- coding: utf-8 -*-
"""backend/knowledge — 统一知识库中台模块

核心概念：
  KnowledgeBase     → 知识库实例（enterprise_faq / sentiment_reviews / ...）
  KnowledgeDocument → 文档（PDF/Word/FAQ/评论等）
  KnowledgeChunk    → 分块（向量化最小单位）
  SearchEngine      → 统一检索引擎（向量 + BM25 + RRF + 降级链）
"""
