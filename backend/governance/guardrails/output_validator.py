# -*- coding: utf-8 -*-
"""backend/governance/guardrails/output_validator.py — Agent 输出质量验证器

设计来源: CrewAI Task Output Guardrails + 本项目 v4.0 治理架构

功能:
  - 按规则集验证 Agent 输出
  - 规则类型: schema / range / length / custom / enum
  - 每个 Agent 注册自己的规则集
  - 返回 ValidationResult 包含所有违规详情

事件类型 (用于 Trace 记录):
  output_validated — 输出验证完成
  output_rejected — 输出验证失败

用法:
    result = await output_validator.validate(
        agent_name="InsightComposerAgent",
        output={"executive_summary": "...", "risk_highlights": "...", ...}
    )
    if not result.passed:
        logger.warning(f"Output validation failed: {result.violations}")
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

from loguru import logger
from pydantic import BaseModel, ConfigDict


# ── 规则定义 ──────────────────────────────────────────────────────

class RuleType(str, Enum):
    SCHEMA = "schema"      # 必要字段存在性检查
    RANGE = "range"        # 数值范围检查
    LENGTH = "length"      # 文本长度检查
    ENUM = "enum"          # 枚举值检查
    CUSTOM = "custom"      # 自定义函数检查


class ValidationRule(BaseModel):
    """单条验证规则"""
    rule_type: RuleType
    field: str                                  # 要检查的字段路径 (支持 . 分隔嵌套)
    description: str = ""                       # 规则描述 (用于错误信息)
    # schema 类型参数
    required: bool = False                      # field 是否必须存在
    # range 类型参数
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    # length 类型参数
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    # enum 类型参数
    allowed_values: Optional[List[str]] = None
    # custom 类型参数 (不在 Pydantic 中, 运行时注入)

    model_config = ConfigDict(arbitrary_types_allowed=True)


class Violation(BaseModel):
    """单条违规记录"""
    rule_type: str
    field: str
    message: str
    actual_value: Optional[str] = None


class ValidationResult(BaseModel):
    """验证结果"""
    passed: bool
    agent_name: str
    violations: List[Violation] = []
    checked_rules: int = 0


# ── 字段路径解析 ──────────────────────────────────────────────────

def _get_nested(data: dict, path: str) -> Any:
    """从 dict 中按 . 分隔路径取值，找不到返回 _MISSING sentinel"""
    parts = path.split(".")
    cur = data
    for p in parts:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return _MISSING
    return cur


class _MissingSentinel:
    """标记字段不存在"""
    def __repr__(self):
        return "<MISSING>"


_MISSING = _MissingSentinel()


# ── OutputValidator 实现 ──────────────────────────────────────────

class OutputValidator:
    """
    Agent 输出质量验证器。

    用法:
        validator = OutputValidator()
        validator.register("InsightComposerAgent", [
            ValidationRule(rule_type="schema", field="executive_summary", required=True),
            ValidationRule(rule_type="length", field="executive_summary", min_length=50, max_length=1000),
            ...
        ])
        result = await validator.validate("InsightComposerAgent", output_dict)
    """

    def __init__(self):
        self._rule_registry: Dict[str, List[ValidationRule]] = {}
        self._custom_checks: Dict[str, Dict[str, Callable]] = {}

    # ── 注册 ──────────────────────────────────────────────────

    def register(
        self,
        agent_name: str,
        rules: List[ValidationRule],
        custom_checks: Optional[Dict[str, Callable]] = None,
    ) -> None:
        """
        注册 Agent 的输出验证规则。

        Args:
            agent_name: Agent 名称
            rules: 验证规则列表
            custom_checks: 自定义检查函数 {field: callable(value) -> str|None}
                           返回 None 表示通过，返回字符串表示违规原因
        """
        self._rule_registry[agent_name] = rules
        if custom_checks:
            self._custom_checks[agent_name] = custom_checks
        logger.info(
            f"[OutputValidator] registered {agent_name}: "
            f"{len(rules)} rules, {len(custom_checks or {})} custom checks"
        )

    def get_registered_agents(self) -> List[str]:
        return list(self._rule_registry.keys())

    # ── 验证 ──────────────────────────────────────────────────

    async def validate(
        self,
        agent_name: str,
        output: Dict[str, Any],
    ) -> ValidationResult:
        """
        验证 Agent 输出。

        Args:
            agent_name: Agent 名称
            output: Agent 输出字典

        Returns:
            ValidationResult
        """
        rules = self._rule_registry.get(agent_name)
        if rules is None:
            logger.debug(f"[OutputValidator] no rules for {agent_name}, auto-pass")
            return ValidationResult(passed=True, agent_name=agent_name, checked_rules=0)

        violations: List[Violation] = []
        custom_checks = self._custom_checks.get(agent_name, {})

        for rule in rules:
            value = _get_nested(output, rule.field)
            v = self._check_rule(rule, value, custom_checks)
            if v is not None:
                violations.append(v)

        passed = len(violations) == 0
        result = ValidationResult(
            passed=passed,
            agent_name=agent_name,
            violations=violations,
            checked_rules=len(rules),
        )

        if not passed:
            logger.warning(
                f"[OutputValidator] {agent_name} FAILED: "
                f"{len(violations)}/{len(rules)} violations"
            )
            for v in violations:
                logger.warning(f"  [{v.rule_type}] {v.field}: {v.message}")
        else:
            logger.debug(
                f"[OutputValidator] {agent_name} PASSED: {len(rules)} rules checked"
            )

        return result

    # ── 规则检查引擎 ──────────────────────────────────────────

    def _check_rule(
        self,
        rule: ValidationRule,
        value: Any,
        custom_checks: Dict[str, Callable],
    ) -> Optional[Violation]:
        """检查单条规则，违规返回 Violation，通过返回 None"""

        if rule.rule_type == RuleType.SCHEMA:
            return self._check_schema(rule, value)
        elif rule.rule_type == RuleType.RANGE:
            return self._check_range(rule, value)
        elif rule.rule_type == RuleType.LENGTH:
            return self._check_length(rule, value)
        elif rule.rule_type == RuleType.ENUM:
            return self._check_enum(rule, value)
        elif rule.rule_type == RuleType.CUSTOM:
            return self._check_custom(rule, value, custom_checks)
        else:
            return None

    @staticmethod
    def _check_schema(rule: ValidationRule, value: Any) -> Optional[Violation]:
        if rule.required and isinstance(value, _MissingSentinel):
            return Violation(
                rule_type="schema",
                field=rule.field,
                message=f"必要字段 '{rule.field}' 缺失",
            )
        return None

    @staticmethod
    def _check_range(rule: ValidationRule, value: Any) -> Optional[Violation]:
        if isinstance(value, _MissingSentinel):
            return None  # 字段不存在时 range 不检查 (由 schema 规则负责)
        try:
            num = float(value)
        except (TypeError, ValueError):
            return Violation(
                rule_type="range",
                field=rule.field,
                message=f"字段 '{rule.field}' 不是数值类型",
                actual_value=str(value)[:100],
            )
        if rule.min_value is not None and num < rule.min_value:
            return Violation(
                rule_type="range",
                field=rule.field,
                message=f"值 {num} < 最小值 {rule.min_value}",
                actual_value=str(num),
            )
        if rule.max_value is not None and num > rule.max_value:
            return Violation(
                rule_type="range",
                field=rule.field,
                message=f"值 {num} > 最大值 {rule.max_value}",
                actual_value=str(num),
            )
        return None

    @staticmethod
    def _check_length(rule: ValidationRule, value: Any) -> Optional[Violation]:
        if isinstance(value, _MissingSentinel):
            return None
        if not isinstance(value, str):
            return Violation(
                rule_type="length",
                field=rule.field,
                message=f"字段 '{rule.field}' 不是字符串类型",
                actual_value=str(type(value)),
            )
        length = len(value)
        if rule.min_length is not None and length < rule.min_length:
            return Violation(
                rule_type="length",
                field=rule.field,
                message=f"长度 {length} < 最小长度 {rule.min_length}",
                actual_value=f"len={length}",
            )
        if rule.max_length is not None and length > rule.max_length:
            return Violation(
                rule_type="length",
                field=rule.field,
                message=f"长度 {length} > 最大长度 {rule.max_length}",
                actual_value=f"len={length}",
            )
        return None

    @staticmethod
    def _check_enum(rule: ValidationRule, value: Any) -> Optional[Violation]:
        if isinstance(value, _MissingSentinel):
            return None
        if rule.allowed_values and str(value) not in rule.allowed_values:
            return Violation(
                rule_type="enum",
                field=rule.field,
                message=f"值 '{value}' 不在允许范围 {rule.allowed_values}",
                actual_value=str(value)[:100],
            )
        return None

    @staticmethod
    def _check_custom(
        rule: ValidationRule,
        value: Any,
        custom_checks: Dict[str, Callable],
    ) -> Optional[Violation]:
        fn = custom_checks.get(rule.field)
        if fn is None:
            return None
        try:
            error_msg = fn(value)
            if error_msg:
                return Violation(
                    rule_type="custom",
                    field=rule.field,
                    message=error_msg,
                    actual_value=str(value)[:100] if not isinstance(value, _MissingSentinel) else "<MISSING>",
                )
        except Exception as e:
            return Violation(
                rule_type="custom",
                field=rule.field,
                message=f"自定义检查异常: {e}",
            )
        return None


# ── 全局单例 ──────────────────────────────────────────────────────

output_validator = OutputValidator()


# ── 预注册 Agent 规则 ─────────────────────────────────────────────

def _register_default_rules():
    """注册所有 Agent 的默认输出验证规则"""

    # SupervisorAgent: route_plan 必须包含 workflow 字段
    output_validator.register("SupervisorAgent", [
        ValidationRule(
            rule_type=RuleType.SCHEMA, field="route",
            required=True, description="路由结果必须存在",
        ),
        ValidationRule(
            rule_type=RuleType.RANGE, field="confidence",
            min_value=0.0, max_value=1.0,
            description="置信度必须在 0~1 范围",
        ),
        ValidationRule(
            rule_type=RuleType.ENUM, field="route",
            allowed_values=["business_overview", "risk_review", "openclaw", "ops_copilot"],
            description="路由必须是已知 workflow",
        ),
    ])

    # InsightComposerAgent: 三个核心字段
    output_validator.register("InsightComposerAgent", [
        ValidationRule(
            rule_type=RuleType.SCHEMA, field="executive_summary",
            required=True, description="经营摘要必须存在",
        ),
        ValidationRule(
            rule_type=RuleType.SCHEMA, field="risk_highlights",
            required=True, description="风险提示必须存在",
        ),
        ValidationRule(
            rule_type=RuleType.SCHEMA, field="action_plan",
            required=True, description="行动建议必须存在",
        ),
        ValidationRule(
            rule_type=RuleType.LENGTH, field="executive_summary",
            min_length=50, max_length=2000,
            description="经营摘要长度 50~2000 字",
        ),
        ValidationRule(
            rule_type=RuleType.LENGTH, field="risk_highlights",
            min_length=10, max_length=2000,
            description="风险提示长度 10~2000 字",
        ),
        ValidationRule(
            rule_type=RuleType.LENGTH, field="action_plan",
            min_length=10, max_length=2000,
            description="行动建议长度 10~2000 字",
        ),
    ])

    # OpenClawAgent: 回复文本非空 + confidence > 0
    output_validator.register("OpenClawAgent", [
        ValidationRule(
            rule_type=RuleType.SCHEMA, field="reply_text",
            required=True, description="回复文本必须存在",
        ),
        ValidationRule(
            rule_type=RuleType.LENGTH, field="reply_text",
            min_length=1, max_length=4000,
            description="回复文本长度 1~4000 字",
        ),
        ValidationRule(
            rule_type=RuleType.RANGE, field="confidence",
            min_value=0.0, max_value=1.0,
            description="置信度必须在 0~1 范围",
        ),
    ])

    # RiskReviewAgent: risk_level 枚举检查
    output_validator.register("RiskReviewAgent", [
        ValidationRule(
            rule_type=RuleType.SCHEMA, field="risk_level",
            required=True, description="风险等级必须存在",
        ),
        ValidationRule(
            rule_type=RuleType.ENUM, field="risk_level",
            allowed_values=["low", "medium", "high", "critical"],
            description="风险等级必须是 low/medium/high/critical",
        ),
        ValidationRule(
            rule_type=RuleType.SCHEMA, field="risk_score",
            required=True, description="风险分数必须存在",
        ),
        ValidationRule(
            rule_type=RuleType.RANGE, field="risk_score",
            min_value=0.0, max_value=1.0,
            description="风险分数必须在 0~1 范围",
        ),
    ])


_register_default_rules()
