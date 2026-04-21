# -*- coding: utf-8 -*-
"""backend/tests/fixtures/ops_copilot_mock_data.py

OpsCopilotAgent 测试用 mock 数据。
所有数据为静态构造，不依赖真实数据库、router、前端。
"""
from datetime import datetime

# ── trace / run ──────────────────────────────────────────────────

MOCK_SLOWEST_RUNS = [
    {
        "id": "run-001",
        "workflow_name": "fraud_detection_workflow",
        "status": "completed",
        "duration_sec": 320,
    },
    {
        "id": "run-002",
        "workflow_name": "customer_analysis_workflow",
        "status": "completed",
        "duration_sec": 215,
    },
]

MOCK_FAILED_RUNS = [
    {
        "id": "run-003",
        "workflow_name": "forecast_workflow",
        "error_message": "TimeoutError: LLM call exceeded 30s limit",
        "started_at": datetime(2026, 3, 31, 18, 0, 0),
    },
    {
        "id": "run-004",
        "workflow_name": "sentiment_workflow",
        "error_message": "ValueError: input data schema mismatch",
        "started_at": datetime(2026, 3, 31, 16, 30, 0),
    },
]

# ── eval / experiment ─────────────────────────────────────────────

MOCK_RECENT_EXPERIMENTS = [
    {
        "id": "exp-001",
        "name": "fraud_v2_eval",
        "status": "completed",
        "pass_rate": 0.92,
        "created_at": datetime(2026, 3, 30, 10, 0, 0),
    },
    {
        "id": "exp-002",
        "name": "sentiment_v3_eval",
        "status": "completed",
        "pass_rate": 0.61,
        "created_at": datetime(2026, 3, 29, 14, 0, 0),
    },
    {
        "id": "exp-003",
        "name": "forecast_v1_eval",
        "status": "running",
        "pass_rate": None,
        "created_at": datetime(2026, 3, 31, 9, 0, 0),
    },
]

MOCK_LOWEST_EXPERIMENT = {
    "id": "exp-002",
    "name": "sentiment_v3_eval",
    "pass_rate": 0.61,
    "created_at": datetime(2026, 3, 29, 14, 0, 0),
}

# ── prompt ────────────────────────────────────────────────────────

MOCK_PUBLISHED_PROMPTS = [
    {
        "name": "fraud_scoring_prompt",
        "agent_name": "FraudAgent",
        "version": 3,
        "updated_at": datetime(2026, 3, 31, 11, 0, 0),
    },
    {
        "name": "supervisor_system_prompt",
        "agent_name": "SupervisorAgent",
        "version": 2,
        "updated_at": datetime(2026, 3, 30, 9, 0, 0),
    },
]

MOCK_PROMPT_VERSIONS = [
    {"name": "fraud_scoring_prompt", "version_count": 3},
    {"name": "supervisor_system_prompt", "version_count": 2},
    {"name": "insight_composer_prompt", "version_count": 1},
]

# ── release ───────────────────────────────────────────────────────

MOCK_RECENT_RELEASES = [
    {
        "id": "rel-001",
        "name": "platform",
        "version": "4.0.1",
        "status": "active",
        "released_by": "admin",
        "created_at": datetime(2026, 3, 31, 12, 0, 0),
    },
    {
        "id": "rel-002",
        "name": "platform",
        "version": "4.0.0",
        "status": "rolled_back",
        "released_by": "admin",
        "created_at": datetime(2026, 3, 28, 10, 0, 0),
    },
    {
        "id": "rel-003",
        "name": "fraud_module",
        "version": "2.1.0",
        "status": "active",
        "released_by": "devops",
        "created_at": datetime(2026, 3, 25, 15, 0, 0),
    },
]

MOCK_LAST_ROLLBACK = {
    "id": "rel-002",
    "name": "platform",
    "version": "4.0.0",
    "released_by": "admin",
    "created_at": datetime(2026, 3, 28, 10, 0, 0),
}
