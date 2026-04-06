# -*- coding: utf-8 -*-
"""backend/core/cancel_registry.py — 轻量级 workflow 取消令牌注册表

用法:
    # 取消端点
    cancel_registry.cancel(run_id)

    # 后台任务中周期性检查
    if cancel_registry.is_cancelled(run_id):
        raise CancelledError(f"run {run_id} cancelled")

    # 任务结束后清理
    cancel_registry.remove(run_id)
"""
from __future__ import annotations

import threading
from typing import Set


class CancelRegistry:
    def __init__(self) -> None:
        self._cancelled: Set[str] = set()
        self._lock = threading.Lock()

    def cancel(self, run_id: str) -> None:
        with self._lock:
            self._cancelled.add(run_id)

    def is_cancelled(self, run_id: str) -> bool:
        with self._lock:
            return run_id in self._cancelled

    def remove(self, run_id: str) -> None:
        with self._lock:
            self._cancelled.discard(run_id)


cancel_registry = CancelRegistry()
