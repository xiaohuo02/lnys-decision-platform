# -*- coding: utf-8 -*-
"""backend/governance/hooks/hook_pipeline.py — Pre/Post Hook 管道

设计来源: Claude Code Pre/Post Hook + 本项目 v4.0 治理架构

功能:
  - 在 service 调用前后执行可扩展的 Hook 链
  - Pre Hook: 审计预记录、PII 脱敏检查、输入校验
  - Post Hook: 输出敏感信息检查、artifact 自动保存标记、高风险标记、审计记录

用法:
    # 注册自定义 hook
    hook_pipeline.register_pre_hook("audit_pre", audit_pre_hook_fn)
    hook_pipeline.register_post_hook("risk_flag", risk_flag_hook_fn)

    # 在 ServiceProtocol 中调用
    pre_result = await hook_pipeline.pre_service_call("CustomerIntelService", input_data, ctx)
    ...执行 service...
    post_result = await hook_pipeline.post_service_call("CustomerIntelService", output, ctx)
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Callable, Coroutine, Dict, List, Optional, Union

from loguru import logger
from pydantic import BaseModel, Field


# ── 数据结构 ──────────────────────────────────────────────────────

class HookAction(BaseModel):
    """单个 Hook 的执行结果"""
    hook_name: str
    passed: bool = True
    action: str = "allow"        # allow / warn / block / modify
    message: str = ""
    modifications: Dict[str, Any] = Field(default_factory=dict)


class HookResult(BaseModel):
    """Hook 管道整体结果"""
    passed: bool = True
    phase: str = "pre"           # pre / post
    actions: List[HookAction] = Field(default_factory=list)
    blocked_reason: Optional[str] = None
    modifications: Dict[str, Any] = Field(default_factory=dict)


# Hook 函数签名: async (service_name, data, context) -> HookAction
HookFn = Callable[
    [str, Dict[str, Any], Dict[str, Any]],
    Coroutine[Any, Any, HookAction],
]


# ── HookPipeline 实现 ────────────────────────────────────────────

class HookPipeline:
    """
    Pre/Post Hook 管道。

    Hook 按注册顺序依次执行，任一 Hook 返回 block 则中止。
    """

    def __init__(self):
        self._pre_hooks: List[tuple[str, HookFn]] = []
        self._post_hooks: List[tuple[str, HookFn]] = []

    # ── 注册 ──────────────────────────────────────────────────

    def register_pre_hook(self, name: str, fn: HookFn) -> None:
        self._pre_hooks.append((name, fn))
        logger.debug(f"[HookPipeline] registered pre hook: {name}")

    def register_post_hook(self, name: str, fn: HookFn) -> None:
        self._post_hooks.append((name, fn))
        logger.debug(f"[HookPipeline] registered post hook: {name}")

    # ── 执行 ──────────────────────────────────────────────────

    async def pre_service_call(
        self,
        service_name: str,
        input_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> HookResult:
        """执行所有 Pre Hook"""
        return await self._run_hooks(
            "pre", self._pre_hooks, service_name, input_data, context or {}
        )

    async def post_service_call(
        self,
        service_name: str,
        result_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> HookResult:
        """执行所有 Post Hook"""
        return await self._run_hooks(
            "post", self._post_hooks, service_name, result_data, context or {}
        )

    async def _run_hooks(
        self,
        phase: str,
        hooks: List[tuple[str, HookFn]],
        service_name: str,
        data: Dict[str, Any],
        context: Dict[str, Any],
    ) -> HookResult:
        actions: List[HookAction] = []
        all_modifications: Dict[str, Any] = {}

        for name, fn in hooks:
            try:
                action = await fn(service_name, data, context)
                actions.append(action)

                if action.modifications:
                    all_modifications.update(action.modifications)

                if action.action == "block":
                    logger.warning(
                        f"[HookPipeline] {phase} hook '{name}' BLOCKED "
                        f"service={service_name}: {action.message}"
                    )
                    return HookResult(
                        passed=False,
                        phase=phase,
                        actions=actions,
                        blocked_reason=f"[{name}] {action.message}",
                        modifications=all_modifications,
                    )
            except Exception as e:
                logger.warning(
                    f"[HookPipeline] {phase} hook '{name}' error (non-fatal): {e}"
                )
                actions.append(HookAction(
                    hook_name=name,
                    passed=True,
                    action="warn",
                    message=f"Hook 执行异常: {e}",
                ))

        logger.debug(
            f"[HookPipeline] {phase} hooks done: service={service_name} "
            f"hooks={len(actions)} all_passed=True"
        )

        return HookResult(
            passed=True,
            phase=phase,
            actions=actions,
            modifications=all_modifications,
        )


# ── 全局单例 ──────────────────────────────────────────────────────

hook_pipeline = HookPipeline()


# ── 预注册默认 Hook ──────────────────────────────────────────────

# PII 检测模式
_PII_PATTERNS = [
    (r"1[3-9]\d{9}", "手机号"),
    (r"\d{6}(18|19|20)\d{2}(0[1-9]|1[0-2])\d{6}", "身份证号"),
    (r"\d{16,19}", "银行卡号"),
]


async def _pre_audit_log(
    service_name: str, data: Dict[str, Any], context: Dict[str, Any]
) -> HookAction:
    """Pre Hook: 审计预记录"""
    run_id = context.get("run_id", "unknown")
    logger.debug(
        f"[Hook:audit_pre] service={service_name} run_id={run_id} "
        f"input_keys={list(data.keys())[:5]}"
    )
    return HookAction(hook_name="audit_pre", passed=True, action="allow")


async def _pre_pii_check(
    service_name: str, data: Dict[str, Any], context: Dict[str, Any]
) -> HookAction:
    """Pre Hook: PII 脱敏检查 (仅检测，不拦截)"""
    text_fields = []
    for k, v in data.items():
        if isinstance(v, str) and len(v) > 5:
            text_fields.append((k, v))

    pii_found = []
    for field_name, text in text_fields:
        for pattern, pii_type in _PII_PATTERNS:
            if re.search(pattern, text):
                pii_found.append(f"{field_name} 含 {pii_type}")

    if pii_found:
        return HookAction(
            hook_name="pii_check",
            passed=True,
            action="warn",
            message=f"PII 检测: {', '.join(pii_found)}",
        )
    return HookAction(hook_name="pii_check", passed=True, action="allow")


async def _post_sensitive_check(
    service_name: str, data: Dict[str, Any], context: Dict[str, Any]
) -> HookAction:
    """Post Hook: 输出敏感信息检查"""
    sensitive_keywords = ["api_key", "password", "secret", "token", "密码"]
    found = []
    for k, v in data.items():
        if isinstance(v, str):
            for kw in sensitive_keywords:
                if kw.lower() in v.lower():
                    found.append(f"{k} 含敏感词 '{kw}'")

    if found:
        return HookAction(
            hook_name="sensitive_check",
            passed=True,
            action="warn",
            message=f"输出含敏感信息: {', '.join(found[:3])}",
        )
    return HookAction(hook_name="sensitive_check", passed=True, action="allow")


async def _post_risk_flag(
    service_name: str, data: Dict[str, Any], context: Dict[str, Any]
) -> HookAction:
    """Post Hook: 高风险标记"""
    risk_score = data.get("risk_score") or data.get("fraud_score")
    if risk_score is not None:
        try:
            if float(risk_score) >= 0.8:
                return HookAction(
                    hook_name="risk_flag",
                    passed=True,
                    action="warn",
                    message=f"高风险标记: risk_score={risk_score}",
                    modifications={"_risk_flagged": True},
                )
        except (TypeError, ValueError):
            pass
    return HookAction(hook_name="risk_flag", passed=True, action="allow")


# 注册默认 hook
hook_pipeline.register_pre_hook("audit_pre", _pre_audit_log)
hook_pipeline.register_pre_hook("pii_check", _pre_pii_check)
hook_pipeline.register_post_hook("sensitive_check", _post_sensitive_check)
hook_pipeline.register_post_hook("risk_flag", _post_risk_flag)
