# -*- coding: utf-8 -*-
"""backend/main.py — FastAPI 应用工厂

设计原则：
- create_app() 工厂函数，便于测试注入不同配置
- Agent 逐个独立加载，单个失败不阻断其他 Agent 或服务启动
- app.state.agent_registry 记录每个 Agent 的就绪状态，供 /api/health 查询
- 无注释开关：代码始终尝试加载，模型文件缺失时优雅记录并降级
"""
import asyncio
import importlib
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.encoders import ENCODERS_BY_TYPE
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

# ── 全局修复：naive datetime 一律视为 UTC 并带 +00:00 后缀 ────────
# MySQL DATETIME 列返回的 Python datetime 无时区信息，
# FastAPI 默认 isoformat() 不带后缀，前端 new Date() 按本地时间解析导致差 8 小时。
ENCODERS_BY_TYPE[datetime] = lambda v: (
    v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v
).isoformat()

from backend.config import settings
from backend.core.logging import configure_logging
from backend.core.exceptions import (
    AppError,
    app_error_handler,
    http_exception_handler,
    validation_error_handler,
    unhandled_exception_handler,
)
from backend.middleware.trace import TraceMiddleware
from backend.middleware.concurrency import ConcurrencyLimitMiddleware
from backend.middleware.timeout import RequestTimeoutMiddleware
from backend.middleware.cache_headers import CacheHeadersMiddleware
from backend.database import get_redis, close_redis, close_async_engine, SessionLocal

from backend.routers import (
    health,
    customers,
    forecast,
    fraud,
    sentiment,
    inventory,
    chat,
    association,
)
from backend.routers.internal import smoke as internal_smoke
from backend.routers.internal import services as internal_services
from backend.routers.external import analyze as external_analyze
from backend.routers.external import chat as external_chat
from backend.routers.external import workflow_sse as external_workflow_sse
from backend.routers.admin import reviews as admin_reviews
from backend.routers.admin import traces as admin_traces
from backend.routers.admin import dashboard as admin_dashboard
from backend.routers.admin import prompts as admin_prompts
from backend.routers.admin import policies as admin_policies
from backend.routers.admin import audit as admin_audit
from backend.routers.admin import knowledge as admin_knowledge
from backend.routers.admin import knowledge_v2 as admin_knowledge_v2
from backend.routers.admin import memory as admin_memory
from backend.routers.admin import auth as admin_auth
from backend.routers.admin import evals as admin_evals
from backend.routers.admin import releases as admin_releases
from backend.routers.admin import ops_copilot as admin_ops_copilot
from backend.routers.admin import agents as admin_agents
from backend.routers.admin import team as admin_team
from backend.routers.admin import copilot_stream as admin_copilot_stream
from backend.routers.admin import copilot_config as admin_copilot_config
from backend.routers.admin import telemetry as admin_telemetry
from backend.routers.admin import eval_verdicts as admin_eval_verdicts
from backend.routers import copilot_biz
from backend.routers import business_kb
from backend.routers import report as report_router
from backend.routers import workflow as workflow_router
from backend.routers import dashboard as biz_dashboard

_AGENT_MANIFEST: dict[str, tuple[str, str]] = {
    "customer_agent": ("backend.agents.customer_agent", "CustomerAgent"),
    "forecast_agent": ("backend.agents.forecast_agent", "ForecastAgent"),
    "fraud_agent": ("backend.agents.fraud_agent", "FraudAgent"),
    "sentiment_agent": ("backend.agents.sentiment_agent", "SentimentAgent"),
    "inventory_agent": ("backend.agents.inventory_agent", "InventoryAgent"),
    "openclaw_agent": ("backend.agents.openclaw_agent", "OpenClawCustomerAgent"),
    "association_agent": ("backend.agents.association_agent", "AssociationAgent"),
}


