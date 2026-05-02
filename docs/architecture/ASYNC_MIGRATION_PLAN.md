# 异步并发架构改造方案（500+ 并发）

## 一、现状诊断

### 1.1 数据层
| 组件 | 现状 | 问题 |
|------|------|------|
| MySQL 驱动 | `pymysql`（同步） | 阻塞事件循环 |
| SQLAlchemy 引擎 | `create_engine`（同步） | 无法 await |
| Session | `sessionmaker` → 同步 `Session` | 所有 DB 操作阻塞 |
| 连接池 | `pool_size=10, max_overflow=20` | 500 并发不够 |
| Copilot 表 | 无 ORM Model，全用 `text()` 原生 SQL | 不一致、不安全、无类型 |
| Redis | `redis.asyncio` ✅ | 已是异步 |

### 1.2 受影响文件
- **34 个文件** 有 `db.execute` / `self._db.execute` 同步调用
- **25 个路由文件** 依赖 `Depends(get_db)` 同步 Session
- **5 个 Copilot 表** 无 ORM 模型：copilot_threads, copilot_messages, copilot_memory, copilot_rules, copilot_action_log

### 1.3 服务器层
- 无 gunicorn 多 worker 配置
- 无限流/限速中间件
- 无请求超时保护

## 二、目标架构

```
                    ┌─────────────┐
                    │   Nginx     │  连接限制 / 反向代理
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Gunicorn   │  master 进程
                    │  (管理者)    │
                    └──────┬──────┘
           ┌───────────────┼───────────────┐
    ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
    │  Uvicorn    │ │  Uvicorn    │ │  Uvicorn    │  N 个 Worker
    │  Worker 1   │ │  Worker 2   │ │  Worker N   │  (N = CPU*2+1)
    └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
           │               │               │
    ┌──────▼───────────────▼───────────────▼──────┐
    │           AsyncSession (per-request)          │
    │     create_async_engine + asyncmy 驱动        │
    │     pool_size=30, max_overflow=70             │
    │     (每个 Worker 独立连接池)                    │
    └──────┬───────────────────────────────┬──────┘
           │                               │
    ┌──────▼──────┐                 ┌──────▼──────┐
    │    MySQL    │                 │    Redis    │
    │  max_conn   │                 │   (异步)    │
    │  = 500+     │                 │             │
    └─────────────┘                 └─────────────┘
```

### 每 Worker 连接池数学
- **Workers**: 4（假设 2核 CPU × 2 + 1，取整）
- **每 Worker pool_size**: 30
- **每 Worker max_overflow**: 70
- **每 Worker 最大连接数**: 30 + 70 = 100
- **全部 Worker 最大连接数**: 4 × 100 = 400
- **MySQL max_connections**: 建议设 512（留余量给管理连接）
- **理论并发承载**: 400 个同时 DB 查询（远超 500 并发用户需求，因为不是每个请求都在等 DB）

## 三、改造清单

### Phase 1: 基础设施（必须先做） ✅ DONE
| # | 文件 | 改动 | 状态 |
|---|------|------|------|
| 1 | `pyproject.toml` | 添加 `asyncmy>=0.2.9` 依赖 | ✅ |
| 2 | `config.py` | 添加 `ASYNC_DATABASE_URL`、`DB_POOL_SIZE`、`DB_MAX_OVERFLOW`、`WORKERS` | ✅ |
| 3 | `database.py` | 新增 `create_async_engine` + `async_sessionmaker` + `get_async_db` 依赖 | ✅ |
| 4 | `models/copilot.py` | **新建** Copilot 5 张表的 ORM Model | ✅ |
| 5 | `models/__init__.py` | 导出新增 Copilot 模型 | ✅ |
| 6 | `main.py` | lifespan 初始化/关闭异步引擎；添加限流中间件 | ✅ |

### Phase 2: Copilot 高并发路径（最高优先级） ✅ DONE
| # | 文件 | 改动 | 状态 |
|---|------|------|------|
| 7 | `copilot/persistence.py` | 改用 AsyncSession + ORM Model，所有方法真异步 | ✅ |
| 8 | `copilot/context.py` | DB 查询改用 AsyncSession + ORM | ✅ |
| 9 | `routers/admin/copilot_stream.py` | `Depends(get_async_db)` 替换 `Depends(get_db)` | ✅ |
| 10 | `routers/copilot_biz.py` | 同上 | ✅ |
| 11 | `routers/admin/copilot_config.py` | 同上 | ✅ |
| 12 | `copilot/skills/memory_skill.py` | DB 调用改异步 | ✅ |

