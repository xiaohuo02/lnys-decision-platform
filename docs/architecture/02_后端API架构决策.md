# 后端与 API 架构决策（v4.0）

## 1. 结论

当前项目后端继续使用 **FastAPI + 模块化单体**，不在本阶段拆成独立微服务集群。

v4.0 的落地方式是：

- 在 `backend/agents/` 中保留少量核心 Agent
- 在 `backend/services/` 中承接所有确定性业务计算
- 在 `backend/governance/` 中承接 trace / eval / prompt / policy / hitl / audit 能力
- 在 `backend/routers/` 中明确分离外部 API、后台 API、内部服务 API

---

## 2. Agent 与服务的边界

### 2.1 Agent 职责

Agent 只负责：

- 理解用户意图
- 判断复杂度
- 选择 workflow
- 调用服务或其他 Agent
- 汇总 artifact 并生成解释性输出

### 2.2 服务职责

服务负责：

- 规则计算
- 模型推理
- 数据处理
- 公式计算
- schema 校验后的结构化输出
- workflow 与 Agent 在模块化单体内默认直接调用 `backend/services/*`
- `backend/routers/internal/*` 仅作为调试、回归验证、后台触发与模块联调入口

**禁止** 让 Agent 直接承载底层模型实现逻辑。

---

## 3. 核心后端目录

```text
backend/
├── agents/
│   ├── supervisor_agent.py
│   ├── insight_composer_agent.py
│   ├── openclaw_agent.py
│   ├── risk_review_agent.py
│   └── ops_copilot_agent.py
├── services/
│   ├── customer_service.py
│   ├── forecast_service.py
│   ├── fraud_service.py
│   ├── sentiment_service.py
│   ├── inventory_service.py
│   ├── chat_service.py
│   ├── association_service.py
│   ├── dashboard_service.py
│   ├── data_preparation_service.py
│   ├── customer_intelligence_service.py
│   ├── sales_forecast_service.py
│   ├── fraud_scoring_service.py
│   ├── sentiment_intelligence_service.py
│   ├── inventory_optimization_service.py
│   ├── association_mining_service.py
│   └── report_rendering_service.py
├── governance/
│   ├── trace_center/
│   ├── eval_center/
│   ├── prompt_center/
│   ├── policy_center/
│   ├── hitl_center/
│   └── audit_center/
├── routers/
│   ├── external/
│   ├── admin/
│   └── internal/
└── schemas/
```

---

## 4. API 分层

### 4.1 外部 API

面向业务入口：

- `POST /api/v1/analyze`
- `POST /api/v1/chat/openclaw`
- `GET /api/v1/runs/{id}`
- `GET /api/v1/artifacts/{id}`
- `GET /api/v1/reports/{id}/download`

### 4.2 管理后台 API

面向治理控制台：

- `GET /admin/dashboard/summary`
- `GET /admin/workflows`
- `GET /admin/agents`
- `GET /admin/traces`
- `GET /admin/traces/{run_id}`
- `POST /admin/traces/{run_id}/replay`
- `GET /admin/prompts`
- `POST /admin/prompts`
- `POST /admin/prompts/{id}/release`
- `GET /admin/policies`
- `POST /admin/policies`
- `GET /admin/reviews`
- `GET /admin/reviews/{id}`
- `POST /admin/reviews/{id}/approve`
- `POST /admin/reviews/{id}/edit`
- `POST /admin/reviews/{id}/reject`
- `GET /admin/releases`
- `GET /admin/releases/{id}`
- `POST /admin/releases`
- `POST /admin/releases/{id}/rollback`
- `GET /admin/evals/datasets`
- `POST /admin/evals/datasets`
- `GET /admin/evals/evaluators`
- `POST /admin/evals/evaluators`
- `POST /admin/evals/experiments`
- `GET /admin/evals/experiments/{id}`
- `POST /admin/evals/experiments/{id}/run`
- `POST /admin/evals/online-samples/import`
- `GET /admin/knowledge/faqs`
- `POST /admin/knowledge/faqs`
- `GET /admin/memory/records`
- `POST /admin/memory/records/{id}/disable`
- `POST /admin/memory/records/{id}/expire`
- `POST /admin/memory/records/{id}/feedback`
- `GET /admin/audit`
- `POST /admin/auth/login`
- `GET /admin/auth/me`
- `POST /admin/ops-copilot/ask`
- `GET /admin/agents/overview`
- `GET /admin/team/users`
- `GET /admin/team/users/{id}`
- `POST /admin/team/users`
- `PUT /admin/team/users/{id}/role`
- `POST /admin/team/users/{id}/disable`
- `POST /admin/team/users/{id}/enable`
- `GET /admin/team/roles`

