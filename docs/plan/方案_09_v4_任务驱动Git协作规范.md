# 柠优生活大数据智能决策平台 · 方案文档（九）
## v4.0 任务驱动 Git 协作规范

> **适用范围**：Agent 开发、后端开发、前端开发、运维与文档维护  
> **适配对象**：`docs/plan/方案_10_v4技术规划文档.md` 与 `docs/plan/方案_11_v4开发任务清单.md` 对应的 v4.0 架构开发  
> **核心原则**：一个任务 = 一个分支 = 一个 PR = 一个独立 AI 会话

---

## 一、分支模型

项目继续采用：

- `main`：稳定生产分支
- `dev`：集成联调分支
- `feature/*`：单任务功能分支

与旧方案不同的是，v4.0 不再建议按“宽泛业务模块”开长期分支，而是按 **阶段、工作流、治理能力、页面或服务** 开短生命周期分支。

### 1.1 推荐分支命名

```text
feature/<task-id>-<short-name>
```

示例：

- `feature/p1-t01-project-skeleton`
- `feature/p1-t03-db-governance`
- `feature/p2-t04-service-fraud`
- `feature/p2-t13-workflow-business-overview`
- `feature/p3-t04-console-prompts`

---

## 二、任务粒度规则

### 2.1 一个分支只能做一类事情

允许：

- 一个服务层能力
- 一个 Agent
- 一个 workflow
- 一个治理后台页面组
- 一个数据库迁移
- 一份核心架构文档更新

不允许：

- 在同一个分支里同时改 3 个 service
- 在同一个分支里混入前端、后端、数据库和文档的大范围无关改动
- 在同一个分支里边改 Prompt Center，边改风控工作流

### 2.2 推荐开发顺序

一个完整能力的推荐拆分顺序：

1. 文档 / ADR / TASKS
2. schema
3. service
4. workflow / agent 直接接入 service
5. internal router（调试 / 联调 / 后台触发）
6. 前端页面
7. 评测 / 回归 / 审计

---

## 三、日常工作流

```bash
# 1. 同步 dev
git checkout dev
git pull origin dev

# 2. 创建任务分支
git checkout -b feature/p2-t04-service-fraud

# 3. 开发并提交
git add .
git commit -m "feat(P2-T04): 新增 FraudScoringService"

# 4. 推送远程
git push origin feature/p2-t04-service-fraud

# 5. 发起 PR 到 dev
# feature/p2-t04-service-fraud -> dev

# 6. 合并后删除分支
git branch -d feature/p2-t04-service-fraud
git push origin --delete feature/p2-t04-service-fraud
```

---

## 四、Commit 与 PR 规范

### 4.1 Commit 格式

```text
<type>(<task-id>): <简要说明>
```

示例：

- `feat(P1-T05): 建立 LangGraph 工作流基础骨架`
- `feat(P2-T02): 封装 CustomerIntelligenceService`
- `fix(P2-T11): 修复 review case 状态流转错误`
- `docs(P0-T02): 新增 v4 任务驱动 Git 协作规范`

### 4.2 PR 标题格式

```text
[type] <task-id> <title>
```

示例：

- `[feat] P2-T13 Workflow A 经营总览分析`
- `[feat] P3-T03 Prompt Center API`
- `[docs] P0-T02 v4 Git workflow`

### 4.3 PR 描述必须包含

- 本 PR 对应的任务编号
- 改动范围
- 是否涉及数据库变更
- 是否涉及环境变量变更
- 是否需要前后端联调
- 是否影响已有工作流
- 验证方式

---

## 五、职责边界

