# -*- coding: utf-8 -*-
"""backend/models — SQLAlchemy ORM Model 定义

所有 Model 均继承自 backend.database.Base，与 init.sql DDL 一一对应。
按业务域分文件组织，此 __init__.py 统一导出。
"""
from backend.models.auth import User, Role, Permission, UserRole, RolePermission
from backend.models.business import (
    Sku, Store, Customer, Order,
    AnalysisResult, FraudRecord, ChatMessage, InventorySnapshot,
)
from backend.models.governance import (
    Run, RunStep, Artifact, Agent, AgentTool,
    Prompt, PromptRelease,
    Policy, Release, ReleaseItem, ReleaseRollback,
    ReviewCase, ReviewAction,
    AuditLog, ActionLedger,
    FaqDocument, MemoryRecord, MemoryFeedback,
)
from backend.models.evaluation import (
    EvalDataset, EvalCase, Evaluator, EvalExperiment, EvalResult, EvalOnlineSample,
)
from backend.knowledge.models import KBLibrary, KBDocument, KBChunk
from backend.models.copilot import (
    CopilotThread, CopilotMessage, CopilotActionLog,
    CopilotMemory, CopilotRule, CopilotSkillOverride,
    FeishuGroupMapping,
)

__all__ = [
    # auth
    "User", "Role", "Permission", "UserRole", "RolePermission",
    # business
    "Sku", "Store", "Customer", "Order",
    "AnalysisResult", "FraudRecord", "ChatMessage", "InventorySnapshot",
    # governance
    "Run", "RunStep", "Artifact", "Agent", "AgentTool",
    "Prompt", "PromptRelease",
    "Policy", "Release", "ReleaseItem", "ReleaseRollback",
    "ReviewCase", "ReviewAction",
    "AuditLog", "ActionLedger",
    "FaqDocument", "MemoryRecord", "MemoryFeedback",
    # evaluation
    "EvalDataset", "EvalCase", "Evaluator", "EvalExperiment", "EvalResult", "EvalOnlineSample",
    # knowledge v2
    "KBLibrary", "KBDocument", "KBChunk",
    # copilot
    "CopilotThread", "CopilotMessage", "CopilotActionLog",
    "CopilotMemory", "CopilotRule", "CopilotSkillOverride",
    "FeishuGroupMapping",
]
