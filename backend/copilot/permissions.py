# -*- coding: utf-8 -*-
"""backend/copilot/permissions.py — Copilot RBAC 权限矩阵

三层权限模型：
  Layer 1: 角色 → 默认 Skill 集合（ROLE_SKILL_MATRIX）
  Layer 2: copilot_skill_overrides 表 → 管理员为特定用户启用/禁用 Skill
  Layer 3: 运行时 Action 级校验 → 每个 Action 有风险等级和角色要求
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional, Set

from loguru import logger
from sqlalchemy import select

from backend.models.copilot import CopilotSkillOverride


# ── 角色定义 ──
# DB `roles` 表 7 个真实角色 + 5 个 legacy 虚构角色（保留作兼容 fallback，不新分配）
class CopilotRole(str, Enum):
    # ── DB 真实角色（roles 表）──
    PLATFORM_ADMIN            = "platform_admin"             # 平台超级管理员
    OPS_ANALYST               = "ops_analyst"                # 运营分析师
    ML_ENGINEER               = "ml_engineer"                # 算法/模型开发工程师
    CUSTOMER_SERVICE_MANAGER  = "customer_service_manager"   # 客服主管
    RISK_REVIEWER             = "risk_reviewer"              # 风控审核员
    AUDITOR                   = "auditor"                    # 审计只读员
    EMPLOYEE                  = "employee"                   # 默认员工角色

    # ── Legacy 虚构角色（historical; 保留兼容旧硬编码，不作为新分配入口）──
    SUPER_ADMIN     = "super_admin"       # legacy, 等价 platform_admin
    BUSINESS_ADMIN  = "business_admin"    # legacy
    BIZ_OPERATOR    = "biz_operator"      # legacy
    BIZ_VIEWER      = "biz_viewer"        # legacy
    SYSTEM_PATROL   = "system_patrol"     # legacy 巡检系统角色


# ── 默认角色 → Skill 权限矩阵 ──
# 注意：飞书通知（feishu_notify / feishu_card）属于 ActionExecutor 管理的 Action，
# 不是 Skill，因此不出现在 ROLE_SKILL_MATRIX，而在 ACTION_ROLE_REQUIREMENTS 中控制。
# 全 15 skill 列表（平台管理员 + super_admin legacy 拥有全部权限）
_ALL_SKILLS: Set[str] = {
    "customer_intel_skill", "forecast_skill", "sentiment_skill",
    "inventory_skill", "fraud_skill", "association_skill",
    "kb_rag_skill", "trace_skill", "system_skill",
    "memory_skill", "ocr_skill",
    "eval_query_skill", "prompt_query_skill",
    "release_query_skill", "review_query_skill",
}

ROLE_SKILL_MATRIX: Dict[str, Set[str]] = {
    # ── DB 真实角色（按 docs/plan/R-RBAC-FIX.md §5.1 推荐分配）──
    "platform_admin": set(_ALL_SKILLS),                 # 全量 15
    "ops_analyst": {                                     # 13 —— 运营分析 + 治理只读
        "customer_intel_skill", "forecast_skill", "sentiment_skill",
        "inventory_skill", "fraud_skill",
        "kb_rag_skill", "trace_skill", "system_skill",
        "ocr_skill",
        "eval_query_skill", "prompt_query_skill",
        "release_query_skill", "review_query_skill",
    },
    "ml_engineer": {                                     # 9 —— AI 工程 + 模型相关业务
        "kb_rag_skill", "memory_skill",
        "eval_query_skill", "prompt_query_skill",
        "release_query_skill", "trace_skill",
        "forecast_skill", "fraud_skill", "sentiment_skill",
    },
    "customer_service_manager": {                        # 6 —— 客户 + 舆情 + 知识
        "customer_intel_skill", "sentiment_skill",
        "association_skill", "inventory_skill",
        "kb_rag_skill", "ocr_skill",
    },
    "risk_reviewer": {                                   # 4 —— 风控 + 审核
        "kb_rag_skill", "fraud_skill",
        "review_query_skill", "customer_intel_skill",
    },
    "auditor": {                                         # 5 —— 治理只读
        "kb_rag_skill", "review_query_skill",
        "prompt_query_skill", "release_query_skill",
        "trace_skill",
    },
    "employee": {                                        # 3 —— 最小只读
        "kb_rag_skill", "customer_intel_skill", "sentiment_skill",
    },

    # ── Legacy 虚构角色（保留兼容，等价映射到对应 DB 角色的 skill 集合）──
    "super_admin":     set(_ALL_SKILLS),                 # = platform_admin
    "business_admin": {                                   # 大致等价 ops_analyst 业务前台部分
        "customer_intel_skill", "forecast_skill", "sentiment_skill",
        "inventory_skill", "association_skill",
        "kb_rag_skill", "memory_skill",
    },
    "biz_operator": {                                     # 大致等价 customer_service_manager
        "customer_intel_skill", "forecast_skill", "sentiment_skill",
        "inventory_skill", "association_skill",
        "kb_rag_skill",
    },
    "biz_viewer": {                                       # 大致等价 employee
        "customer_intel_skill", "sentiment_skill",
        "kb_rag_skill",
    },
    "system_patrol": {                                    # 大致等价 ops_analyst 巡检子集
        "customer_intel_skill", "forecast_skill", "sentiment_skill",
        "inventory_skill", "fraud_skill",
        "trace_skill", "system_skill",
    },
}

# ── Mode 限制：哪些 Skill 在 biz 模式下不可用 ──
OPS_ONLY_SKILLS: FrozenSet[str] = frozenset({
    "trace_skill", "system_skill",
})


# ── Action 风险等级 ──
class ActionRisk(str, Enum):
    LOW    = "low"       # 用户确认即可
    MEDIUM = "medium"    # 需二次确认
    HIGH   = "high"      # 需管理员审批


ACTION_RISK_LEVELS: Dict[str, ActionRisk] = {
    "feishu_notify":     ActionRisk.LOW,
    "feishu_card":       ActionRisk.LOW,
    "export_report":     ActionRisk.LOW,
    "create_alert_rule": ActionRisk.MEDIUM,
    "schedule_task":     ActionRisk.HIGH,
}

# 能执行 Action 的最低角色（DB 真实角色 + legacy 虚构角色兼容并存）
_NOTIFY_ROLES: Set[str] = {
    # DB 真实角色：所有能用 Copilot 做业务决策的角色都可推送飞书通知
    "platform_admin", "ops_analyst", "ml_engineer",
    "customer_service_manager", "risk_reviewer",
    # legacy 虚构角色保留兼容
    "super_admin", "business_admin", "biz_operator",
}
_EXPORT_ROLES: Set[str] = {
    # DB 真实角色：所有能查询业务数据的角色都可导出报告（含 auditor）
    "platform_admin", "ops_analyst", "ml_engineer",
    "customer_service_manager", "risk_reviewer", "auditor",
    # legacy
    "super_admin", "business_admin", "biz_operator",
}
_ADMIN_ROLES: Set[str] = {
    # 高风险运维动作：仅限平台管理员
    "platform_admin",
    "super_admin",  # legacy
}

ACTION_ROLE_REQUIREMENTS: Dict[str, Set[str]] = {
    "feishu_notify":     _NOTIFY_ROLES,
    "feishu_card":       _NOTIFY_ROLES,
    "export_report":     _EXPORT_ROLES,
    "create_alert_rule": _ADMIN_ROLES,
    "schedule_task":     _ADMIN_ROLES,
}


class PermissionChecker:
    """Copilot 权限检查器

    使用方式:
        checker = PermissionChecker(db_session)
        allowed = await checker.get_allowed_skills(user_id, user_role, mode)
        can = checker.can_execute_action(user_role, "feishu_notify")
    """

    def __init__(self, db=None):
        self._db = db

    async def get_allowed_skills(
        self, user_id: str, user_role: str, mode: str
    ) -> Set[str]:
        """计算用户在指定模式下可用的 Skill 集合

        1. 从 ROLE_SKILL_MATRIX 获取角色默认权限
        2. 从 copilot_skill_overrides 表获取用户级覆盖
        3. 如果是 biz 模式，移除 OPS_ONLY_SKILLS
        """
        # Layer 1: 角色默认
        base_skills = ROLE_SKILL_MATRIX.get(user_role, set()).copy()

        # Layer 2: 用户级覆盖（DB）
        if self._db is not None:
            try:
                overrides = await self._load_overrides(user_id)
                for override in overrides:
                    skill = override["skill_name"]
                    if override["enabled"]:
                        base_skills.add(skill)
                    else:
                        base_skills.discard(skill)
            except Exception as e:
                logger.warning(f"[permissions] 加载用户覆盖失败: {e}")

        # Layer 3: 模式过滤
        if mode == "biz":
            base_skills -= OPS_ONLY_SKILLS

        return base_skills

    async def _load_overrides(self, user_id: str) -> List[Dict[str, Any]]:
        """从 copilot_skill_overrides 表加载用户级权限覆盖"""
        if self._db is None:
            return []
        try:
            stmt = (
                select(CopilotSkillOverride.skill_name, CopilotSkillOverride.enabled)
                .where(
                    CopilotSkillOverride.user_id == user_id,
                    CopilotSkillOverride.is_active == True,
                )
            )
            result = await self._db.execute(stmt)
            return [{"skill_name": r.skill_name, "enabled": bool(r.enabled)} for r in result.all()]
        except Exception as e:
            logger.debug(f"[permissions] overrides 表可能不存在: {e}")
            return []

    @staticmethod
    def can_execute_action(user_role: str, action_type: str) -> bool:
        """检查用户是否有权执行指定 Action"""
        allowed_roles = ACTION_ROLE_REQUIREMENTS.get(action_type, set())
        return user_role in allowed_roles

    @staticmethod
    def get_action_risk(action_type: str) -> ActionRisk:
        return ACTION_RISK_LEVELS.get(action_type, ActionRisk.HIGH)

    # 可直接放行（无需审批 / 二次确认）的管理员角色
    _BYPASS_APPROVAL_ROLES: FrozenSet[str] = frozenset({"super_admin", "platform_admin"})

    @staticmethod
    def needs_approval(user_role: str, action_type: str) -> bool:
        """是否需要审批或二次确认才能执行。

        规则:
          - HIGH    非管理员必须走审批流（ActionExecutor 保存 pending_approval）
          - MEDIUM  非管理员需要二次确认（前端应再次弹窗），同样返回 True
          - LOW     直接放行
          - 未知    默认按 HIGH 处理，返回 True
        """
        risk = ACTION_RISK_LEVELS.get(action_type, ActionRisk.HIGH)
        if user_role in PermissionChecker._BYPASS_APPROVAL_ROLES:
            return False
        return risk in (ActionRisk.HIGH, ActionRisk.MEDIUM)