| 目录 | 主要负责人 | 备注 |
|------|-----------|------|
| `backend/agents/` | Agent 开发 | 核心 Agent、workflow 入口 |
| `backend/services/` | 后端 / 算法协同 | 确定性计算逻辑 |
| `backend/routers/` | 后端开发 | 外部 API、后台 API 与 internal 调试/联调入口 |
| `backend/db/` | 后端开发 | 表结构、迁移、初始化 |
| `frontend/src/views/business/` | 前端开发 | 业务页面 |
| `frontend/src/views/console/` | 前端开发 | 治理后台 |
| `ml/` | 算法开发 | 训练脚本、实验、模型产物 |
| `docs/plan/` `docs/architecture/` | 方案维护者 | 文档先行、任务拆解 |

---

## 六、冲突预防规则

### 6.1 先拆任务，再写代码

如果两个开发者都要改同一块能力：

- 先在 `方案_11_v4开发任务清单.md` 中拆出两个任务
- 明确谁负责 schema / service / workflow / internal router / frontend
- 不在没有拆清边界时直接并行修改同一文件

### 6.2 高冲突目录

以下目录改动前必须确认边界：

- `backend/config.py`
- `backend/db/init.sql`
- `backend/main.py`
- `frontend/src/router/`
- `docker-compose.yml`
- `docs/plan/方案_10_v4技术规划文档.md`
- `docs/plan/方案_11_v4开发任务清单.md`

### 6.3 冲突处理建议

```bash
git fetch origin
git checkout feature/xxx
git rebase origin/dev
# 解决冲突
# git add .
# git rebase --continue
```

优先使用 `rebase` 保持任务分支历史整洁。

---

## 七、文档与代码的先后顺序

### 7.1 以下情况必须先更新文档

- 新增 Agent
- 新增 workflow
- 新增治理中心能力
- 新增数据库核心表
- 新增对外 API
- 修改 Prompt / Policy 发布机制

### 7.2 约束

- `方案_10_v4技术规划文档.md` 是规划真相源
- `方案_11_v4开发任务清单.md` 是执行真相源
- `docs/architecture/*.md` 是架构边界真相源
- 未进入 `方案_11_v4开发任务清单.md` 的能力，不建议直接开工

---

## 八、数据库与环境变量改动规则

### 8.1 数据库改动

数据库相关 PR 必须单独拆开，推荐分支：

- `feature/p1-t03-db-governance`
- `feature/p3-t07-audit-center`

PR 中必须说明：

- 新增或修改了哪些表
- 是否兼容旧数据
- 如何初始化或迁移
- 如何回滚

### 8.2 环境变量改动

凡是新增依赖以下变量的改动：

- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL_NAME`
- `LANGCHAIN_API_KEY`
- `LANGCHAIN_PROJECT`
- `MEM0_API_KEY`

都必须同时更新：

- `.env.example`
- 对应文档
- PR 描述

---

## 九、发布规则

### 9.1 合并路径

- 所有功能先合并到 `dev`
- `dev` 联调稳定后再进入 `main`
- `main` 只接收已验证能力，不直接做实验性开发

### 9.2 推荐版本节点

- `v0.1.0`：平台骨架与治理表完成
- `v0.2.0`：核心 services 完成
- `v0.3.0`：3 条核心 workflow 跑通
- `v0.4.0`：治理后台基础能力完成
- `v1.0.0`：答辩版可演示闭环完成

---

## 十、与 AI 协作的建议

如果任务交给 AI 开发，建议每次会话只给一个任务，且初始上下文固定包含：

- `docs/plan/方案_10_v4技术规划文档.md`
- `docs/plan/方案_11_v4开发任务清单.md`
- `docs/architecture/01-04`
- 当前任务编号与验收标准

推荐提问方式：

```text
请读取 方案_10_v4技术规划文档.md、方案_11_v4开发任务清单.md、docs/architecture/01-04，完成 P2-T04。
要求：
1. 仅修改 backend/services 与 backend/routers/internal/fraud 相关文件
2. 不改前端
3. 保留现有 ML 结果与路径
4. 完成后说明影响范围与后续联调点
```

这样最符合当前仓库的 Git 配合开发方式。
