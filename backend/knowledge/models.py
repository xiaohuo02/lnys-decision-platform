# -*- coding: utf-8 -*-
"""backend/knowledge/models.py — 知识库中台 ORM Model

三张核心表：
  kb_libraries  → 知识库实例
  kb_documents  → 文档（含原始文本 + 清洗文本 + 状态机）
  kb_chunks     → 分块（MySQL 侧记录，与 ChromaDB 双向映射）
"""
from sqlalchemy import (
    Column, String, Text, Integer, BigInteger, Boolean,
    Float, JSON, Index, ForeignKey, func,
)
from sqlalchemy.dialects.mysql import DATETIME as MySQLDateTime, LONGTEXT
from sqlalchemy.orm import relationship

from backend.database import Base


# ── kb_libraries：知识库实例 ───────────────────────────────────────

class KBLibrary(Base):
    """知识库实例。每个库对应一个 ChromaDB collection。"""
    __tablename__ = "kb_libraries"

    kb_id = Column(String(36), primary_key=True, comment="UUID")
    name = Column(String(200), nullable=False, unique=True, comment="知识库唯一标识名")
    display_name = Column(String(200), nullable=False, comment="显示名称")
    description = Column(Text, default=None)
    domain = Column(
        String(50), nullable=False, default="enterprise",
        comment="业务域: enterprise / sentiment / ops / general",
    )
    collection_name = Column(
        String(100), nullable=False, unique=True,
        comment="ChromaDB collection 名，如 kb_xxxxxxxx",
    )
    embedding_model = Column(String(200), nullable=False, default="bge-small-zh-v1.5")
    chunk_strategy = Column(
        String(50), nullable=False, default="recursive",
        comment="分块策略: recursive / fixed / none",
    )
    chunk_config = Column(
        JSON, default=None,
        comment='分块参数 {"max_tokens":512,"overlap":64}',
    )
    doc_count = Column(Integer, nullable=False, default=0, comment="文档总数(冗余)")
    chunk_count = Column(Integer, nullable=False, default=0, comment="分块总数(冗余)")
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(String(100), nullable=False)
    created_at = Column(MySQLDateTime(fsp=3), nullable=False, server_default=func.now())
    updated_at = Column(
        MySQLDateTime(fsp=3), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    documents = relationship("KBDocument", back_populates="library", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_kb_lib_domain", "domain"),
        Index("idx_kb_lib_active", "is_active"),
    )


# ── kb_documents：文档 ────────────────────────────────────────────

class KBDocument(Base):
    """文档实体。一个文档属于一个知识库，可被分成多个 chunk。"""
    __tablename__ = "kb_documents"

    document_id = Column(String(36), primary_key=True, comment="UUID")
    kb_id = Column(
        String(36), ForeignKey("kb_libraries.kb_id", ondelete="CASCADE"),
        nullable=False,
    )
    title = Column(String(500), nullable=False)
    source_type = Column(
        String(50), nullable=False, default="faq_manual",
        comment="faq_manual / file_upload / agent_auto / api_import",
    )
    source_uri = Column(String(500), default=None, comment="文件路径 / API来源URL")
    file_name = Column(String(300), default=None)
    file_type = Column(String(50), default=None, comment="pdf / docx / xlsx / csv / txt / image")
    file_size = Column(BigInteger, default=None, comment="文件字节数")
    file_hash = Column(String(64), default=None, comment="SHA-256 去重")

    content_raw = Column(LONGTEXT, default=None, comment="原始提取文本")
    content_clean = Column(LONGTEXT, default=None, comment="清洗后文本")

    status = Column(
        String(30), nullable=False, default="pending",
        comment="pending / processing / ready / failed / disabled",
    )
    version = Column(Integer, nullable=False, default=1, comment="重处理时递增")
    quality_score = Column(Float, default=None, comment="质量评分 0~1")
    chunk_count = Column(Integer, nullable=False, default=0, comment="分块数(冗余)")
    error_msg = Column(Text, default=None, comment="处理失败原因")
    created_by = Column(String(100), nullable=False, default="system")
    created_at = Column(MySQLDateTime(fsp=3), nullable=False, server_default=func.now())
    updated_at = Column(
        MySQLDateTime(fsp=3), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    library = relationship("KBLibrary", back_populates="documents")
    chunks = relationship("KBChunk", back_populates="document", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_kb_doc_kb", "kb_id"),
        Index("idx_kb_doc_status", "status"),
        Index("idx_kb_doc_hash", "file_hash"),
        Index("idx_kb_doc_source", "source_type"),
    )


# ── kb_chunks：分块 ───────────────────────────────────────────────

class KBChunk(Base):
    """分块实体。与 ChromaDB 中的 vector 一一对应。"""
    __tablename__ = "kb_chunks"

    chunk_id = Column(String(36), primary_key=True, comment="UUID")
    document_id = Column(
        String(36), ForeignKey("kb_documents.document_id", ondelete="CASCADE"),
        nullable=False,
    )
    kb_id = Column(
        String(36), ForeignKey("kb_libraries.kb_id", ondelete="CASCADE"),
        nullable=False, comment="冗余FK，加速按库查询",
    )
    chunk_index = Column(Integer, nullable=False, comment="块在文档中的顺序")
    content = Column(LONGTEXT, nullable=False, comment="块文本")
    token_count = Column(Integer, default=None)
    char_count = Column(Integer, default=None)

    heading_path = Column(String(500), default=None, comment='标题层级路径，如 "退款政策 > 七天无理由"')
    chunk_type = Column(
        String(30), nullable=False, default="paragraph",
        comment="paragraph / table / list / code / ocr",
    )
    metadata_extra = Column(JSON, default=None, comment="扩展元数据")
    chromadb_id = Column(String(200), default=None, comment="ChromaDB 中的向量 ID")
    embedding_status = Column(
        String(20), nullable=False, default="pending",
        comment="pending / done / failed",
    )
    created_at = Column(MySQLDateTime(fsp=3), nullable=False, server_default=func.now())

    document = relationship("KBDocument", back_populates="chunks")

    __table_args__ = (
        Index("idx_kb_chunk_doc", "document_id"),
        Index("idx_kb_chunk_kb", "kb_id"),
        Index("idx_kb_chunk_embed", "embedding_status"),
    )
