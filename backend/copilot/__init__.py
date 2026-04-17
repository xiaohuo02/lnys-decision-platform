# -*- coding: utf-8 -*-
"""backend/copilot — 统一 Copilot 智能体系统

包含：
- events:     SSE 事件类型定义
- base_skill: Skill 基类
- registry:   Skill 注册表
- context:    三层上下文管理器
- engine:     CopilotEngine 核心引擎
- permissions: RBAC 权限矩阵
- persistence: 对话持久化
- actions:    可执行 Action 系统
- logging:    智能体专用日志
"""
