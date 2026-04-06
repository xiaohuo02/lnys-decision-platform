# ── base ───────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-mysql-client gcc g++ curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]"

COPY . .

# ── development ────────────────────────────────────────────────────────────
FROM base AS dev
ENV ENV=development \
    ENABLE_MOCK_DATA=true

EXPOSE 8000
# Liveness 探针: 只验证进程存活，不依赖 DB/Redis/PG/模型文件
# 业务依赖健康由 /api/health (综合) 或 /api/health/ready (Redis) 单独轮询
HEALTHCHECK --interval=15s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health/live || exit 1

CMD ["uvicorn", "backend.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--reload", "--log-level", "debug"]

# ── production ─────────────────────────────────────────────────────────────
FROM base AS prod
ENV ENV=production \
    ENABLE_MOCK_DATA=false

EXPOSE 8000
# Liveness 探针: 只验证进程存活；生产环境如需依赖就绪探针，请在编排层（K8s/Compose）配置 /api/health/ready
HEALTHCHECK --interval=30s --timeout=10s --retries=5 \
    CMD curl -f http://localhost:8000/api/health/live || exit 1

CMD ["gunicorn", "backend.main:app", "-c", "backend/gunicorn.conf.py"]
