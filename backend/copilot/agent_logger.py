# -*- coding: utf-8 -*-
"""backend/copilot/agent_logger.py — 双智能体专用日志系统

为运维助手(ops)和运营助手(biz)提供独立日志通道，
支持结构化日志、skill 调用追踪、性能指标记录。
日志同时输出到控制台和独立文件。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

from backend.config import settings

# ── 日志目录 ──
_LOG_DIR = Path("logs") / "copilot"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

# ── 独立日志实例 ──
# 运维助手日志
ops_logger = logger.bind(agent="ops_copilot")
# 运营助手日志
biz_logger = logger.bind(agent="biz_copilot")
# 巡检日志
patrol_logger = logger.bind(agent="patrol")
# 飞书桥接日志
feishu_logger = logger.bind(agent="feishu")


def configure_copilot_logging() -> None:
    """配置 Copilot 专用日志输出

    调用时机：在 FastAPI lifespan 中，configure_logging() 之后调用。
    生成独立日志文件：
      - logs/copilot/ops_copilot.log     运维助手全量日志
      - logs/copilot/biz_copilot.log     运营助手全量日志
      - logs/copilot/patrol.log          主动巡检日志
      - logs/copilot/feishu.log          飞书桥接日志
      - logs/copilot/actions.log         操作审计日志（所有 Action 执行记录）
    """
    log_config = {
        "rotation": "50 MB",
        "retention": "60 days",
        "compression": "gz",
        "enqueue": True,
        "encoding": "utf-8",
        "serialize": settings.is_production,
        "level": "DEBUG",
    }

    # 运维助手
    logger.add(
        _LOG_DIR / "ops_copilot.log",
        filter=lambda record: record["extra"].get("agent") == "ops_copilot",
        format=_log_format(),
        **log_config,
    )

    # 运营助手
    logger.add(
        _LOG_DIR / "biz_copilot.log",
        filter=lambda record: record["extra"].get("agent") == "biz_copilot",
        format=_log_format(),
        **log_config,
    )

    # 巡检
    logger.add(
        _LOG_DIR / "patrol.log",
        filter=lambda record: record["extra"].get("agent") == "patrol",
        format=_log_format(),
        **log_config,
    )

    # 飞书
    logger.add(
        _LOG_DIR / "feishu.log",
        filter=lambda record: record["extra"].get("agent") == "feishu",
        format=_log_format(),
        **log_config,
    )

    # Action 审计（所有 agent 共享）
    logger.add(
        _LOG_DIR / "actions.log",
        filter=lambda record: record["extra"].get("agent") == "action",
        format=_log_format(),
        **log_config,
    )


def _log_format() -> str:
    return (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{extra[agent]}</cyan> | "
        "<level>{message}</level>"
    )


def get_agent_logger(mode: str):
    """根据模式返回对应的 logger"""
    if mode == "ops":
        return ops_logger
    elif mode == "biz":
        return biz_logger
    elif mode == "patrol":
        return patrol_logger
    elif mode == "feishu":
        return feishu_logger
    return logger.bind(agent=mode)


class SkillCallTracer:
    """Skill 调用追踪器 — 记录每次 Skill 调用的完整生命周期"""

    def __init__(self, mode: str, skill_name: str, user_id: str, thread_id: str):
        self.mode = mode
        self.skill_name = skill_name
        self.user_id = user_id
        self.thread_id = thread_id
        self._log = get_agent_logger(mode)
        self._start_time: float = 0.0
        self._events: list = []

    def start(self) -> None:
        self._start_time = time.time()
        self._log.info(
            f"[skill:start] skill={self.skill_name} user={self.user_id} thread={self.thread_id}"
        )

    def log_event(self, event_type: str, detail: str = "") -> None:
        elapsed = int((time.time() - self._start_time) * 1000)
        self._events.append({"type": event_type, "elapsed_ms": elapsed, "detail": detail})
        self._log.debug(
            f"[skill:event] skill={self.skill_name} type={event_type} "
            f"elapsed={elapsed}ms {detail}"
        )

    def end(self, success: bool = True, error: Optional[str] = None) -> Dict[str, Any]:
        elapsed_ms = int((time.time() - self._start_time) * 1000)
        summary = {
            "skill": self.skill_name,
            "user_id": self.user_id,
            "thread_id": self.thread_id,
            "mode": self.mode,
            "elapsed_ms": elapsed_ms,
            "success": success,
            "event_count": len(self._events),
            "error": error,
        }
        if success:
            self._log.info(
                f"[skill:end] skill={self.skill_name} elapsed={elapsed_ms}ms events={len(self._events)}"
            )
        else:
            self._log.error(
                f"[skill:error] skill={self.skill_name} elapsed={elapsed_ms}ms error={error}"
            )
        return summary


class ActionAuditLogger:
    """Action 执行审计日志"""

    _log = logger.bind(agent="action")

    @classmethod
    def log_request(cls, action_type: str, user_id: str, target: str, payload: Any = None):
        cls._log.info(
            f"[action:request] type={action_type} user={user_id} target={target} "
            f"payload={payload}"
        )

    @classmethod
    def log_approved(cls, action_type: str, user_id: str, target: str):
        cls._log.info(f"[action:approved] type={action_type} user={user_id} target={target}")

    @classmethod
    def log_executed(cls, action_type: str, user_id: str, target: str, result: Any = None):
        cls._log.info(
            f"[action:executed] type={action_type} user={user_id} target={target} result={result}"
        )

    @classmethod
    def log_failed(cls, action_type: str, user_id: str, target: str, error: str):
        cls._log.error(
            f"[action:failed] type={action_type} user={user_id} target={target} error={error}"
        )

    @classmethod
    def log_rejected(cls, action_type: str, user_id: str, reason: str):
        cls._log.warning(
            f"[action:rejected] type={action_type} user={user_id} reason={reason}"
        )
