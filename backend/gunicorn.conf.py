# -*- coding: utf-8 -*-
"""gunicorn.conf.py — 生产级多 Worker 配置

用法：
  gunicorn backend.main:app -c backend/gunicorn.conf.py

设计依据：
  - 每 Worker 独享异步事件循环（uvicorn.workers.UvicornWorker）
  - 每 Worker 独享 AsyncEngine 连接池（pool_size=30, max_overflow=70）
  - workers = CPU*2+1（可通过 WORKERS 环境变量覆盖）
  - graceful_timeout 适当加长，避免 SSE 流被粗暴中断
"""
import multiprocessing
import os


# ── Worker 数量 ──
_env_workers = os.getenv("WORKERS", "0")
workers = int(_env_workers) if _env_workers.isdigit() and int(_env_workers) > 0 else (multiprocessing.cpu_count() * 2 + 1)

# ── Worker 类型：Uvicorn 异步 Worker ──
worker_class = "uvicorn.workers.UvicornWorker"

# ── 绑定地址 ──
bind = os.getenv("BIND", "0.0.0.0:8000")

# ── 超时 ──
timeout = 120               # Worker 无响应超时（秒）
graceful_timeout = 60       # 优雅关闭等待时间
keepalive = 5               # Keep-Alive 连接保持时间

# ── 连接 ──
worker_connections = 1000   # 每 Worker 最大并发连接数

# ── 预加载 ──
preload_app = False         # 关闭：每 Worker 各自初始化自己的引擎/连接池

# ── 日志 ──
accesslog = "-"             # stdout
errorlog = "-"              # stderr
loglevel = os.getenv("LOG_LEVEL", "info")

# ── 进程管理 ──
max_requests = 10000        # Worker 处理 N 个请求后重启（防内存泄漏）
max_requests_jitter = 1000  # 随机抖动，避免所有 Worker 同时重启

# ── 生命周期 Hook ──
def on_starting(server):
    """Master 进程启动前"""
    server.log.info(f"[gunicorn] starting with {workers} workers")


def post_worker_init(worker):
    """Worker fork 后"""
    worker.log.info(f"[gunicorn] worker {worker.pid} initialized")
