# -*- coding: utf-8 -*-
"""backend/governance/policy_center/policy_handlers.py — R6-5 Apply Handler 官方实现

PolicyAdjuster 默认 enforce 是 dry-run（只标 applied=True）。
本文件提供若干**官方** handler 实现, 调用 `register_default_handlers(adjuster)`
可按需把它们注册进 PolicyAdjuster, 让对应 policy_key 真正落地。

设计原则:
  - 每个 handler 只修改单一类型的 global state, 不跨领域
  - 修改必须可回滚（rollback 时 change.new_value 会被替换成原 old_value 再调一次 handler）
  - handler 内异常自吞, 不向上抛（PolicyAdjuster 已有 log 记录）
  - 生产默认 **不** 调 register_default_handlers, 由运维确认后 opt-in

当前实现:
  - `handle_model_default_name`  改 ModelSelector PRIMARY 的 model_name
                                  影响所有后续 get_spec/get_llm 调用
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from backend.governance.policy_center.policy_adjuster import (
        PolicyAdjuster,
        PolicyChange,
    )


def handle_model_default_name(change: "PolicyChange") -> None:
    """R6-5 官方 handler: 切换 ModelSelector 的 PRIMARY model_name。

    影响:
      - 所有后续 model_selector.get_spec(PRIMARY) 返回新 model
      - model_selector.get_llm(PRIMARY) 会构造新 LLM 实例（缓存会被清除）

    注意:
      - 只修改 ModelSelector 的内存状态, 不写 settings / 不写 DB
      - 重启后恢复原默认值（由 settings.LLM_MODEL_NAME 决定）
      - rollback 时 handler 也被调用（change.new_value 此时是 old_value）
    """
    new_model = change.new_value
    if not new_model or not isinstance(new_model, str):
        logger.warning(
            f"[policy_handler] model.default_name: invalid new_value={new_model!r}, skip"
        )
        return

    try:
        from backend.core.model_selector import model_selector, ModelRole
        spec = model_selector._specs.get(ModelRole.PRIMARY)
        if spec is None:
            logger.warning("[policy_handler] ModelSelector not initialized, skip")
            return
        # ModelSpec 是 __slots__ 可写
        old = spec.model_name
        spec.model_name = new_model
        # 清缓存让下次 get_llm 用新 model 构造
        model_selector._llm_cache.pop(ModelRole.PRIMARY, None)
        logger.info(
            f"[policy_handler] ModelSelector PRIMARY model_name "
            f"{old!r} -> {new_model!r}"
        )
    except Exception as e:
        logger.error(f"[policy_handler] model.default_name handler error: {e}")


# ── 注册 helper ───────────────────────────────────────────────

def register_default_handlers(adjuster: "PolicyAdjuster") -> None:
    """把官方 handler 批量注册到 adjuster。

    当前 opt-in 行为:
      - lifespan 中若 settings.POLICY_ENFORCE_MODE=="enforce"
        → 调用此函数 + set_whitelist(["model.default_name", ...])
      - 默认 shadow 模式下不调用, enforce 分支也是 dry-run
    """
    adjuster.register_apply_handler(
        "model.default_name", handle_model_default_name,
    )
    logger.info("[policy_handler] registered default apply handlers: model.default_name")