### 4.3 内部服务 API

供调试、回归验证、后台运维触发和模块联调使用。
工作流与 Agent 在模块化单体内默认直接调用 `backend/services/*`，不通过 HTTP 再绕一层。

- `POST /internal/data/prepare`
- `POST /internal/customer/intelligence`
- `POST /internal/forecast/run`
- `POST /internal/fraud/score`
- `POST /internal/sentiment/analyze`
- `POST /internal/inventory/optimize`
- `POST /internal/association/mine`
- `POST /internal/report/render`

---

## 5. 工作流引擎

### 5.1 选型

- 使用 `LangGraph` 承接工作流编排
- 工作流只协调 Agent 与服务，不把底层计算塞进图节点里
- 风险审核流程继续使用 `interrupt()` 承接 HITL

### 5.2 首批工作流

- 经营总览分析
- 高风险交易审核
- 客服会话
- 后台运维问答

---

## 6. 后端输出规范

### 6.1 服务输出

所有服务必须输出：

- 明确 schema
- 可解释字段
- 错误字段
- 降级状态（如有）
- artifact 引用或可持久化内容

### 6.2 Agent 输出

Agent 输出优先是：

- `route_plan`
- `artifact_refs`
- `final_summary`
- `risk_highlights`
- `action_plan`

而不是随意的自由文本对象。

---

## 7. Guardrails 与 HITL

### 7.1 必须接入的节点

- 输入 Guardrails
- 路由 Guardrails
- Tool Guardrails
- 输出 Guardrails
- HITL 中断节点

### 7.2 高风险动作

以下能力不允许直接自动执行：

- 冻结订单
- 提交退款
- 修改风控状态
- 发布 Prompt
- 发布 Policy
- 执行回滚

以上动作至少需要：

- 审批流
- 或人工审核
- 或平台策略显式放行

所有高风险写操作必须记录 action ledger，并带 idempotency key。
包括：冻结订单、提交退款、修改风控状态、发布 Prompt、发布 Policy、执行回滚。
恢复执行时必须保证幂等，不允许重复副作用。

### 7A. 身份与权限控制

- 后台必须登录后访问
- 采用 RBAC
- 关键动作需二次确认或审批
- Prompt 发布、Policy 发布、Review 审批、Release 回滚必须受角色约束

核心角色至少包括：

- `platform_admin`
- `ml_engineer`
- `ops_analyst`
- `customer_service_manager`
- `risk_reviewer`
- `auditor`

---

## 8. Git 协作要求

后端开发必须遵守“先 schema / 后 service / 先接入 workflow 或 agent / 再补 internal router / 最后补 admin API 与前端联调”的顺序。

推荐任务拆分：

1. 定义 schema 和 artifact 结构
2. 实现 service
3. 由 workflow / agent 直接接入 service
4. 再补 internal router（调试 / 联调用）
5. 最后补 admin API 与前端联调

每个功能分支只负责一个能力单元，例如：

- `feature/service-fraud-scoring`
- `feature/workflow-business-overview`
- `feature/admin-trace-api`

---

## 9. 暂缓事项

当前阶段不做：

- 独立微服务拆分
- service mesh
- gRPC 内部通信
- PostgreSQL 专属特性绑定
- 大规模异步任务平台化改造

当前阶段的重点是：**先用 FastAPI 模块化单体把 v4.0 跑通，再按需要演进部署形态。**