async def _load_agents(app: FastAPI, redis) -> None:
    """逐个加载 Agent；单个失败只记录，不阻断其余 Agent 或服务启动"""
    registry: dict[str, str] = {}
    for name, (mod_path, cls_name) in _AGENT_MANIFEST.items():
        try:
            mod = importlib.import_module(mod_path)
            instance = getattr(mod, cls_name)(redis)
            setattr(app.state, name, instance)
            registry[name] = "ready"
            logger.info(f"[startup:agent] {name} ")
        except FileNotFoundError as exc:
            msg = f"not_loaded: ({exc.filename})"
            registry[name] = msg
            logger.warning(f"[startup:agent] {name} {msg}")
        except Exception as exc:
            msg = f"not_loaded: {type(exc).__name__}: {exc}"
            registry[name] = msg
            logger.warning(f"[startup:agent] {name} {msg}")

    app.state.agent_registry = registry
    ready = sum(1 for v in registry.values() if v == "ready")
    logger.info(f"[startup:agent] {ready}/{len(_AGENT_MANIFEST)} ")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging("DEBUG" if not settings.is_production else "INFO")
    logger.info(f"[startup] ENV={settings.ENV} mock_data={settings.ENABLE_MOCK_DATA}")

    logger.info("[startup] Redis...")
    redis = await get_redis()
    app.state.redis = redis

    # ── P0-SSE: 注入 redis 到 progress_manager ──
    # 让 ProgressChannel.emit() 真正发布到 Redis pubsub，
    # 同时让 workflow_sse 的 fallback 订阅路径可用（多 worker 部署必需）。
    try:
        from backend.core.progress_channel import progress_manager
        progress_manager.set_redis(redis)
    except Exception as e:
        logger.warning(f"[startup:sse] progress_manager redis inject failed (non-fatal): {e}")

    # ── R6-2: AppContainer 基础设施统一入口 ──
    # 失败时降级到老路径（单独初始化 ModelSelector / Telemetry），
    # 保证 container 不可用不影响应用启动
    app.state.container = None
    _core_container = None
    try:
        from backend.core.container import build_core_container
        # 加 15s timeout: build_core_container 内部会 telemetry.configure (Redis) +
        # model_selector.initialize (读 settings)；Redis 抖动时最多等 15s 后降级
        _core_container = await asyncio.wait_for(
            build_core_container(settings=settings, redis=redis),
            timeout=15.0,
        )
        # 向后兼容：app.state.telemetry / model_selector 仍指向同一对象
        app.state.telemetry = _core_container.telemetry
        app.state.model_selector = _core_container.model_selector
        logger.info("[startup:infra] CoreContainer ready (telemetry + model_selector)")
    except asyncio.TimeoutError:
        logger.warning("[startup:infra] CoreContainer init timed out after 15s, fallback to legacy singletons")
    except Exception as e:
        logger.warning(f"[startup:infra] CoreContainer init failed, fallback to legacy singletons: {e}")
        # Fallback: 单独初始化 ModelSelector + Telemetry（与历史行为一致）
        try:
            from backend.core.model_selector import model_selector
            model_selector.initialize()
            app.state.model_selector = model_selector
            logger.info("[startup:infra] ModelSelector initialized (fallback)")
        except Exception as e2:
            logger.warning(f"[startup:infra] ModelSelector init failed (non-fatal): {e2}")
        try:
            from backend.core.telemetry import telemetry
            try:
                telemetry.configure(redis=redis, stream_key="lnys:telemetry", stream_maxlen=10000)
            except Exception as _e:
                logger.debug(f"[startup:infra] Telemetry Redis configure skipped: {_e}")
            app.state.telemetry = telemetry
            logger.info("[startup:infra] Telemetry ready (fallback)")
        except Exception as e2:
            logger.warning(f"[startup:infra] Telemetry init failed (non-fatal): {e2}")

    logger.info("[startup] Agent...")
    await _load_agents(app, redis)

    try:
        from backend.agents.checkpoint import setup_checkpointer
        # 加 10s timeout: PG 不可达时避免 asyncpg 默认 60s+ 阻塞
        await asyncio.wait_for(setup_checkpointer(), timeout=10.0)
    except asyncio.TimeoutError:
        logger.warning("[startup] PostgreSQL checkpoint setup timed out after 10s (non-fatal)")
    except Exception as e:
        logger.warning(f"[startup] PostgreSQL checkpoint setup (non-fatal): {e}")

    # 
    try:
        from backend.copilot.agent_logger import configure_copilot_logging
        configure_copilot_logging()
        logger.info("[startup:copilot] ")
    except Exception as e:
        logger.warning(f"[startup:copilot] (non-fatal): {e}")

    try:
        from backend.copilot.registry import SkillRegistry
        registry = SkillRegistry.instance()
        registry.auto_discover()
        app.state.skill_registry = registry
        logger.info(f"[startup:copilot] Skill registry ready: {registry.count} skills")

        # ── R6-2: 构造 AgentContainer + AppContainer ──
        # 需要 CoreContainer 已经成功构造；core 失败时跳过，Engine 走旧路径
        if _core_container is not None:
            try:
                from backend.core.container import build_agent_container, AppContainer
                _agent_container = build_agent_container(_core_container)
                app.state.container = AppContainer(core=_core_container, agent=_agent_container)
                logger.info("[startup:copilot] AppContainer mounted to app.state.container")
            except Exception as e:
                logger.warning(f"[startup:copilot] AppContainer build failed (non-fatal): {e}")

        # ── R6-4: 加载 prompt_store 的 YAML + DB 规则 ──
        # skill hints 已在 build_agent_container 里加载；这里补 YAML 目录 + copilot_rules 表
        if _core_container is not None and _core_container.prompt_store is not None:
            from pathlib import Path as _Path
            ps = _core_container.prompt_store
            try:
                yaml_dir = _Path(__file__).parent / "governance" / "prompt_center"
                ps.load_from_yaml_dir(yaml_dir)
            except Exception as e:
                logger.warning(f"[startup:prompt_store] yaml load failed (non-fatal): {e}")
            try:
                db = SessionLocal()
                try:
                    ps.load_from_db(db)
                finally:
                    db.close()
            except Exception as e:
                logger.warning(f"[startup:prompt_store] db load failed (non-fatal): {e}")
            logger.info(f"[startup:prompt_store] summary={ps.summary()}")

        # ── R6-5: 配置 PeriodicEvaluator / PolicyAdjuster 持久化 + 真实 apply handler ──
        try:
            from backend.governance.eval_center.periodic_evaluator import periodic_evaluator
            from backend.governance.policy_center.policy_adjuster import policy_adjuster
            periodic_evaluator.configure(db_session_factory=SessionLocal)
            policy_adjuster.configure(db_session_factory=SessionLocal)
            # 仅在 enforce 模式下注册官方 apply handler，默认 shadow 保持 dry-run
            if settings.POLICY_ENFORCE_MODE.lower() == "enforce":
                from backend.governance.policy_center.policy_handlers import (
                    register_default_handlers,
                )
                register_default_handlers(policy_adjuster)
                logger.info("[startup:policy] enforce mode + default handlers registered")
            else:
                logger.info("[startup:policy] shadow mode (no real apply handlers)")
        except Exception as e:
            logger.warning(f"[startup:policy] eval/policy configure failed (non-fatal): {e}")
    except Exception as e:
        logger.warning(f"[startup:copilot] Skill registry init failed (non-fatal): {e}")

    # ── S2 最小弹性：启动自愈 runs 表中卡死的 pending/running 记录 ──
    # BackgroundTasks 在 uvicorn reload / 容器重启时会丢失，但 runs 表里的状态行
    # 不会自动回到 failed，前端会一直看到 "running" 却永远拿不到结果。
    try:
        from backend.core.bg_run_tracker import reap_stale_runs
        await reap_stale_runs()
    except Exception as e:
        logger.warning(f"[startup:reap] (non-fatal): {e}")

    # ── Feishu & Patrol（单 leader 运行，避免多 worker 重复启动）──
    app.state.feishu = None
    app.state.patrol = None
    app.state.feishu_leader_lock = None
    _is_feishu_leader = False
    if settings.FEISHU_ENABLED and settings.FEISHU_APP_ID:
        from backend.core.leader_lock import LeaderLock
        leader_lock = LeaderLock(
            redis=redis, key="lnys:feishu_leader",
            ttl_seconds=60, renew_interval_seconds=20,
        )
        _is_feishu_leader = await leader_lock.acquire()

        if _is_feishu_leader:
            await leader_lock.start_renewal()
            app.state.feishu_leader_lock = leader_lock
            try:
                from backend.integrations.feishu.bridge import FeishuBridge
                feishu_bridge = FeishuBridge(
                    app_id=settings.FEISHU_APP_ID,
                    app_secret=settings.FEISHU_APP_SECRET,
                )
                feishu_bridge.start(event_loop=asyncio.get_event_loop())
                try:
                    db = SessionLocal()
                    feishu_bridge.load_group_registry(db)
                    db.close()
                except Exception as e:
                    logger.warning(f"[startup:feishu] group registry load failed: {e}")
                app.state.feishu = feishu_bridge
                logger.info("[startup:feishu] feishu bridge started (leader)")
            except Exception as e:
                logger.warning(f"[startup:feishu] feishu start failed (non-fatal): {e}")
        else:
            logger.info("[startup:feishu] skipped (another worker is leader or redis unavailable)")

    if settings.COPILOT_PATROL_ENABLED and _is_feishu_leader:
        try:
            from backend.copilot.engine import CopilotEngine
            from backend.integrations.feishu.scheduler import CopilotPatrolScheduler
            # R6-2: 当 AppContainer 构造成功时传入 agent container；Engine 内部
            # 自行判断 settings.COPILOT_CONTAINER_ENABLED 决定是否从 container 取依赖
            _app_container = getattr(app.state, "container", None)
            copilot_engine = CopilotEngine(
                redis=redis,
                container=(_app_container.agent if _app_container is not None else None),
            )
            patrol = CopilotPatrolScheduler(
                feishu_bridge=app.state.feishu,
                engine=copilot_engine,
            )
            patrol.start()
            app.state.patrol = patrol
            logger.info("[startup:patrol] patrol scheduler started (leader)")
        except Exception as e:
            logger.warning(f"[startup:patrol] patrol start failed (non-fatal): {e}")

    logger.info("[startup]  http://0.0.0.0:8000/docs")
    yield
    logger.info("[shutdown] closing async MySQL engine...")
    await close_async_engine()

    if app.state.patrol:
        try:
            app.state.patrol.shutdown()
        except Exception:
            pass

    # 释放 feishu leader 锁（含续期任务取消 + 原子 compare-and-delete）
    if getattr(app.state, "feishu_leader_lock", None) is not None:
        try:
            await app.state.feishu_leader_lock.release()
        except Exception as e:
            logger.warning(f"[shutdown:feishu] leader release failed: {e}")

    try:
        from backend.agents.checkpoint import close_pool
        await close_pool()
    except Exception:
        pass

    logger.info("[shutdown] closing Redis...")
    await close_redis()
    logger.info("[shutdown] stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="LNYS Agent Platform",
        version="4.0.0",
        description="LNYS Agent Platform API",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # 
    # TraceMiddleware 
    # TraceMiddleware 
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID", "X-Trace-ID"],
    )
    # / SSE 
    _STREAM_PREFIXES = (
        "/admin/copilot/stream",
        "/api/copilot/stream",
        "/api/v1/workflows/",    # SSE stream
        "/admin/ops-copilot/",   # LLM 
        "/api/v1/analyze",       # workflow LLM 
    )
    app.add_middleware(CacheHeadersMiddleware)
    app.add_middleware(RequestTimeoutMiddleware, timeout_seconds=30.0, skip_prefixes=_STREAM_PREFIXES)
    app.add_middleware(ConcurrencyLimitMiddleware, max_concurrent=500, skip_prefixes=_STREAM_PREFIXES)
    app.add_middleware(TraceMiddleware)

    from fastapi import HTTPException
    from fastapi.exceptions import RequestValidationError
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    app.include_router(health.router, prefix="/api")
    app.include_router(biz_dashboard.router, prefix="/api/dashboard", tags=["business"])
    app.include_router(customers.router, prefix="/api/customers", tags=["business"])
    app.include_router(forecast.router, prefix="/api/forecast", tags=["business"])
    app.include_router(fraud.router, prefix="/api/fraud", tags=["business"])
    app.include_router(sentiment.router, prefix="/api/sentiment", tags=["business"])
    app.include_router(inventory.router, prefix="/api/inventory", tags=["business"])
    app.include_router(chat.router, prefix="/api/chat", tags=["business"])
    app.include_router(association.router, prefix="/api/association", tags=["business"])
    app.include_router(report_router.router, prefix="/api/reports", tags=["business"])

    app.include_router(external_analyze.router, prefix="/api/v1", tags=["external-v1"])
    app.include_router(external_chat.router, prefix="/api/v1", tags=["external-v1"])
    app.include_router(external_workflow_sse.router, prefix="/api/v1", tags=["external-v1-sse"])
    app.include_router(workflow_router.router, prefix="/api/v1", tags=["workflow-mgmt"])

    app.include_router(health.router, prefix="/admin", tags=["admin-health"])
    app.include_router(admin_auth.router, prefix="/admin", tags=["admin-auth"])
    app.include_router(admin_dashboard.router, prefix="/admin", tags=["admin-dashboard"])
    app.include_router(admin_reviews.router, prefix="/admin", tags=["admin-reviews"])
    app.include_router(admin_traces.router, prefix="/admin", tags=["admin-traces"])
    app.include_router(admin_prompts.router, prefix="/admin", tags=["admin-prompts"])
    app.include_router(admin_policies.router, prefix="/admin", tags=["admin-policies"])
    app.include_router(admin_audit.router, prefix="/admin", tags=["admin-audit"])
    app.include_router(admin_knowledge.router, prefix="/admin", tags=["admin-knowledge"])
    app.include_router(admin_knowledge_v2.router, prefix="/admin", tags=["admin-knowledge-v2"])
    app.include_router(admin_memory.router, prefix="/admin", tags=["admin-memory"])
    app.include_router(admin_evals.router, prefix="/admin", tags=["admin-evals"])
    app.include_router(admin_releases.router, prefix="/admin", tags=["admin-releases"])
    app.include_router(admin_ops_copilot.router, prefix="/admin", tags=["admin-ops-copilot"])
    app.include_router(admin_agents.router, prefix="/admin", tags=["admin-agents"])
    app.include_router(admin_team.router, prefix="/admin", tags=["admin-team"])
    app.include_router(admin_copilot_stream.router, prefix="/admin", tags=["admin-copilot-stream"])
    app.include_router(admin_copilot_config.router, prefix="/admin", tags=["admin-copilot-config"])
    app.include_router(admin_telemetry.router, prefix="/admin", tags=["admin-telemetry"])
    # R6-5: Eval + Policy 只读路由
    app.include_router(admin_eval_verdicts.router, prefix="/admin", tags=["admin-eval-policy"])

    app.include_router(copilot_biz.router, prefix="/api", tags=["copilot-biz"])
    app.include_router(business_kb.router, prefix="/api", tags=["business-kb"])

    app.include_router(internal_smoke.router, prefix="/internal/smoke", tags=["internal"])
    app.include_router(internal_services.router, prefix="/internal", tags=["internal-services"])

    return app


app = create_app()