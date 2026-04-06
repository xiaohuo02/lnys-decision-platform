# -*- coding: utf-8 -*-
"""backend/core/logging.py — 统一日志配置（loguru）"""
import sys
from pathlib import Path
from loguru import logger

from backend.config import settings


def _json_serializer(message) -> str:
    """Loguru serialize sink — 输出结构化 JSON（生产环境用）"""
    import json as _json
    record = message.record
    log_entry = {
        "timestamp": record["time"].isoformat(),
        "level": record["level"].name,
        "logger": record["name"],
        "function": record["function"],
        "line": record["line"],
        "message": record["message"],
    }
    if record["exception"] is not None:
        log_entry["exception"] = str(record["exception"])
    return _json.dumps(log_entry, ensure_ascii=False) + "\n"


def configure_logging(level: str = "INFO") -> None:
    logger.remove()

    if settings.is_production:
        logger.add(
            sys.stderr,
            level=level,
            format="{message}",
            serialize=True,
            colorize=False,
        )
    else:
        logger.add(
            sys.stderr,
            level=level,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                "<level>{message}</level>"
            ),
            colorize=True,
        )

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    logger.add(
        log_dir / "app.log",
        level="DEBUG",
        rotation="100 MB",
        retention="30 days",
        compression="gz",
        enqueue=True,
        encoding="utf-8",
        serialize=settings.is_production,
    )
