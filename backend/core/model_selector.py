# -*- coding: utf-8 -*-
"""backend/core/model_selector.py — 多角色模型路由选择器

设计来源: Aco ModelSelector + Forge 跨切面 6 (多模型策略)
核心思想: 按任务特征选模型，不是所有地方用同一个模型

角色定义:
    PRIMARY      — 主模型: 报告生成、复杂推理、综合回答
    ROUTING      — 路由模型: 意图分类、Supervisor 分发 (可用小/快模型)
    COMPACT      — 压缩模型: 上下文历史摘要 (可用最便宜的模型)
    REVIEW       — 审查模型: 输出质量校验、风险判断 (可用强模型)
    EXPLORATION  — 探索模型: 知识库搜索增强、数据探查 (快速便宜)
    EMBEDDING    — 向量模型: 文本嵌入 (独立模型)

用法:
    from backend.core.model_selector import model_selector, ModelRole

    model = model_selector.select(ModelRole.ROUTING)
    llm = model_selector.get_llm(ModelRole.ROUTING)
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from loguru import logger


class ModelRole(str, Enum):
    """模型角色枚举"""
    PRIMARY = "primary"
    ROUTING = "routing"
    COMPACT = "compact"
    REVIEW = "review"
    EXPLORATION = "exploration"
    EMBEDDING = "embedding"


class ModelSpec:
    """单个模型的规格描述"""
    __slots__ = ("model_name", "api_key", "base_url", "temperature", "max_tokens", "timeout")

    def __init__(
        self,
        model_name: str,
        api_key: str = "",
        base_url: str = "",
        temperature: float = 0.0,
        max_tokens: int = 4096,
        timeout: int = 60,
    ):
        self.model_name = model_name
        self.api_key = api_key
        self.base_url = base_url
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    def __repr__(self) -> str:
        return f"ModelSpec({self.model_name}, temp={self.temperature}, max={self.max_tokens})"


class ModelSelector:
    """多角色模型选择器。

    初始化时从 settings 读取多模型配置。
    未配置的角色自动 fallback 到 PRIMARY。

    线程安全: 只读映射 + 延迟创建 LLM 实例(带锁)。
    """

    def __init__(self):
        self._specs: Dict[ModelRole, ModelSpec] = {}
        self._llm_cache: Dict[ModelRole, Any] = {}
        self._initialized = False

    def initialize(self) -> None:
        """从 settings 加载模型配置。应在 app lifespan 中调用一次。"""
        from backend.config import settings

        api_key = settings.LLM_API_KEY
        base_url = settings.LLM_BASE_URL
        primary_model = settings.LLM_MODEL_NAME

        # PRIMARY — 主模型
        self._specs[ModelRole.PRIMARY] = ModelSpec(
            model_name=primary_model,
            api_key=api_key,
            base_url=base_url,
            temperature=0.3,
            max_tokens=8192,
            timeout=120,
        )

        # ROUTING — 路由/分类模型 (轻量、快速)
        routing_model = getattr(settings, "LLM_MODEL_ROUTING", "") or primary_model
        self._specs[ModelRole.ROUTING] = ModelSpec(
            model_name=routing_model,
            api_key=api_key,
            base_url=base_url,
            temperature=0.0,
            max_tokens=512,
            timeout=15,
        )

        # COMPACT — 压缩模型 (便宜)
        compact_model = getattr(settings, "LLM_MODEL_COMPACT", "") or primary_model
        self._specs[ModelRole.COMPACT] = ModelSpec(
            model_name=compact_model,
            api_key=api_key,
            base_url=base_url,
            temperature=0.0,
            max_tokens=2048,
            timeout=30,
        )

        # REVIEW — 审查模型 (强推理)
        review_model = getattr(settings, "LLM_MODEL_REVIEW", "") or primary_model
        self._specs[ModelRole.REVIEW] = ModelSpec(
            model_name=review_model,
            api_key=api_key,
            base_url=base_url,
            temperature=0.0,
            max_tokens=4096,
            timeout=60,
        )

        # EXPLORATION — 探索模型 (快速)
        exploration_model = getattr(settings, "LLM_MODEL_EXPLORATION", "") or primary_model
        self._specs[ModelRole.EXPLORATION] = ModelSpec(
            model_name=exploration_model,
            api_key=api_key,
            base_url=base_url,
            temperature=0.2,
            max_tokens=2048,
            timeout=30,
        )

        # EMBEDDING — 向量模型 (独立)
        self._specs[ModelRole.EMBEDDING] = ModelSpec(
            model_name=settings.BGE_MODEL_NAME,
        )

        self._initialized = True

        # 日志: 展示模型分配
        distinct_models = {r.value: s.model_name for r, s in self._specs.items() if r != ModelRole.EMBEDDING}
        logger.info(f"[ModelSelector] initialized: {distinct_models}")

    def select(self, role: ModelRole) -> str:
        """返回指定角色的模型名称。"""
        self._ensure_init()
        spec = self._specs.get(role)
        if not spec:
            spec = self._specs[ModelRole.PRIMARY]
        return spec.model_name

    def get_spec(self, role: ModelRole) -> ModelSpec:
        """返回指定角色的完整 ModelSpec。"""
        self._ensure_init()
        return self._specs.get(role, self._specs[ModelRole.PRIMARY])

    def get_llm(self, role: ModelRole) -> Any:
        """获取指定角色的 ChatOpenAI 实例（延迟创建，带缓存）。

        Returns:
            ChatOpenAI 实例，如果 langchain_openai 不可用则返回 None
        """
        self._ensure_init()
        if role in self._llm_cache:
            return self._llm_cache[role]

        spec = self.get_spec(role)
        try:
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(
                api_key=spec.api_key,
                base_url=spec.base_url,
                model=spec.model_name,
                temperature=spec.temperature,
                max_tokens=spec.max_tokens,
                timeout=spec.timeout,
            )
            self._llm_cache[role] = llm
            logger.debug(f"[ModelSelector] created LLM for {role.value}: {spec.model_name}")
            return llm
        except Exception as e:
            logger.warning(f"[ModelSelector] failed to create LLM for {role.value}: {e}")
            return None

    def get_model_info(self) -> Dict[str, Dict[str, Any]]:
        """返回所有角色的模型信息（供 /api/health 和前端展示）。"""
        self._ensure_init()
        return {
            role.value: {
                "model_name": spec.model_name,
                "temperature": spec.temperature,
                "max_tokens": spec.max_tokens,
                "timeout": spec.timeout,
            }
            for role, spec in self._specs.items()
        }

    def _ensure_init(self) -> None:
        if not self._initialized:
            self.initialize()


# ── 默认单例 ──────────────────────────────────────────────────────
model_selector = ModelSelector()
