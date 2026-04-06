# -*- coding: utf-8 -*-
"""backend/core/container.py — 应用依赖注入容器 (R6-2)

设计目标:
  1. 取代散点的 get_instance() / 模块级 singleton import 风格
  2. 提供测试时统一替换依赖的入口（替换一次 = 全链路生效）
  3. 双层 facade: CoreContainer (基础设施) + AgentContainer (领域服务)
  4. 不破坏向后兼容: 现有 module-level singleton 仍可用，Container 持有同一引用

架构:
  CoreContainer     — 跨领域共用重资源（redis/db/telemetry/model_selector/...）
    │  只读 dataclass，构造后不变更
    ▼
  AgentContainer    — Copilot/Agent 领域单例（skill_registry/...）
    │  依赖 core
    ▼
  AppContainer      — 门面，同时暴露 core 和 agent，挂到 app.state.container

延迟加载:
  - redis / db factory / telemetry / model_selector / input_guard / context_monitor
    → 启动时强制加载（必备）
  - embedding / vector_store
    → 按需调用 .get_embedding() / .get_vector_store()
    （避免启动时加载 ~200MB BGE 模型）

用法:

    # lifespan 启动时
    from backend.core.container import build_core_container, build_agent_container, AppContainer
    core = await build_core_container(settings=settings, redis=redis)
    agent = build_agent_container(core)
    app.state.container = AppContainer(core=core, agent=agent)

    # 业务代码使用
    container = request.app.state.container  # type: AppContainer
    engine = CopilotEngine(redis=container.redis, container=container.agent)
    async for event in engine.run(...): ...

    # 测试替换 telemetry（验收标准）
    import dataclasses
    fake_telem = FakeTelemetry()
    test_core = dataclasses.replace(real_core, telemetry=fake_telem)
    test_agent = build_agent_container(test_core)
    # 无需 patch("backend.core.telemetry.telemetry", ...)

Feature flag:
    settings.COPILOT_CONTAINER_ENABLED = False → Engine 走旧单例（默认）
    settings.COPILOT_CONTAINER_ENABLED = True  → Engine 从 container 取依赖
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from backend.config import Settings
    from backend.core.telemetry import Telemetry
    from backend.core.model_selector import ModelSelector
    from backend.core.token_counter import TokenCounter
    from backend.core.context_monitor import ContextMonitor
    from backend.core.embedding import EmbeddingService
    from backend.core.vector_store import VectorStoreManager
    from backend.core.prompt_store import PromptStore
    from backend.copilot.registry import SkillRegistry
    from backend.governance.guardrails.input_guard import InputGuard


# ── Core Container: 基础设施层 ─────────────────────────────────────
@dataclass(frozen=True)
class CoreContainer:
    """核心基础设施容器（不可变）。

    所有跨领域共用的"重"资源都通过此容器暴露。
    Skill / Stage / Service 只应依赖此层，避免对领域容器的循环依赖。

    Attributes:
        settings:                  应用配置
        redis:                     已初始化的 redis.asyncio.Redis
        db_session_factory:        同步 sessionmaker（非 Depends 场景使用）
        async_db_session_factory:  async_sessionmaker（Depends 注入）
        telemetry:                 Telemetry 单例（已 configure redis 归档）
        model_selector:            ModelSelector 单例（已 initialize）
        token_counter:             TokenCounter 无状态单例
        context_monitor:           ContextMonitor 单例（per-thread 状态内聚）
        input_guard:               InputGuard 单例（PII/注入/敏感词检查）
    """
    settings: "Settings"
    redis: Any
    db_session_factory: Any
    async_db_session_factory: Any
    telemetry: "Telemetry"
    model_selector: "ModelSelector"
    token_counter: "TokenCounter"
    context_monitor: "ContextMonitor"
    input_guard: "InputGuard"
    # R6-4: 统一 prompt 注册中心（可选，lifespan 未加载时为 None）
    prompt_store: "Optional[PromptStore]" = None

    # ── 延迟加载访问器（避免启动时加载 BGE 模型 + Chroma）────────
    def get_embedding(self) -> "EmbeddingService":
        """按需获取 Embedding 服务（首次调用时加载 BAAI/bge-small-zh-v1.5，约 200MB）。"""
        from backend.core.embedding import EmbeddingService
        return EmbeddingService.get_instance()

    def get_vector_store(self) -> "VectorStoreManager":
        """按需获取 VectorStore 管理器（首次调用时初始化 ChromaDB）。"""
        from backend.core.vector_store import VectorStoreManager
        return VectorStoreManager.get_instance()


# ── Agent Container: 领域服务层 ─────────────────────────────────────
@dataclass(frozen=True)
class AgentContainer:
    """Copilot / Agent 领域容器。

    依赖 CoreContainer, 只包含真正的单例级领域服务:
      - SkillRegistry（全局唯一，启动时 auto_discover）
      - （未来 R6-4）PromptStore
      - （未来 R6-1）PipelineBuilder

    不放 per-request 构造的组件（ContextManager / PermissionChecker），
    它们依赖请求级的 db session，放这里会引起生命周期混淆。
    """
    core: CoreContainer
    skill_registry: "SkillRegistry"


# ── App Container: 门面 ────────────────────────────────────────────
@dataclass(frozen=True)
class AppContainer:
    """应用级门面: 同时持有 core 和 agent。挂到 app.state.container。

    业务代码按需细粒度依赖 core 或 agent，避免整个容器被强引用。
    """
    core: CoreContainer
    agent: AgentContainer

    # ── 常用组件的便捷直访（避免 container.core.xxx 过长）──
    @property
    def settings(self) -> "Settings":
        return self.core.settings

    @property
    def redis(self) -> Any:
        return self.core.redis

    @property
    def telemetry(self) -> "Telemetry":
        return self.core.telemetry

    @property
    def skill_registry(self) -> "SkillRegistry":
        return self.agent.skill_registry


# ── 构造函数 ───────────────────────────────────────────────────────
async def build_core_container(settings: "Settings", redis: Any) -> CoreContainer:
    """构建 CoreContainer。

    Args:
        settings: Pydantic Settings 实例
        redis:    已初始化的 redis.asyncio.Redis 客户端

    Returns:
        CoreContainer 冻结实例

    副作用:
        - database.py 的同步 engine 被触发创建（若未创建）
        - ModelSelector.initialize() 被调用（读 settings）
        - Telemetry.configure(redis=...) 被调用（启用 Stream 归档）

    异常语义:
        - Redis configure 失败不抛异常，降级为仅内存 deque
        - 其它依赖失败会向上抛，由 lifespan 捕获并降级
    """
    # Sync session factory: 触发 lazy init
    import backend.database as _db_mod
    _db_mod._get_engine()
    sync_factory = _db_mod._SessionLocal

    # Async session factory
    async_factory = _db_mod.get_async_session_factory()

    # Telemetry: 复用 module 级单例，configure redis 归档
    from backend.core.telemetry import telemetry
    try:
        telemetry.configure(
            redis=redis,
            stream_key="lnys:telemetry",
            stream_maxlen=10000,
        )
    except Exception as e:
        logger.debug(f"[container] telemetry redis configure skipped: {e}")

    # ModelSelector: 复用 module 级单例并初始化
    from backend.core.model_selector import model_selector
    model_selector.initialize()

    # Context monitor / token counter / input guard → module 级单例
    from backend.core.context_monitor import context_monitor
    from backend.core.token_counter import token_counter
    from backend.governance.guardrails.input_guard import input_guard

    # R6-4: prompt_store module 单例（skill hints 等需要 SkillRegistry 就绪后在
    # build_agent_container 里补加载，此处只传引用）
    from backend.core.prompt_store import prompt_store

    core = CoreContainer(
        settings=settings,
        redis=redis,
        db_session_factory=sync_factory,
        async_db_session_factory=async_factory,
        telemetry=telemetry,
        model_selector=model_selector,
        token_counter=token_counter,
        context_monitor=context_monitor,
        input_guard=input_guard,
        prompt_store=prompt_store,
    )
    logger.info("[container] CoreContainer ready")
    return core


def build_agent_container(core: CoreContainer) -> AgentContainer:
    """构建 AgentContainer（同步，依赖 core）。

    Args:
        core: 已构造的 CoreContainer

    Returns:
        AgentContainer 冻结实例

    副作用:
        - SkillRegistry.instance() 被获取（此时应已完成 auto_discover）
        - 如果 core.prompt_store 存在，从 registry 加载 skill summarization_hint
    """
    from backend.copilot.registry import SkillRegistry
    registry = SkillRegistry.instance()

    # R6-4: 在 SkillRegistry 就绪后把 skill summarization_hint 注册到 prompt_store
    if core.prompt_store is not None:
        try:
            core.prompt_store.load_from_skill_registry(registry)
        except Exception as e:
            logger.warning(f"[container] prompt_store skill hints load failed: {e}")

    agent = AgentContainer(
        core=core,
        skill_registry=registry,
    )
    logger.info(f"[container] AgentContainer ready: {registry.count} skills")
    return agent


async def build_app_container(settings: "Settings", redis: Any) -> AppContainer:
    """一次性构建完整 AppContainer（core + agent）。

    推荐入口: lifespan 中直接调这个，省去两步。

    Args:
        settings: Pydantic Settings 实例
        redis:    已初始化的 redis 客户端

    Returns:
        AppContainer 冻结实例
    """
    core = await build_core_container(settings=settings, redis=redis)
    agent = build_agent_container(core)
    return AppContainer(core=core, agent=agent)
