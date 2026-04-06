# -*- coding: utf-8 -*-
"""backend/config.py — Pydantic Settings v2（本地直跑 + Docker 容器互连双模式）

本地直跑：DB_HOST=localhost / REDIS_HOST=localhost（.env 默认值）
Docker：  DB_HOST=mysql      / REDIS_HOST=redis（docker-compose 通过 environment 注入）
DATABASE_URL / REDIS_URL 若在 .env 中显式设置则直接使用，否则由各组件字段自动构造。
"""
import secrets
from pathlib import Path
from typing import List, Optional
import json

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENV: str = "development"

    # ── MySQL 组件（优先用组件构造 URL，适配 docker 服务名）────────────
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "lnys_user"
    DB_PASSWORD: str = "lnys_password"
    DB_NAME: str = "lnys_db"
    DATABASE_URL: Optional[str] = None
    ASYNC_DATABASE_URL: Optional[str] = None
    # 连接池调优（每个 Worker 独立池）
    DB_POOL_SIZE: int = 30
    DB_MAX_OVERFLOW: int = 70
    DB_POOL_RECYCLE: int = 1800
    # 多 Worker 配置
    WORKERS: int = 0  # 0 = auto (CPU * 2 + 1)

    # ── Redis 组件 ─────────────────────────────────────────────────────
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0
    REDIS_URL: Optional[str] = None

    # PostgreSQL （仅用于 LangGraph checkpoint）
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "lnys_user"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = "lnys_checkpoint"
    POSTGRES_CHECKPOINT_URL: Optional[str] = None

    # ── CORS（保留字符串形式，避免 pydantic-settings v2 提前 JSON 解析失败）──
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # ── 模型路径 ───────────────────────────────────────────────────────
    MODELS_ROOT: Path = Path(__file__).parent.parent / "models"
    ART_CUSTOMER: Optional[Path] = None
    ART_FORECAST: Optional[Path] = None
    ART_FRAUD: Optional[Path] = None
    ART_NLP: Optional[Path] = None

    # Artifact 本地存储路径
    ARTIFACT_STORE_ROOT: Path = Path(__file__).parent.parent / "artifact_store"

    # JWT 认证 / 安全
    # 默认随机生成，每次重启后旧 Token 失效；生产环境必须通过环境变量固定
    SECRET_KEY: str = secrets.token_urlsafe(32)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # LLM 接入（兼容 DeepSeek / Qwen / OpenAI）
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    LLM_MODEL_NAME: str = "qwen3.5-plus-2026-02-15"

    # 多模型角色路由 (留空则 fallback 到 LLM_MODEL_NAME)
    LLM_MODEL_ROUTING: str = ""        # 意图分类/路由 (轻量快速)
    LLM_MODEL_COMPACT: str = ""        # 上下文压缩 (最便宜)
    LLM_MODEL_REVIEW: str = ""         # 输出审查 (强推理)
    LLM_MODEL_EXPLORATION: str = ""    # 数据探索 (快速)

    # Embedding + 向量知识库
    BGE_MODEL_NAME: str = str(Path(__file__).parent.parent / "models" / "bge-small-zh-v1.5")
    CHROMA_PERSIST_DIR: str = str(Path(__file__).parent.parent / "chroma_data")
    SENTIMENT_KB_ENABLED: bool = True

    # 知识库中台 v2
    KB_UPLOAD_DIR: str = str(Path(__file__).parent.parent / "kb_uploads")
    KB_MAX_FILE_SIZE_MB: int = 50
    KB_MAX_BATCH_SIZE: int = 20
    KB_OCR_ENABLED: bool = True
    KB_OCR_TIMEOUT: int = 30
    KB_DEFAULT_CHUNK_MAX_TOKENS: int = 512
    KB_DEFAULT_CHUNK_OVERLAP: int = 64
    KB_QUALITY_MIN_SCORE: float = 0.3
    KB_PII_DETECTION_ENABLED: bool = True
    KB_PII_POLICY: str = "warn"  # warn / reject / mask
    KB_SEARCH_TIMEOUT: int = 5
    KB_BM25_CACHE_SIZE: int = 5
    KB_CONFIDENCE_HIGH: float = 0.72
    KB_CONFIDENCE_MEDIUM: float = 0.55
    KB_CONFIDENCE_LOW: float = 0.35
    KB_AMBIGUOUS_GAP: float = 0.08
    KB_DEGRADED_CONF_PENALTY: float = 0.15
    KB_RERANK_ENABLED: bool = False
    KB_RERANK_MODEL: str = "BAAI/bge-reranker-base"
    KB_RERANK_TOP_N: int = 5

    # §3.1 Grounding L1：强制引用 + 后验剥离
    KB_GROUNDING_ENFORCE_CITATIONS: bool = True
    KB_MIN_GROUNDED_RATIO: float = 0.8
    KB_GROUNDING_WARN_ON_LOW_RATIO: bool = True
    KB_GROUNDING_WARN_MSG: str = "\n\n> ⚠️ 上述答复中部分内容未在知识库中找到直接依据，建议你核对原文或换个问法重试。\n"

    # §3.2 Abstain 正确拒答机制
    KB_ABSTAIN_ENABLED: bool = True
    KB_ABSTAIN_FALLBACK_SUGGEST_COUNT: int = 3
    KB_ABSTAIN_MSG_NO_EVIDENCE: str = "现有资料未收录此信息，已为你推荐相关主题。"
    KB_ABSTAIN_MSG_LOW_CONFIDENCE: str = "未找到足够可靠的资料。以下是最接近的候选，仅供参考。"
    KB_ABSTAIN_MSG_AMBIGUOUS: str = "找到多个可能相关的内容，请选择你想了解的方向。"
    KB_ABSTAIN_MSG_DOMAIN_FORBIDDEN: str = "你无权访问此类资料，请联系管理员开通权限。"

    # LangSmith 可观测性
    LANGCHAIN_TRACING_V2: bool = False
    LANGCHAIN_API_KEY: str = ""
    LANGCHAIN_PROJECT: str = "lnys-agent-platform"

    # Mem0 （OpenClaw 专用，可选）
    MEM0_API_KEY: str = ""

    # ── 飞书集成 ─────────────────────────────────────────────────────
    FEISHU_APP_ID: str = ""
    FEISHU_APP_SECRET: str = ""
    FEISHU_ENABLED: bool = False
    COPILOT_PATROL_ENABLED: bool = False
    # 飞书群映射（JSON 格式，DB 不可用时的 fallback）
    # 例: {"ops_alert":"oc_xxx","procurement":"oc_yyy","biz_daily":"oc_zzz"}
    FEISHU_GROUP_MAPPING: str = ""

    # ── 注册授权码（员工注册时需要提供的企业授权码）────────────────────
    # 生产环境通过 .env 注入，公开仓库示例使用占位值
    REGISTER_AUTH_CODE: str = "CHANGE_ME_IN_ENV"

    # ── 后台 Workflow 弹性控制 ──────────────────────────────────────
    # 单个后台 workflow 总超时（秒）：防止 LLM/Workflow 无限挂起
    BG_WORKFLOW_TIMEOUT_SECONDS: int = 600
    # 启动自愈阈值（分钟）：runs 表里 pending/running 超过此阈值的记录
    # 会在应用启动时被标为 failed（覆盖 FastAPI BackgroundTasks 进程重启丢任务场景）
    # 阈值应大于 BG_WORKFLOW_TIMEOUT_SECONDS/60 以避免误杀正常超时中的任务
    BG_WORKFLOW_STALE_MINUTES: int = 15

    # ── 功能开关 ──────────────────────────────────────────────────────
    ENABLE_MOCK_DATA: bool = True
    # 开发后门开关：仅用于本地开发无 DB 时 admin/admin 快速登录
    # 与 ENV 解耦，生产环境强制禁止开启
    DEV_BACKDOOR_ENABLED: bool = False

    # ── R6 架构重构 feature flag ───────────────────────────────────────
    # R6-2: CopilotEngine / Skill / Stage 通过 AppContainer 取依赖
    #        关闭 → 保留旧的单例 import 路径（默认，向后兼容）
    #        打开 → lifespan 构造 container 并挂到 app.state.container，
    #              CopilotEngine 优先从 container 取依赖
    COPILOT_CONTAINER_ENABLED: bool = False
    # R6-1: engine.run() 拆成 Pipeline Stage（占位，后续 commit 开工）
    COPILOT_PIPELINE_V2: bool = False
    # R6-4: Prompt / Rule / Policy 统一注册中心（占位）
    PROMPT_STORE_ENABLED: bool = False
    # R6-5: PolicyAdjuster 自动调整策略模式
    #        shadow  → 只记录建议，不真改配置（默认）
    #        enforce → 按 verdict 自动落实 policy 变更
    POLICY_ENFORCE_MODE: str = "shadow"

    @model_validator(mode="after")
    def _build_derived(self) -> "Settings":
        if self.is_production and len(self.SECRET_KEY) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 characters in production! "
                "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
            )
        if self.is_production and self.DEV_BACKDOOR_ENABLED:
            raise ValueError(
                "DEV_BACKDOOR_ENABLED must be False in production! "
                "Development backdoor cannot be enabled in production environment."
            )

        if not self.DATABASE_URL:
            self.DATABASE_URL = (
                f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
                f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
                f"?charset=utf8mb4"
            )
        elif "charset" not in self.DATABASE_URL:
            sep = "&" if "?" in self.DATABASE_URL else "?"
            self.DATABASE_URL += f"{sep}charset=utf8mb4"

        # 异步 URL（asyncmy 驱动）
        if not self.ASYNC_DATABASE_URL:
            self.ASYNC_DATABASE_URL = (
                f"mysql+asyncmy://{self.DB_USER}:{self.DB_PASSWORD}"
                f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
                f"?charset=utf8mb4"
            )

        if not self.REDIS_URL:
            auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
            self.REDIS_URL = f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

        if not self.POSTGRES_CHECKPOINT_URL:
            pg_auth = (
                f"{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                if self.POSTGRES_PASSWORD
                else self.POSTGRES_USER
            )
            self.POSTGRES_CHECKPOINT_URL = (
                f"postgresql://{pg_auth}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )

        base = self.MODELS_ROOT / "artifacts"
        self.ART_CUSTOMER = self._resolve_latest(base / "customer")
        self.ART_FORECAST = self._resolve_latest(base / "forecast")
        self.ART_FRAUD = self._resolve_latest(base / "fraud")
        self.ART_NLP = self._resolve_latest(base / "nlp")
        return self

    @staticmethod
    def _resolve_latest(art_dir: Path) -> Path:
        """解析 artifact 目录：如果存在版本子目录 (vX.Y.Z) 则指向最新版本，否则返回原目录"""
        if not art_dir.exists():
            return art_dir
        versions = sorted(
            [d for d in art_dir.iterdir() if d.is_dir() and d.name.startswith("v")],
            key=lambda p: p.name,
            reverse=True,
        )
        if versions:
            return versions[0]
        return art_dir

    @property
    def allowed_origins(self) -> List[str]:
        v = self.ALLOWED_ORIGINS.strip()
        if v.startswith("["):
            return json.loads(v)
        return [o.strip() for o in v.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENV.lower() == "production"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()