### Phase 3: 全量路由迁移（逐步推进） ✅ DONE
| # | 路由组 | 文件数 | 状态 |
|---|--------|--------|------|
| 13 | admin/* (traces, evals, team, prompts, policies, reviews, releases, knowledge, memory, audit, agents, dashboard, auth, ops_copilot) | 14 个 | ✅ |
| 14 | external/* (analyze, chat) + workflow + report | 4 个 | ✅ |
| 15 | internal/smoke (移除未使用 get_db 导入) | 1 个 | ✅ |

> **结果**: 路由层 0 处 `get_db` 残留。同步 `SessionLocal` 仅保留给后台任务和 Feishu 启动。

### Phase 4: 生产加固 ✅ DONE
| # | 改动 | 状态 |
|---|------|------|
| 17 | `gunicorn.conf.py` — 多 Worker、UvicornWorker、自动重启 | ✅ |
| 18 | `middleware/concurrency.py` — asyncio.Semaphore 全局并发上限 500 | ✅ |
| 19 | `middleware/timeout.py` — asyncio.wait_for 30s hard timeout | ✅ |
| 20 | `core/rate_limiter.py` — Redis 滑动窗口 per-IP/user QPS 限流 | ✅ |
| 21 | `db/scripts/tune_max_connections.sql` — MySQL max_connections=512 | ✅ |
| 22 | `Dockerfile` prod stage → `gunicorn backend.main:app -c gunicorn.conf.py` | ✅ |
| 23 | `main.py` — 注册 ConcurrencyLimitMiddleware + RequestTimeoutMiddleware | ✅ |

## 四、ORM Model 设计（Copilot 表）

```python
# models/copilot.py — 5 张 Copilot 核心表

class CopilotThread(Base):
    __tablename__ = "copilot_threads"
    id          = Column(String(36), primary_key=True)
    user_id     = Column(String(100), nullable=False, index=True)
    mode        = Column(String(10), nullable=False)
    title       = Column(String(256))
    summary     = Column(Text)
    page_origin = Column(String(200))
    tags        = Column(JSON)
    status      = Column(String(20), default="active")
    pinned      = Column(Boolean, default=False)
    messages    = relationship("CopilotMessage", back_populates="thread", ...)

class CopilotMessage(Base):
    __tablename__ = "copilot_messages"
    id          = Column(BigInteger, primary_key=True, autoincrement=True)
    thread_id   = Column(String(36), ForeignKey("copilot_threads.id"), index=True)
    role        = Column(String(20), nullable=False)
    content     = Column(Text)
    thinking    = Column(Text)
    skills_used = Column(JSON)
    artifacts   = Column(JSON)
    ...
    thread      = relationship("CopilotThread", back_populates="messages")

class CopilotMemory(Base):
    __tablename__ = "copilot_memory"
    ...

class CopilotRule(Base):
    __tablename__ = "copilot_rules"
    ...

class CopilotActionLog(Base):
    __tablename__ = "copilot_action_log"
    ...
```

## 五、AsyncSession 使用范式

```python
# 路由层
@router.post("/copilot/stream")
async def copilot_stream(
    body: ...,
    db: AsyncSession = Depends(get_async_db),  # 异步 Session
):
    persistence = CopilotPersistence(db=db)
    await persistence.save_message(...)  # 真异步!

# 持久化层
class CopilotPersistence:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def save_message(self, ...):
        msg = CopilotMessage(thread_id=thread_id, role=role, content=content)
        self._db.add(msg)
        await self._db.commit()       # ← 真 await
        await self._db.refresh(msg)   # ← 真 await
        return msg.id

    async def list_threads(self, user_id, ...):
        stmt = (
            select(CopilotThread)
            .where(CopilotThread.user_id == user_id)
            .order_by(CopilotThread.pinned.desc(), CopilotThread.updated_at.desc())
            .limit(limit).offset(offset)
        )
        result = await self._db.execute(stmt)  # ← 真 await
        return [_to_dict(t) for t in result.scalars().all()]
```

## 六、Gunicorn 配置

```python
# gunicorn.conf.py
import multiprocessing

bind = "0.0.0.0:8000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"
timeout = 120          # LLM 流式响应可能较长
keepalive = 5
max_requests = 2000    # Worker 自动重启，防内存泄漏
max_requests_jitter = 200
graceful_timeout = 30
accesslog = "-"
errorlog = "-"
loglevel = "info"
```

## 七、迁移策略

采用 **渐进式双轨并行**：
1. `get_db()` 同步依赖保留，已有路由继续工作
2. `get_async_db()` 异步依赖新增，Copilot 路由首先迁移
3. 两套引擎共存，共享同一个 MySQL 实例
4. 逐步把 Phase 3 路由迁移到异步
5. 全部迁移完成后，移除同步引擎

**回滚点**: 每个 Phase 独立可回滚，Phase 1 不改任何现有路由行为。
