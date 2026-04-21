# -*- coding: utf-8 -*-
"""backend/governance/policy_center/policy_engine.py — 3 层 Policy 执行引擎

设计来源: Claude Code 分层 Policy + 本项目 v4.0 治理架构

3 层检查流程:
  Layer 1: service_self_check → 调用 service.check_risk(output) (如果 service 实现了该方法)
  Layer 2: policy_rules_match → 从 policies 表 / 内存规则库匹配 active 规则
  Layer 3: hitl_trigger → 高风险结果 → 创建 review_case / 标记需审核

用法:
    result = await policy_engine.check(
        service_name="FraudScoringService",
        input_data={"run_id": "xxx"},
        output_data={"risk_score": 0.92, "risk_level": "high"},
        context={"run_id": "xxx", "agent_name": "RiskReviewAgent"},
    )
    if result.action == "block":
        raise PolicyBlockError(result.reason)
    elif result.action == "hitl":
        # 触发 HITL 审核
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from loguru import logger
from pydantic import BaseModel, Field


# ── 数据结构 ──────────────────────────────────────────────────────

class PolicyAction(str, Enum):
    ALLOW = "allow"        # 放行
    WARN = "warn"          # 放行但记录警告
    BLOCK = "block"        # 拦截
    HITL = "hitl"          # 需人工审核
    MODIFY = "modify"      # 自动修改输出


class PolicyRule(BaseModel):
    """单条 Policy 规则"""
    rule_id: str
    name: str
    service_pattern: str = "*"                  # 匹配的 service 名 (支持 * 通配)
    condition_field: str = ""                    # 检查的字段路径
    condition_op: str = "exists"                 # 操作: gt / lt / eq / ne / in / exists / regex
    condition_value: Any = None                  # 比较值
    action: PolicyAction = PolicyAction.WARN     # 触发动作
    priority: int = 0                            # 优先级 (越大越高)
    description: str = ""
    is_active: bool = True


class PolicyViolation(BaseModel):
    """单条违规"""
    layer: str                                   # layer_1 / layer_2 / layer_3
    rule_id: str
    rule_name: str
    action: PolicyAction
    reason: str
    field: str = ""
    actual_value: Optional[str] = None


class PolicyResult(BaseModel):
    """Policy 检查结果"""
    passed: bool                                 # 是否最终放行
    action: PolicyAction = PolicyAction.ALLOW     # 最严格的动作
    violations: List[PolicyViolation] = Field(default_factory=list)
    checked_layers: int = 0
    checked_rules: int = 0


# ── 字段路径工具 ──────────────────────────────────────────────────

def _get_nested(data: dict, path: str) -> Any:
    """按 . 分隔路径取值"""
    if not path:
        return data
    parts = path.split(".")
    cur = data
    for p in parts:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return _MISSING
    return cur


class _MissingSentinel:
    pass


_MISSING = _MissingSentinel()


# ── 条件评估 ─────────────────────────────────────────────────────

def _evaluate_condition(value: Any, op: str, expected: Any) -> bool:
    """评估单个条件"""
    if isinstance(value, _MissingSentinel):
        return op == "not_exists"

    try:
        if op == "exists":
            return True
        elif op == "not_exists":
            return False
        elif op == "gt":
            return float(value) > float(expected)
        elif op == "lt":
            return float(value) < float(expected)
        elif op == "gte":
            return float(value) >= float(expected)
        elif op == "lte":
            return float(value) <= float(expected)
        elif op == "eq":
            return str(value) == str(expected)
        elif op == "ne":
            return str(value) != str(expected)
        elif op == "in":
            return str(value) in (expected if isinstance(expected, (list, set)) else [expected])
        elif op == "contains":
            return str(expected) in str(value)
        elif op == "regex":
            import re
            return bool(re.search(str(expected), str(value)))
        else:
            return False
    except (TypeError, ValueError):
        return False


def _match_service(pattern: str, service_name: str) -> bool:
    """检查 service 名是否匹配规则 pattern"""
    if pattern == "*":
        return True
    if "*" in pattern:
        import fnmatch
        return fnmatch.fnmatch(service_name, pattern)
    return pattern == service_name


# ── PolicyEngine 实现 ─────────────────────────────────────────────

_ACTION_SEVERITY = {
    PolicyAction.ALLOW: 0,
    PolicyAction.WARN: 1,
    PolicyAction.MODIFY: 2,
    PolicyAction.HITL: 3,
    PolicyAction.BLOCK: 4,
}


class PolicyEngine:
    """
    3 层 Policy 执行引擎。

    Layer 1: Service 自检 (service.check_risk)
    Layer 2: 规则库匹配 (内存 + DB)
    Layer 3: HITL 触发器 (高风险自动升级)
    """

    def __init__(self):
        self._rules: List[PolicyRule] = []
        self._service_checkers: Dict[str, Callable] = {}
        self._hitl_thresholds: Dict[str, float] = {}

    # ── 注册 ──────────────────────────────────────────────────

    def register_rules(self, rules: List[PolicyRule]) -> None:
        """批量注册 Policy 规则"""
        self._rules.extend(rules)
        active = sum(1 for r in rules if r.is_active)
        logger.info(f"[PolicyEngine] registered {len(rules)} rules ({active} active)")

    def register_service_checker(
        self, service_name: str, checker: Callable
    ) -> None:
        """注册 service 自检函数: checker(output_data) -> Optional[str]"""
        self._service_checkers[service_name] = checker
        logger.debug(f"[PolicyEngine] registered checker for {service_name}")

    def register_hitl_threshold(
        self, service_name: str, field: str, threshold: float
    ) -> None:
        """注册 HITL 触发阈值"""
        self._hitl_thresholds[f"{service_name}.{field}"] = threshold
        logger.debug(
            f"[PolicyEngine] HITL threshold: {service_name}.{field} >= {threshold}"
        )

    # ── 主检查入口 ────────────────────────────────────────────

    async def check(
        self,
        service_name: str,
        input_data: Dict[str, Any],
        output_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> PolicyResult:
        """
        执行 3 层 Policy 检查。

        Returns:
            PolicyResult: 最终检查结果
        """
        ctx = context or {}
        violations: List[PolicyViolation] = []
        layers_checked = 0
        rules_checked = 0

        # ── Layer 1: Service 自检 ─────────────────────────────
        layers_checked += 1
        checker = self._service_checkers.get(service_name)
        if checker:
            try:
                risk_msg = checker(output_data)
                if risk_msg:
                    violations.append(PolicyViolation(
                        layer="layer_1",
                        rule_id=f"self_check_{service_name}",
                        rule_name=f"{service_name} 自检",
                        action=PolicyAction.WARN,
                        reason=risk_msg,
                    ))
                    rules_checked += 1
            except Exception as e:
                logger.warning(f"[PolicyEngine] Layer 1 checker error: {e}")

        # ── Layer 2: 规则库匹配 ──────────────────────────────
        layers_checked += 1
        active_rules = [
            r for r in self._rules
            if r.is_active and _match_service(r.service_pattern, service_name)
        ]
        active_rules.sort(key=lambda r: r.priority, reverse=True)

        for rule in active_rules:
            rules_checked += 1
            # 检查 output_data
            value = _get_nested(output_data, rule.condition_field)
            if _evaluate_condition(value, rule.condition_op, rule.condition_value):
                violations.append(PolicyViolation(
                    layer="layer_2",
                    rule_id=rule.rule_id,
                    rule_name=rule.name,
                    action=rule.action,
                    reason=rule.description or f"规则 {rule.name} 触发",
                    field=rule.condition_field,
                    actual_value=str(value)[:100] if not isinstance(value, _MissingSentinel) else "<MISSING>",
                ))

        # ── Layer 3: HITL 触发器 ─────────────────────────────
        layers_checked += 1
        for key, threshold in self._hitl_thresholds.items():
            svc, field = key.rsplit(".", 1)
            if svc != service_name:
                continue
            rules_checked += 1
            value = _get_nested(output_data, field)
            if not isinstance(value, _MissingSentinel):
                try:
                    if float(value) >= threshold:
                        violations.append(PolicyViolation(
                            layer="layer_3",
                            rule_id=f"hitl_{svc}_{field}",
                            rule_name=f"HITL 触发: {field} >= {threshold}",
                            action=PolicyAction.HITL,
                            reason=f"{field}={value} >= 阈值 {threshold}，需人工审核",
                            field=field,
                            actual_value=str(value),
                        ))
                except (TypeError, ValueError):
                    pass

        # ── 汇总结果 ─────────────────────────────────────────
        if violations:
            worst_action = max(
                (v.action for v in violations),
                key=lambda a: _ACTION_SEVERITY.get(a, 0),
            )
            passed = worst_action in (PolicyAction.ALLOW, PolicyAction.WARN)
        else:
            worst_action = PolicyAction.ALLOW
            passed = True

        result = PolicyResult(
            passed=passed,
            action=worst_action,
            violations=violations,
            checked_layers=layers_checked,
            checked_rules=rules_checked,
        )

        if not passed:
            logger.warning(
                f"[PolicyEngine] {service_name} → {worst_action.value}: "
                f"{len(violations)} violations"
            )
        else:
            logger.debug(
                f"[PolicyEngine] {service_name} → ALLOW "
                f"({rules_checked} rules, {len(violations)} warnings)"
            )

        return result


# ── 全局单例 ──────────────────────────────────────────────────────

policy_engine = PolicyEngine()


# ── 预注册默认规则 ────────────────────────────────────────────────

def _register_defaults():
    """注册平台默认 Policy 规则"""

    # 欺诈评分 HITL 阈值
    policy_engine.register_hitl_threshold(
        "FraudScoringService", "risk_score", 0.8
    )

    # 通用规则
    policy_engine.register_rules([
        PolicyRule(
            rule_id="pol_token_limit",
            name="单次 Token 上限",
            service_pattern="*",
            condition_field="token_usage.total_tokens",
            condition_op="gt",
            condition_value=85000,
            action=PolicyAction.BLOCK,
            priority=100,
            description="单次调用 token 超过 85k 上限",
        ),
        PolicyRule(
            rule_id="pol_fraud_high",
            name="欺诈高风险拦截",
            service_pattern="FraudScoringService",
            condition_field="risk_score",
            condition_op="gte",
            condition_value=0.95,
            action=PolicyAction.BLOCK,
            priority=90,
            description="风险分 >= 0.95 自动拦截交易",
        ),
        PolicyRule(
            rule_id="pol_fraud_medium",
            name="欺诈中风险警告",
            service_pattern="FraudScoringService",
            condition_field="risk_score",
            condition_op="gte",
            condition_value=0.5,
            action=PolicyAction.WARN,
            priority=50,
            description="风险分 >= 0.5 记录警告",
        ),
        PolicyRule(
            rule_id="pol_sentiment_alert",
            name="舆情负面占比预警",
            service_pattern="SentimentIntelligenceService",
            condition_field="negative_ratio",
            condition_op="gt",
            condition_value=0.3,
            action=PolicyAction.WARN,
            priority=40,
            description="负面评价占比 > 30% 触发预警",
        ),
        PolicyRule(
            rule_id="pol_empty_reply",
            name="空回复拦截",
            service_pattern="OpenClawAgent",
            condition_field="reply",
            condition_op="not_exists",
            action=PolicyAction.BLOCK,
            priority=80,
            description="客服回复不能为空",
        ),
    ])

    # FraudScoring 自检函数
    def _fraud_self_check(output: dict) -> Optional[str]:
        if output.get("degraded"):
            return "FraudScoringService 降级运行，评分可靠性下降"
        return None

    policy_engine.register_service_checker("FraudScoringService", _fraud_self_check)


_register_defaults()
