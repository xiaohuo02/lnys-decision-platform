---
trigger: glob
globs: backend/**/*.py
---

# Backend Python 约束 (改 backend 下 .py 时自动生效)

## 必守

- **日志统一用 `from loguru import logger`** (项目 127+ 文件统一约定); 禁止 `print` / `import logging`
- 公共函数 / Service / Router / Repository 入口必须有完整 type hint (参数 + 返回值)
- 异常捕获必须明确: 禁止裸 `except:`; 至少 `except Exception as e:` + `logger.exception(...)` 或 `logger.error("...", exc_info=True)`
- 业务异常优先用 `backend/core/exceptions.py` 已定义的异常类, 不要随手 `raise Exception(...)`
- DB 访问:
  - 路由层用 `Depends(get_async_db)` (源自 `backend/database.py`)
  - 脚本层用 `async with` (异步) 或 `with get_db() as db:` (同步)
  - 不要在路由里直接构造 session
- 外部 HTTP / LLM / DeepSeek / Qwen 调用:
  - 用 `httpx` (同步 `httpx.Client`, 异步 `httpx.AsyncClient`); 不要 `requests`
  - 必须显式 `timeout=` (DeepSeek/Qwen 至少 60s, 普通接口 15s)
  - 失败要 retry + 日志 + 降级路径

## 禁止

- 硬编码 secret / API key / DSN / 数据库密码; 统一走 `backend.config.settings` (读 `.env` / `.env.docker` / 云端 `/opt/lnys/.env.prod`)
- service / router 里直接 `os.environ[...]`; 统一走 settings
- 跨层直接传 ORM 对象给前端; 经 pydantic schema 序列化
- 引入新的运行时依赖 (修改 `pyproject.toml`) 不和用户确认; 先说收益/成本/替代

## 强烈建议

- 函数 < 50 行; 超长拆 service / repository
- 早返回, 减少嵌套
- ML / 聚合 / 重计算优先走 cache (Redis 或内存); 写之前问一句缓存策略
- 涉及 LangGraph agent 时遵循 `backend/agents/base_workflow.py` 的契约 (state 输入输出明确)

## 测试

- 改 service / repository → 在 `backend/tests/test_*` 加 / 改测试; 至少正常路径 + 1 个边界
- pytest 配置见 `backend/pyproject.toml::[tool.pytest.ini_options]`, asyncio 模式自动
