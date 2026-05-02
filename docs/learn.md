# 参考项目学习笔记 — Aco / Forge 最佳实践对照

> **来源**: `D:\aco`（含 aco-main 设计文档 + forge-main 16 篇系统设计文档）
> **目标**: 对照本项目（LNYS 柠优生活智能决策平台）现状，提取可落地的优化参考点
> **原则**: 只记录对本项目有实际价值的点，不做无意义搬运

---

## 目录

1. [上下文治理与自动压缩](#1-上下文治理与自动压缩)
2. [结构化分层记忆](#2-结构化分层记忆)
3. [统一错误处理与分级降级](#3-统一错误处理与分级降级)
4. [统一 Token 计数](#4-统一-token-计数)
5. [统一可观测性（Telemetry）](#5-统一可观测性telemetry)
6. [Hook 生命周期事件驱动](#6-hook-生命周期事件驱动)
7. [声明式权限规则](#7-声明式权限规则)
8. [多模型角色路由](#8-多模型角色路由)
9. [Prompt 工程分段缓存](#9-prompt-工程分段缓存)
10. [工具执行拦截器链](#10-工具执行拦截器链)
11. [评测框架与实验方法](#11-评测框架与实验方法)
12. [并行子 Agent 调度与资源隔离](#12-并行子-agent-调度与资源隔离)
13. [启动编排与依赖注入顺序](#13-启动编排与依赖注入顺序)
14. [工具输出源头裁剪](#14-工具输出源头裁剪)
15. [Session 持久化与断点恢复](#15-session-持久化与断点恢复)
16. [记忆新鲜度与自动失效](#16-记忆新鲜度与自动失效)
17. [Agent 契约模板化](#17-agent-契约模板化)
18. [阶段式工作流与门控确认](#18-阶段式工作流与门控确认)
19. [Agent 模板与能力分级](#19-agent-模板与能力分级)
20. [数据读取去重与智能历史折叠](#20-数据读取去重与智能历史折叠)
21. [跨 Session 项目级记忆](#21-跨-session-项目级记忆)
22. [Skill/工具按场景自动激活](#22-skill工具按场景自动激活)
23. [Git/数据源变更感知上下文](#23-git数据源变更感知上下文)
24. [安全模式匹配 Hook](#24-安全模式匹配-hook)
25. [重复调用检测与行为熔断](#25-重复调用检测与行为熔断)
26. [双路径模型调用 (FC+XML)](#26-双路径模型调用-fcxml)
27. [模型能力注册表与自动预算推导](#27-模型能力注册表与自动预算推导)

---

## 1. 上下文治理与自动压缩

### 参考来源
- `forge-main/doc/13-自动压缩与上下文熔断设计.md`
- `aco-main/docs/design.md` § 3.5 compact

### Aco/Forge 做法
- **ContextMonitor**: 每轮执行后评估上下文 token 占比 → 三状态机 `HEALTHY / NEEDS_COMPACT / CIRCUIT_BREAK`
- **AutoCompactor**: 超 80% 阈值时用 LLM（COMPACT 角色小模型）摘要旧历史，保留最近 6 轮不动
- **熔断机制**: 连续 3 次压缩无效（reduction < 15%）→ 熔断停止，给出可操作错误信息
- **ContextBudget**: 不可变 dataclass，从模型名自动推导预算

### LNYS 现状 ✅ 已实现
- `backend/core/context_monitor.py` — 三状态机 (HEALTHY/NEEDS_COMPACT/CIRCUIT_BREAK) + ContextBudget 按模型自动推导
- `CopilotEngine.run()` step 2.5 集成 context_monitor.evaluate() → 自动压缩 + 熔断告警
- `backend/core/token_counter.py` — 统一 token 估算 + truncate_to_budget (head_tail 截断)
- `_synthesize_answer` 已用 token_counter.truncate_to_budget 裁剪 Skill 输出
- TelemetryDashboard 前端展示上下文 Gauge + 压缩次数 + 熔断计数

### 剩余优化
1. ~~CopilotEngine 增加 ContextMonitor~~ ✅
2. ~~thread_history 压缩~~ ✅ (compact_messages 用 COMPACT 模型摘要)
3. **Workflow 节点添加 token 预算字段**: BusinessOverviewState 增加 `token_budget` / `token_used` (后续迭代)
4. **InsightComposerAgent prompt 预算化**: 分段控制各 artifact 的 token 占比 (后续迭代)

### 优先级: ~~高~~ → **核心已完成**，剩余为精细化优化

---

## 2. 结构化分层记忆

### 参考来源
- `forge-main/doc/05-结构化的会话记忆.md`
- `aco-main/docs/design.md` § 3.6 memory

### Aco/Forge 做法
- **四层结构**: task_summary + recent_files + file_summaries + episodic_notes
- 每层有**硬上限**（8 文件 / 12 笔记 / 6 摘要）和**文本长度裁剪**
- 不用向量检索，用**轻量规则召回**（tag 命中 + 关键词重叠 + 时间新旧）→ 可解释
- `render_memory_text()` 渲染给模型看时重新校验新鲜度

### LNYS 现状 ✅ 已实现
- `copilot/context.py` 三层记忆 (Redis thread_history → copilot_memory DB → copilot_rules 静态配置)
- memory reconciliation: decay + soft-delete 自动衰减
- `memory_skill.py` 支持记忆读写，通过 Copilot 自然语言管理
- `MemoryGovernance.vue` 前端展示新鲜度分布 + 健康总览
- `memory_freshness.py` Ebbinghaus 灵感新鲜度评分
- `memory_consolidator.py` L2 对话压缩 + L3 记忆提取

### 剩余优化
1. **记忆细分层**: 拆为 task_summary / recent_skills / skill_summaries / episodic_notes (后续迭代)
2. ~~每层硬上限~~ ✅ (reconciliation decay 已实现)
3. **轻量召回替代全量注入**: 按当前问题做 top-K 规则召回 (后续迭代)
4. **Skill 执行后自动沉淀**: Skill 关键结论自动写入记忆 (后续迭代)

### 优先级: ~~高~~ → **核心已完成**，剩余为精细化

---

## 3. 统一错误处理与分级降级

### 参考来源
- `forge-main/doc/14-宏观架构总览与跨切面设计.md` § 跨切面 2

### Aco/Forge 做法
- **三级错误分类**: `Retryable`（重试）/ `Degradable`（降级跳过）/ `Fatal`（致命停止）
- **统一 ErrorHandler.classify()**: 所有组件异常经同一入口分类
- 主循环 match-case 按级别分别处理：重试 / 注入降级消息 / 停止并记录诊断

### LNYS 现状 ✅ 已实现
- `backend/core/exceptions.py` 统一异常体系: AppError 基类 + ResourceNotFoundError / ValidationError / PermissionDeniedError / RateLimitError
- `main.py` 四层 handler: app_error / http_exception / validation_error / unhandled_exception
- CopilotEngine: CancelledError / TimeoutError / 通用 Exception 分级处理 + ERROR_CLASSIFIED telemetry
- Workflow 并行节点独立 try-except，单节点失败不阻断其他
- `AgentGateway` timeout + exception → None 统一兜底

### 剩余优化
1. **AgentError 三级分类 (Retryable/Degradable/Fatal)**: 更精细的错误分级 (后续迭代)
2. ~~ErrorHandler 统一入口~~ ✅ (core/exceptions.py)
3. **Workflow 节点自动重试**: 可重试类错误自动 retry (后续迭代)

### 优先级: ~~高~~ → **核心已完成**，剩余为精细化

---

## 4. 统一 Token 计数

### 参考来源
- `forge-main/doc/14-宏观架构总览与跨切面设计.md` § 跨切面 1

### Aco/Forge 做法
- **TokenCounter 接口**: 统一注入所有预算组件
- 默认实现: `char / 4` 粗估（快速，无依赖）
- 精确实现: 调 tiktoken 或 provider tokenizer
- 所有预算组件（上下文裁剪 / 自动压缩 / 工具输出限制 / 子 Agent 结果合并）用同一个 counter

### LNYS 现状 ✅ 已实现
- `backend/core/token_counter.py` 统一单例，支持 estimate / estimate_messages / fits_budget / truncate_to_budget / split_budget
- 中英文混合优化: CJK 1.5x + ASCII 0.25x + Other 0.5x，误差 < 15%
- CopilotEngine `_synthesize_answer` 用 truncate_to_budget(4000) 裁剪 Skill 输出
- context_monitor 用 estimate_messages 评估上下文 token
- runs 表已记录 total_tokens

### 剩余优化
1. ~~创建 token_counter.py~~ ✅
2. **Copilot prompt 分段预算**: 上下文/记忆/Skill结果各分配预算 (后续迭代)
3. **Workflow runs 补充 token 统计**: per-node token 用量 (后续迭代)

### 优先级: ~~中~~ → **核心已完成**

---

## 5. 统一可观测性（Telemetry）

### 参考来源
- `forge-main/doc/14-宏观架构总览与跨切面设计.md` § 跨切面 3

### Aco/Forge 做法
- **集中 EventType 枚举**: RUN_STARTED / MODEL_REQUESTED / TOOL_EXECUTED / HOOK_FIRED / COMPACT_TRIGGERED / ERROR_OCCURRED 等
- **统一 Telemetry.emit()**: 所有组件不直接写 trace，通过注入的 Telemetry 实例发射事件
- **TelemetrySummary**: 提供 metrics 聚合视图（事件计数 / 模型调用 / cache 命中 / 压缩次数 / 错误数 / 时长）

### LNYS 现状 ✅ 已实现
- `backend/core/telemetry.py` 统一发射入口 + TelemetrySummary Pydantic 聚合模型
- 16 种 TelemetryEventType 枚举: RUN_STARTED/COMPLETED/FAILED, MODEL_REQUESTED/COMPLETED/FAILED, SKILL_EXECUTED, COMPACT_TRIGGERED/COMPLETED, CONTEXT_EVALUATED, ERROR_CLASSIFIED 等
- CopilotEngine 全链路接入: run 生命周期 + 路由 + 通用对话 + 综合回答 + Skill 执行 + 上下文治理
- BusinessOverview Workflow 并行阶段接入
- MemoryConsolidator L2/L3 LLM 调用接入
- `TelemetryDashboard.vue` 前端: 实时指标卡 + 模型路由图 + 上下文 Gauge + 事件流 + 组件分布
- `BenchmarkDashboard.vue` 前端: 评测实验聚合总览
- `/admin/telemetry/*` 5 个 API 端点

### 剩余优化
1. ~~统一 TelemetryEvent schema~~ ✅
2. ~~创建 telemetry.py~~ ✅
3. ~~关键路径接入~~ ✅
4. **ops_diagnosis / risk_review workflow 接入 telemetry** (后续迭代)

### 优先级: ~~中~~ → **已完成**

---

## 6. Hook 生命周期事件驱动

### 参考来源
- `forge-main/doc/09-Hook生命周期与事件驱动设计.md`
- `aco-main/docs/design.md` § 3.7 hook

### Aco/Forge 做法
- **6 种生命周期事件**: SESSION_START / PRE_TOOL_USE / POST_TOOL_USE / STOP / STOP_FAILURE / POST_COMPACT
- **6 种结构化决策**: Approve / Deny / Ask / Block / Defer / InjectContext
- **决策合并**: Block > Deny > InjectContext > Approve > Defer
- **工具名模式匹配**: glob 模式匹配特定工具
- **TestEnforcementHook**: 代码改了但没跑测试 → Block 阻止停止

### LNYS 现状
- `hook_pipeline.py` 已有 Pre/Post Hook 管道，支持 allow/warn/block/modify 四种 action
- `input_guard.py` 和 `output_validator.py` 作为 guardrails
- 但 Hook 事件类型有限（只有 pre_service_call / post_service_call）
- 无 SESSION_START / STOP / POST_COMPACT 等生命周期事件
- 无 Workflow 级别的 Hook

### 可落地优化
1. **扩展 HookEvent 类型**: 增加 `WORKFLOW_START` / `WORKFLOW_END` / `AGENT_CALL` / `HITL_TRIGGER` / `COPILOT_SESSION_START`
2. **HookPipeline 支持 glob 匹配**: 按 service_name / agent_name 模式匹配
3. **Workflow 级 Hook**: 在 `build_business_overview_graph` 等构建器中注入 pre/post 节点 Hook
4. **Copilot 停止决策 Hook**: Copilot 回复前检查是否需要强制补充操作（如高风险结论需要二次确认）

### 优先级: **中** — 治理能力增强

---

## 7. 声明式权限规则

### 参考来源
- `forge-main/doc/10-结构化权限规则与安全治理设计.md`

### Aco/Forge 做法
- **PermissionRule record**: toolPattern(glob) + argPattern(glob) + decision(ALLOW/ASK/DENY) + source(SYSTEM/PROJECT/USER) + priority
- **三层规则来源**: SYSTEM（不可覆盖的安全底线）> PROJECT > USER
- **裁决引擎**: 找所有匹配规则，取优先级最高的决策，无匹配默认 ASK
- **内置安全底线**: 危险命令/敏感路径/PII 文件绝对禁止

### LNYS 现状
- `permissions.py` 有 RBAC 矩阵 + PermissionChecker
- `copilot_skill_overrides` 表支持 per-skill 权限覆盖
- `input_guard.py` 做输入安全检查
- 但权限粒度是 skill 级别，不是 skill + 参数级别

### 可落地优化
1. **Skill 权限支持参数级匹配**: 如 `fraud_skill` 只允许查询不允许修改阈值
2. **声明式规则配置**: 管理员可在 copilot_skill_overrides 中配置参数级 allow/deny
3. **三层优先级**: SYSTEM 底线（代码写死）> PROJECT 配置（DB/配置文件）> USER 偏好
4. **审计日志增强**: 每次权限裁决记录匹配的规则和决策理由

### 优先级: **低** — 当前 RBAC 够用，后续企业化时再增强

---

## 8. 多模型角色路由

### 参考来源
- `aco-main/docs/design.md` § 3.2.4 ModelSelector
- `forge-main/doc/14-宏观架构总览与跨切面设计.md` § 跨切面 6

### Aco/Forge 做法
- **ModelRole 枚举**: PRIMARY / EXPLORATION / COMPACT / REVIEW / ROUTING
- **按任务特征选模型**: 压缩用小模型（便宜快速），审查用强模型（准确），探索用快模型
- **ModelSelector**: 未配置的角色 fallback 到 PRIMARY
- **成本优化的关键杠杆**: 不是所有地方都需要最强模型

### LNYS 现状 ✅ 已实现
- `backend/core/model_selector.py` ModelSelector 单例 + ModelRole 枚举 (PRIMARY/ROUTING/COMPACT/REVIEW)
- `config.py` 支持 LLM_MODEL_PRIMARY / LLM_MODEL_ROUTING / LLM_MODEL_COMPACT / LLM_MODEL_REVIEW 配置
- CopilotEngine._route_to_skill 用 ROUTING 模型
- context_monitor.compact_messages 用 COMPACT 模型
- MemoryConsolidator L2 用 COMPACT、L3 用 REVIEW
- 未配置角色自动 fallback 到 PRIMARY
- get_model_info() 供 /health 和前端展示

### 剩余优化
1. ~~ModelSelector 工厂~~ ✅
2. ~~ROUTING / COMPACT / REVIEW 模型分离~~ ✅
3. **InsightComposerAgent 接入 ModelSelector**: 当前仍用 settings.LLM_MODEL_NAME (后续迭代)

### 优先级: ~~高~~ → **已完成**

---

## 9. Prompt 工程分段缓存

### 参考来源
- `forge-main/doc/04-提示词形态与缓存复用设计.md`
- `forge-main/doc/15-系统Prompt工程与输出解析设计.md`
- `aco-main/docs/design.md` § 3.3 context

### Aco/Forge 做法
- **10 段结构化 Prompt**: 稳定段（角色+工具+格式）在前 → 利于 API prompt cache; 动态段在后
- **PromptPrefix**: 不可变对象 + fingerprint + cache_key
- **每轮检测 fingerprint**: workspace/tool 签名变了才重建 prefix
- **工具 schema 确定性排序**: 按 name 字母序，保证 cache 命中率
- **动态内容严格隔离**: 从工具描述中移除动态内容

### LNYS 现状
- CopilotEngine 每次调用都重新组装完整 system prompt
- InsightComposerAgent 的 prompt 是字符串拼接，无分段管理
- 无 prompt cache 意识
- 工具 schema（Function Calling）无确定性排序

### 可落地优化
1. **Copilot system prompt 分段**:
   - 稳定段: 角色定义 + Skill schema + 行为约束 → 构建一次，fingerprint 校验
   - 半稳定段: 用户权限 + 可用 Skill 列表 → 用户变化时重建
   - 动态段: 记忆 + 历史 + 当前问题 → 每轮重建
2. **Function Calling schema 排序**: `get_function_schemas()` 按 skill.name 字母序排列
3. **InsightComposerAgent prompt 模板化**: 稳定指令和动态数据分离
4. **SupervisorAgent prompt 缓存**: 关键词规则变更频率低，可缓存

### 优先级: **中** — 降低 LLM 调用成本，提升缓存命中

---

## 10. 工具执行拦截器链

### 参考来源
- `aco-main/docs/design.md` § 3.4 tools (ToolExecutionChain + PostEditVerifyInterceptor)

### Aco/Forge 做法
- **ToolExecutionChain**: validate → interceptor[0].before → ... → tool.execute → ... → interceptor[0].after
- **PostEditVerifyInterceptor**: 编辑后自动执行编译/lint/测试，验证结果追加到 ToolResult
- **拦截器可组合**: 按序执行，before 可短路，after 可修改结果

### LNYS 现状
- `HookPipeline` 已有 pre/post 概念
- `AgentGateway` 做统一调用封装
- 但无类似 ToolExecutionChain 的拦截器链模式
- Skill 执行后无自动校验

### 可落地优化
1. **Skill 执行链增加拦截器**: 在 CopilotEngine Skill 执行前后增加可插拔拦截器
2. **PostSkillVerifyInterceptor**: Skill 输出后自动校验 schema 合法性、敏感信息、数据一致性
3. **AuditInterceptor**: 自动记录每次 Skill 执行的输入/输出摘要到 audit_log
4. **RateLimitInterceptor**: 按用户/Skill 维度限流

### 优先级: **低** — 当前 HookPipeline 基本够用，后续增强

---

## 11. 评测框架与实验方法

### 参考来源
- `forge-main/doc/08-评测框架与实验方法设计.md`

### Aco/Forge 做法
- **Benchmark 任务合同**: id + prompt + fixture + allowed_tools + step_budget + verifier + category
- **四条件判定通过**: 不超预算 + verifier 通过 + 期望工件存在 + 正常停止
- **失败分类**: missing_artifact / budget_exceeded / verifier_failed / failure_stop_reason
- **Scripted baseline**: FakeModelClient 先验证 harness 自身正确性，与真实模型波动解耦
- **Feature ablation**: 不同机制用不同指标证明，不全用同一个大指标

### LNYS 现状
- `eval_center/` 有评测框架
- `test_round5_final.py` 等有回归测试
- 但无 Benchmark 任务合同的结构化定义
- 无 FakeModelClient 用于 harness 稳定性验证
- Agent 评测偏端到端，缺少机制级 ablation

### 可落地优化
1. **定义 Workflow Benchmark 合同**: JSON 格式定义标准测试用例（request_type + 输入数据 + 期望输出 schema + 步骤预算 + verifier）
2. **Copilot Skill Benchmark**: 每个 Skill 定义 3-5 个标准测试用例
3. **FakeModelClient**: mock LLM 响应，测 CopilotEngine/SupervisorAgent 的 harness 稳定性
4. **失败分类**: 区分 LLM 失败 / Skill 失败 / 数据缺失 / 超时 / schema 不匹配
5. **机制级评测**: 分别评测记忆对重复率的影响、压缩对 token 消耗的影响、多模型路由对成本的影响

### 优先级: **中** — 质量保障和持续优化的基础

---

## 12. 并行子 Agent 调度与资源隔离

### 参考来源
- `forge-main/doc/12-并行子Agent调度与工作流编排设计.md`
- `forge-main/doc/14-宏观架构总览与跨切面设计.md` § 跨切面 5

### Aco/Forge 做法
- **SubAgentSpec**: name + task + capability(READ_ONLY/READ_WRITE/FULL) + allowedTools + maxSteps + timeout + model
- **并行调度器**: CompletableFuture 并行启动，超时保留部分结果
- **资源隔离**: READ_ONLY → 共享; READ_WRITE → 拷贝独立 memory; FULL → 完全隔离
- **阶段式编排**: 探索 → 门控确认 → 设计 → 实现 → 审查

### LNYS 现状 ✅ 已实现
- `_node_parallel_analysis` 用 `asyncio.gather` 并行执行 5 个分析节点 (customer/forecast/sentiment/fraud/inventory)
- 每个节点独立 try-except，单节点失败不阻断其他
- SSE 实时推送并行阶段进度 (parallel_started / parallel_completed)
- Telemetry 记录并行执行指标 (WORKFLOW_PARALLEL_STARTED / WORKFLOW_PARALLEL_COMPLETED)
- 前端 `AgentTopologyGraph.vue` SVG DAG 可视化 + `useWorkflowStream.js` 消费并行事件
- 实际收益: 总延迟 ≈ max(单节点延迟) 而非 sum，提速 ~3x

### 剩余优化
1. ~~business_overview 并行化~~ ✅
2. ~~节点超时+部分结果保留~~ ✅
3. **Copilot 并行 Skill**: 同时调多个 Skill (后续迭代)
4. **ops_diagnosis / risk_review 并行化**: 其他 workflow 也可受益 (后续迭代)

### 优先级: ~~高~~ → **已完成**

---

## 13. 启动编排与依赖注入顺序

### 参考来源
- `forge-main/doc/14-宏观架构总览与跨切面设计.md` § 跨切面 4
- `aco-main/docs/design.md` § 3.10 cli

### Aco/Forge 做法
- **AgentBootstrap**: 严格按依赖顺序初始化 14 个组件
- **构造顺序即依赖关系**: 从上到下，每步只依赖前面已创建的对象
- **共享依赖显式传递**: TokenCounter / Telemetry 一处创建多处注入
- **不用 DI 框架**: 手动构造函数注入，透明可调试

### LNYS 现状
- `main.py` lifespan 中依次初始化 Redis / DB / Agent Registry / SkillRegistry
- 但初始化顺序未文档化
- 共享组件（如 Redis 连接、DB session）通过全局变量传递，不够显式
- SkillRegistry auto_discover() 与 Agent 注册的依赖关系隐式

### 可落地优化
1. **main.py 启动顺序文档化**: 注释明确每步依赖链
2. **共享组件显式注入**: TokenCounter / Telemetry / ErrorHandler 等跨切面组件统一在 lifespan 创建，注入到各子系统
3. **健康检查顺序**: 启动时按依赖顺序检查（DB → Redis → LLM → Agent → Skill → Workflow）
4. **失败隔离**: 单个 Agent 或 Skill 加载失败不阻断其他（当前已做到，需保持）

### 优先级: **低** — 工程规范改进

---

## 14. 工具输出源头裁剪

### 参考来源
- `forge-main/doc/06-上下文瘦身与输出管理设计.md`
- `aco-main/docs/design.md` § 3.9 runtime `_truncate_tool_output`

### Aco/Forge 做法
- **四层裁剪**:
  1. 源头: 工具输出统一 clip（默认 4000 char）
  2. 记忆: 各层硬上限
  3. 历史: 新旧分层（最近 6 轮详细，旧历史 60 char/条 vs 最近 900 char/条）
  4. Section 预算: 最终按段分配预算
- **截断策略**: 保留 70% 头部 + 30% 尾部（比纯截头好）
- **重复 read_file 折叠**: 旧历史中按路径去重

### LNYS 现状
- Skill 执行结果无统一裁剪
- CopilotEngine 写 runs 表时 `output_summary` 截断到 500 char
- Workflow 节点输出无长度控制
- InsightComposerAgent 接收 artifact 无大小限制

### 可落地优化
1. **Skill 输出统一裁剪**: BaseCopilotSkill 增加 `max_output_chars` 属性，engine 层自动 clip
2. **头尾保留策略**: 截断时保留 70% 头部 + 30% 尾部
3. **Workflow artifact 大小限制**: 每个 artifact 写入时检查大小，超限压缩
4. **历史分层压缩**: thread_history 旧消息压缩到短摘要，最近消息保持原样

### 优先级: **中** — 防止 prompt 膨胀

---

## 15. Session 持久化与断点恢复

### 参考来源
- `aco-main/docs/design.md` § 3.8 session
- `forge-main/doc/07-会话状态、运行工件与恢复机制设计.md`

### Aco/Forge 做法
- **SessionStore**: history + memory + metadata → JSON 文件
- **RunStore**: task_state.json + trace.jsonl → 每次 ask() 持续更新
- **resume latest**: 恢复上次会话的完整状态
- **run artifact**: commit + branch + model + 参数 + fixture snapshot id → 完整复现上下文

### LNYS 现状
- Copilot 对话通过 `persistence.py` 写入 MySQL thread/message 表
- Workflow 通过 PostgreSQL checkpoint 支持断点恢复
- 但 Copilot session 恢复仅限消息历史，不含记忆状态和上下文
- Workflow run artifact 只有 runs 表基础字段

### 可落地优化
1. **Copilot session 恢复增强**: 保存并恢复 context 状态（记忆快照 + Skill 中间结果）
2. **Workflow run artifact 丰富**: 记录每个节点的输入摘要 / 输出摘要 / 耗时 / token / 模型版本
3. **复盘功能**: 按 run_id 完整回放 Workflow 执行链路

### 优先级: **低** — 当前基本够用

---

## 16. 记忆新鲜度与自动失效

### 参考来源
- `forge-main/doc/05-结构化的会话记忆.md` § 旧摘要怎么失效

### Aco/Forge 做法
- **freshness hash**: file_summaries 每条带文件内容 hash
- **渲染时校验**: render_memory_text() 重新算 hash，不匹配的旧摘要不显示
- **写操作主动失效**: write_file / patch_file 后 invalidate 旧摘要
- **核心原则**: 文件变了模型还拿旧摘要推理，比"没记住"更危险

### LNYS 现状
- copilot_memory 表有 updated_at 时间戳
- context.py 有 memory reconciliation（decay + soft-delete）
- 但无内容级新鲜度校验
- Agent 间通过 artifact_store 传递结果，无新鲜度标记

### 可落地优化
1. **Copilot 记忆增加 freshness**: 基于数据源更新时间判断记忆是否仍然有效
2. **Artifact 新鲜度**: artifact_store 中的数据标记生成时间和数据源版本
3. **跨 Workflow 结果缓存失效**: 当底层数据更新时，旧 Workflow 结果自动标记为 stale
4. **Skill 结果缓存 TTL**: 频繁查询的 Skill 结果设置合理 TTL

### 优先级: **中** — 数据一致性保障

---

## 17. Agent 契约模板化

### 参考来源
- 本项目已有实践（risk_review_agent.py / openclaw_agent.py 的契约头注释）
- Forge 的 SubAgentSpec 结构化定义

### LNYS 现状（已做得好的部分）
- `risk_review_agent.py` 和 `openclaw_agent.py` 有完整的 Agent 契约注释:
  - 输入 schema / 允许调用的 tool / 输出 schema / 不能做的事 / 失败降级 / HITL 条件 / 依赖 artifact / trace 字段
- 这已经是很好的实践

### 可进一步优化
1. **契约从注释升级为代码**: 将 Agent 契约定义为 Pydantic model，运行时自动校验
2. **统一模板**: 所有 Agent 使用同一个 ContractSpec dataclass（输入/输出/工具白名单/降级策略/HITL 条件）
3. **自动测试生成**: 从 Contract 自动生成基础测试用例（输入校验 / 输出 schema 校验 / 降级路径验证）

### 优先级: **低** — 当前注释式契约已足够，代码化是锦上添花

---

## 18. 阶段式工作流与门控确认

### 参考来源
- `aco-main/docs/design.md` § 8.1 WorkflowEngine + WorkflowTemplates
- `forge-main/doc/12-并行子Agent调度与工作流编排设计.md`
- `forge-main/doc/16-产品原型文档-对标Codex的本地Code Agent.md`

### Aco/Forge 做法
- **WorkflowPhase**: 每个阶段定义 PhaseType (PARALLEL_AGENTS / SINGLE_AGENT / USER_INPUT) + agent_specs + requires_user_approval
- **WorkflowEngine**: 按顺序执行 phase，PARALLEL → scheduler 并行，SINGLE → 单 agent，USER_INPUT → 等用户确认（门控）
- **3 种预定义模板**:
  - `code_review`: 探索→并行审查(convention+bug+security)→用户审批
  - `feature_dev`: 并行探索→并行设计→**用户选方案**→实现→并行审查
  - `quick_explore`: 2 个 explorer 并行(high-level+deep-dive)
- **跨阶段 context Map**: 前阶段结果注入后阶段上下文
- **ReviewResultFilter**: 过滤低置信度发现 (threshold=0.7)

### LNYS 现状
- `build_business_overview_graph` 有 LangGraph 多节点编排，parallel fan-out/fan-in
- 但无门控确认（所有节点自动推进，无 USER_INPUT 类型）
- 无跨阶段方案选择（如用户在两个设计方案中选一个）
- Workflow 模板硬编码在 graph builder 中，不可参数化

### 可落地优化
1. **Workflow 增加门控节点**: 在关键决策点（如风险评估结论异常、多方案取舍）插入 USER_INPUT 阶段，通过 SSE 推送等待用户确认
2. **参数化 Workflow 模板**: 将 business_overview / risk_review / ops_diagnosis 的阶段定义抽为配置，支持管理员自定义节点组合
3. **跨阶段 Context Map**: 前阶段 artifact 自动作为后阶段的 context 输入，减少重复数据查询

### 优先级: **中** — 提升复杂决策的可控性

---

## 19. Agent 模板与能力分级

### 参考来源
- `aco-main/docs/design.md` § 8.1 AgentTemplate + SubAgentSpec + AgentCapability + IsolationLevel

### Aco/Forge 做法
- **5 种 Agent 模板**: CODE_EXPLORER(只读探索) / BUG_HUNTER(bug扫描+置信度) / CODE_REVIEWER(代码审查) / CODE_ARCHITECT(架构设计) / IMPLEMENTER(可写实现)
- **3 级能力控制**: READ_ONLY / READ_WRITE / FULL
- **3 级资源隔离**: SHARED(共享父资源) / COPY(独立memory) / FULL(独立workspace)
- **工具白名单**: 按能力级别自动限制可用工具集
  - READ_ONLY → {list_files, read_file, search}
  - READ_WRITE → 上述 + {write_file, patch_file, multi_patch_file}
  - FULL → 上述 + {run_shell}
- **每个模板预配置**: 角色名、专用 system prompt、步数限制、超时时间

### LNYS 现状
- Agent 契约在注释中定义（risk_review_agent.py / openclaw_agent.py）
- SupervisorAgent 有 Skill 白名单分配
- 但无标准化的 Agent 模板系统
- 无能力分级（所有 Agent 本质都是 FULL 权限）
- Agent 之间资源隔离不明确

### 可落地优化
1. **定义 AgentTemplate 枚举**: ANALYST(只读查询) / ADVISOR(分析+建议) / EXECUTOR(可执行操作) / SUPERVISOR(编排调度)
2. **能力白名单**: 按 AgentTemplate 限制可调用的 Skill 集合
3. **AgentSpec dataclass**: 统一每个 Agent 的 name/capability/allowed_skills/max_steps/timeout/model 配置

### 优先级: **低** — 当前 Agent 数量有限，后续 Agent 增多时再规范化

---

## 20. 数据读取去重与智能历史折叠

### 参考来源
- `aco-main/docs/design.md` § 8.9 FileReadDeduplicator
- `forge-main/pico-main/tests/test_context_manager.py` — 历史折叠测试
- `forge-main/doc/06-上下文瘦身与输出管理设计.md`

### Aco/Forge 做法
- **FileReadDeduplicator**: content hash 去重，重复 read_file 返回 "[same as read_file #N path]" 而非完整内容
- **智能历史折叠**:
  - 旧历史中相同文件的多次 read_file 折叠为一行摘要: `"[tool:read_file] sample.txt -> alpha | beta"`
  - 旧 tool 输出压缩为一行: `"pytest -q -> FAIL test_one | FAIL test_two | FAIL test_three"`
  - 最近 N 轮保持完整，旧条目自动折叠
- **Metadata 追踪**: collapsed_duplicate_reads / summarized_tool_count / reused_file_summary_count

### LNYS 现状
- CopilotEngine thread_history 原样保留所有历史消息
- Workflow 节点间无数据去重（同一客户数据可能被多个节点重复查询）
- compact_messages 做整体摘要但不做逐条智能折叠
- Skill 执行结果每次重新生成，不复用

### 可落地优化
1. **Skill 结果缓存**: 相同 Skill + 相同参数在 TTL 内返回缓存结果，避免重复 LLM/DB 调用
2. **Thread History 智能折叠**: compact_messages 增强——旧 Skill 输出折叠为一行摘要，最近 3 轮保持完整
3. **Workflow 节点数据共享**: parallel 阶段的共同数据依赖（如客户基础信息）只查询一次，通过 state 共享

### 优先级: **中** — 降低 token 消耗和重复查询成本

---

## 21. 跨 Session 项目级记忆

### 参考来源
- `aco-main/docs/design.md` § 8.10 ProjectMemoryStore

### Aco/Forge 做法
- **ProjectMemoryStore**: 持久化到 .agent/memories.json，跨 session 加载
- **Jaccard 去重**: 相似度 > 0.7 视为相似，更新而非新增
- **带标签和时间戳**: 支持 remember / find_by_tags / search / forget
- **用途**: 存储项目决策、架构约定、反复出现的问题解决方案
- **双来源**: "user" (用户显式记忆) / "auto" (Agent 自动沉淀)

### LNYS 现状
- copilot_memory 表是 per-user 的，有 decay + soft-delete
- memory_consolidator L3 可以提取跨对话的长期记忆
- 但无"项目级"记忆——跨用户共享的项目知识（如"库存预警阈值是30天"、"该客户偏好XX品类"）
- knowledge_base 是静态文档，不是动态沉淀的项目记忆

### 可落地优化
1. **项目级记忆表 (copilot_project_memory)**: 所有用户共享的项目知识，来源标记 (user/auto/skill)
2. **Skill 自动沉淀**: 高频查询结论自动写入项目记忆（如"2025年Q2库存周转天数45天"）
3. **去重合并**: 新记忆与已有记忆做相似度检查，避免重复条目
4. **Copilot 自动召回**: 与当前问题相关的项目记忆自动注入 context

### 优先级: **中** — 对多用户场景价值大

---

## 22. Skill/工具按场景自动激活

### 参考来源
- `aco-main/docs/design.md` § 8.11 SkillDefinition + § 9.13 SkillRegistry
- `forge-main/doc/11-插件化工具注册与MCP协议设计.md` § ToolSearch

### Aco/Forge 做法
- **SkillDefinition**: Markdown 文件 + YAML frontmatter，定义 name / description / paths (glob 模式)
- **自动激活**: 当 Agent 编辑匹配 paths 的文件时，对应 Skill 内容自动注入 context
- **ToolSearch**: 不是所有工具都一开始塞进 prompt，核心工具先上，其余按需激活
- **好处**: 减少初始 prompt 长度 + 提升 cache 命中率 + 按需扩展

### LNYS 现状
- CopilotEngine._route_to_skill 通过 LLM 路由决定调用哪个 Skill
- 所有 Skill schema 始终全量注入 Function Calling prompt
- 无场景自动激活（不会根据用户正在查看的页面自动关联 Skill）
- Skill 数量增多时 prompt 开销线性增长

### 可落地优化
1. **Skill 分组**: 将 11 个 Skill 分为 core（始终可用）和 extended（按需激活）
   - core: memory, system, kb_rag
   - extended: inventory, forecast, sentiment, customer_intel, fraud, association, trace, ocr
2. **场景感知激活**: 前端传递当前页面 context（如"正在查看库存页"），Engine 只注入相关 Skill schema
3. **Skill Schema 缓存**: Function Calling schema 按名称排序，确保 prompt cache 命中

### 优先级: **中** — 当 Skill 超过 15 个时收益明显

---

## 23. Git/数据源变更感知上下文

### 参考来源
- `aco-main/docs/design.md` § 9.3 GitDiffContextProvider

### Aco/Forge 做法
- **GitDiffContextProvider**: 编辑前自动注入 git diff 信息
  - get_uncommitted_diff(path) → 未提交变更
  - get_staged_diff(path) → 暂存区变更
  - get_recent_history(path, count) → 最近 git log
  - get_blame(path, start, end) → 行级归因
  - build_edit_context(path) → 组合 diff + history 为编辑前上下文
- **输出限制**: diff 限 200 行 / 3000 字符，命令 5s 超时

### LNYS 现状
- CopilotEngine 不感知数据源的变更状态
- 回答"上周库存变化"需要 Skill 实时查询，不知道数据是否已更新
- Workflow 重新运行时不知道哪些底层数据变了

### 可落地优化（映射到业务数据场景）
1. **数据变更摘要**: 为关键表（客户、库存、销售）维护 last_updated 时间戳，Copilot 回答时自动注入"数据截至 XX 时间"
2. **Workflow 增量感知**: 重新运行 business_overview 时，标注哪些数据维度相比上次发生了变化
3. **数据新鲜度标签**: Skill 结果标记数据采集时间，stale 数据自动提醒

### 优先级: **低** — 当前数据量和更新频率下影响不大

---

## 24. 安全模式匹配 Hook

### 参考来源
- `aco-main/docs/design.md` § 8.15 SecurityPatternHook
- `forge-main/pico-main/tests/test_safety_invariants.py`

### Aco/Forge 做法
- **SecurityPatternHook**: PRE_TOOL_USE 事件，7 条安全规则:
  1. eval_injection — `eval()` 执行任意代码
  2. exec_injection — `Runtime.exec()` / `ProcessBuilder`
  3. sql_injection — SQL 拼接注入
  4. rm_rf — `rm -rf /` / `rm -rf *`
  5. fork_bomb — `:(){ :|:& };:`
  6. env_file_write — 写入 .env secrets
  7. chmod_777 — 危险权限变更
- **PathBoundaryHook**: workspace 外路径 → Block
- **全面安全测试**: path_escape / symlink_traversal / risky_tool_deny / secret_redaction / env_allowlist / delegate_read_only

### LNYS 现状
- `input_guard.py` 做输入安全检查（敏感词、注入检测）
- `output_validator.py` 做输出安全检查
- 但 Skill 执行参数缺少结构化安全校验
- 无 SQL 注入模式检测（Skill 构造的查询）
- 无 secret 自动脱敏（Skill 输出可能包含敏感信息）

### 可落地优化
1. **Skill 参数安全校验**: BaseCopilotSkill.validate() 增加 SQL 注入模式检测
2. **Skill 输出脱敏**: 自动检测并遮盖手机号/身份证/银行卡等 PII 字段
3. **安全测试套件**: 参照 test_safety_invariants.py 为 Copilot 建立安全回归测试

### 优先级: **中** — 生产环境安全保障

---

## 25. 重复调用检测与行为熔断

### 参考来源
- `aco-main/docs/design.md` § 3.9 runtime _is_repeated_tool_call
- `forge-main/pico-main/pico/metrics.py` — 安全实验框架

### Aco/Forge 做法
- **重复调用检测**: 连续 3 次相同 name+args 的工具调用 → 拦截并注入引导消息
- **步数限制**: maxToolSteps（默认 50）+ maxAttempts → 防止无限循环
- **安全实验框架**: 自动化测试 path_escape / symlink / approval_deny / repeated_call 等场景，量化安全指标

### LNYS 现状
- CopilotEngine 无 Skill 重复调用检测
- Workflow 节点有 timeout 但无循环检测
- 用户可能反复问相同问题触发相同 Skill，浪费 LLM 调用

### 可落地优化
1. **Skill 重复调用检测**: CopilotEngine 记录最近 3 次 skill_name + 参数 hash，重复时返回缓存结果 + 提示
2. **Copilot 回合限制**: 单次对话最多执行 N 次 Skill（防止 LLM 陷入循环）
3. **异常行为告警**: Telemetry 记录重复调用事件，Ops Dashboard 展示

### 优先级: **中** — 防止资源浪费和异常行为

---

## 26. 双路径模型调用 (FC + 文本解析)

### 参考来源
- `aco-main/docs/design.md` § 3.9 runtime 双路径
- `forge-main/pico-main/pico/runtime.py` — XML/JSON 工具解析

### Aco/Forge 做法
- **A 路径 (FC)**: 模型支持 Function Calling → build_fc_messages() + complete_with_tools()
- **B 路径 (XML)**: 不支持 FC → 工具描述嵌入 prompt + OutputParser.parse() 解析 XML 标签
- **FC Fallback**: FC 模式下模型仍输出 XML → 回退到 XML 解析
- **好处**: 兼容所有模型（Ollama 本地模型通常不支持 FC），FC 模式结构化程度更高

### LNYS 现状
- CopilotEngine 完全依赖 Function Calling（OpenAI 兼容 API）
- 如果模型不支持 FC（如某些 Ollama 本地模型、DashScope 部分模型）→ 无法使用
- FC 调用失败时无文本解析 fallback

### 可落地优化
1. **FC 失败降级**: CopilotEngine._route_to_skill 当 FC 解析失败时，fallback 到从文本中正则提取 skill_name + arguments
2. **非 FC 模型兼容**: 对不支持 FC 的模型（如 Ollama 本地部署），用 prompt 内嵌 Skill schema + 文本输出解析
3. **模型能力探测**: ModelSelector.supports_function_calling() 自动判断，选择调用路径

### 优先级: **低** — 当前主用模型都支持 FC

---

## 27. 模型能力注册表与自动预算推导

### 参考来源
- `aco-main/docs/design.md` § 9.8 ModelCapabilities

### Aco/Forge 做法
- **ModelCapabilities 注册表**: 按模型名前缀匹配上下文窗口
  - Qwen 系列: qwen3.5-plus(1M), qwen-plus/max/turbo(128K)
  - OpenAI: gpt-4o/4o-mini(128K), o1/o3(200K)
  - Anthropic: claude-3.x/4.x(200K)
  - DeepSeek: 131K
  - 本地: llama3(8K), mistral/mixtral(32K)
- **预算公式**: context_window × 0.80（留 20% 给模型输出）
- **自动推导**: AgentConfig.auto_budget → 从模型名自动计算 ContextBudget

### LNYS 现状
- context_monitor.py ContextBudget 有 from_model() 但只支持少量模型
- token_counter.py 估算用固定比例，未按模型调整
- 切换模型时需要手动调整预算参数

### 可落地优化
1. **扩展 ModelCapabilities**: 在 config.py 或独立文件中维护完整的模型→窗口映射表
2. **自动预算推导**: ContextMonitor 初始化时从 ModelSelector.current_model 自动推导预算
3. **模型切换自适应**: 切换 COMPACT/REVIEW 模型时自动调整对应的 token 预算

### 优先级: **低** — 当前模型相对固定

---

## 落地优先级汇总

| 状态 | 参考点 | 影响 |
|------|--------|------|
| ✅ **已完成** | #8 多模型角色路由 | ModelSelector + 4 角色 + fallback |
| ✅ **已完成** | #3 统一错误处理与分级降级 | AppError 体系 + 4 层 handler + ERROR_CLASSIFIED telemetry |
| ✅ **已完成** | #12 并行子 Agent 调度 | asyncio.gather fan-out/fan-in + SSE + Telemetry |
| ✅ **已完成** | #1 上下文治理与自动压缩 | ContextMonitor 三状态机 + COMPACT 模型摘要 + 熔断 |
| ✅ **已完成** | #2 结构化分层记忆 | 三层记忆 + reconciliation + freshness + consolidator |
| ✅ **已完成** | #4 统一 Token 计数 | token_counter 单例 + truncate + budget split |
| ✅ **已完成** | #5 统一可观测性 | 16 种事件 + TelemetrySummary + Dashboard 前端 |
| ✅ **已完成** | #16 记忆新鲜度 | memory_freshness Ebbinghaus + MemoryGovernance 前端 |
| ✅ **已完成** | #14 工具输出源头裁剪 | truncate_to_budget head_tail 策略 |
| ✅ **已完成** | #11 评测框架 | EvalCenter + BenchmarkDashboard + 实验竞技场 |
| 🔲 **未做** | #9 Prompt 分段缓存 | 降低 LLM 成本 (低优先级) |
| 🔲 **未做** | #17 Agent 契约代码化 | 锦上添花 (低优先级) |
| 🟡 **部分** | #6 Hook 生命周期扩展 | 已有 pre/post hook，缺 workflow/session 级 |
| 🟡 **部分** | #7 声明式权限 | 已有 RBAC，缺参数级匹配 |
| 🟡 **部分** | #10 拦截器链 | 已有 guardrails，缺声明式链 |
| 🟡 **部分** | #13 启动编排 | main.py lifecycle 有序，缺形式化依赖图 |
| 🟡 **部分** | #15 Session 恢复增强 | 消息历史可恢复，缺记忆状态快照 |
| 🔲 **未做** | #18 阶段式工作流与门控确认 | 提升复杂决策可控性 (中优先级) |
| 🔲 **未做** | #19 Agent 模板与能力分级 | Agent 增多时规范化 (低优先级) |
| 🔲 **未做** | #20 数据读取去重与智能历史折叠 | 降低 token 消耗 (中优先级) |
| 🔲 **未做** | #21 跨 Session 项目级记忆 | 多用户场景价值大 (中优先级) |
| 🔲 **未做** | #22 Skill 按场景自动激活 | Skill >15 时收益明显 (中优先级) |
| 🔲 **未做** | #23 数据源变更感知上下文 | 数据一致性 (低优先级) |
| 🔲 **未做** | #24 安全模式匹配 Hook | 生产安全保障 (中优先级) |
| 🔲 **未做** | #25 重复调用检测与行为熔断 | 防止资源浪费 (中优先级) |
| 🔲 **未做** | #26 双路径模型调用 (FC+XML) | 模型兼容性 (低优先级) |
| 🔲 **未做** | #27 模型能力注册表 | 模型切换自适应 (低优先级) |

---

## 关键设计哲学（贯穿所有参考点）

从 Aco/Forge 项目中提炼的核心设计哲学，值得在 LNYS 所有后续开发中贯彻：

1. **分层治理 > 单点优化**: 每个问题都有基础层 / 执行层 / 智能层 / 治理层的对应解法
2. **统一接口 > 各自为战**: TokenCounter / Telemetry / ErrorHandler 这类跨切面组件必须统一
3. **可降级 > 不可用**: 每个环节都有 fallback，宁可结果质量略降也不能整体不可用
4. **可解释 > 高精度**: 轻量规则召回好过黑箱向量检索，因为出问题时能说清楚为什么
5. **稳定段前置 > 混合拼接**: Prompt 中稳定内容放前面利于缓存，动态内容放后面
6. **按需加载 > 全量暴露**: 工具 / 记忆 / 历史都应该按需加载，不是全部塞进 prompt
7. **构造顺序即依赖关系**: 组件初始化顺序就是依赖图，手动注入比魔法透明
8. **门控优于自动推进**: 关键决策点需要人类确认，不是所有步骤都应该自动执行
9. **重复是信号**: 重复的工具调用、重复的数据读取都是需要优化的信号，应检测并处理
10. **安全是不变量**: 安全规则应该有回归测试，像业务逻辑一样受版本控制和持续验证
