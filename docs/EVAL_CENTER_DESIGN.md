# 评测中心完整设计方案

> **版本**: v1.0  
> **日期**: 2026-04-12  
> **状态**: 设计阶段  
> **模型**: qwen3.5-plus-2026-02-15（支持 thinking mode）

---

## 目录

1. [系统定位与目标](#1-系统定位与目标)
2. [现状分析](#2-现状分析)
3. [三大自进化范式](#3-三大自进化范式)
4. [数据模型设计](#4-数据模型设计)
5. [后端架构设计](#5-后端架构设计)
6. [前端交互与可视化设计](#6-前端交互与可视化设计)
7. [安全边界与门控机制](#7-安全边界与门控机制)
8. [成本估算](#8-成本估算)
9. [实施路线图](#9-实施路线图)

---

## 1. 系统定位与目标

### 1.1 定位

评测中心是平台 AI 质量的**闭环保障系统**，不是一次性测试工具。它连接"智能体日志"（可观测性）→"评测引擎"（质量度量）→"自进化循环"（持续改进），形成 **观测 → 评估 → 改进 → 验证** 的完整闭环。

### 1.2 评测对象（三层）

| 层 | 组件 | 评什么 |
|---|---|---|
| **ML Agent 层** | 7 个 BaseAgent（customer/forecast/fraud/sentiment/inventory/association/openclaw） | 模型精度、延迟、输出 schema 合规 |
| **Copilot Skill 层** | 11 个 BaseCopilotSkill（inventory/forecast/sentiment/customer_intel/fraud/association/kb_rag/memory/trace/system/ocr） | LLM 路由准确率、回答质量、工具调用正确性、幻觉检测 |
| **Workflow 层** | SupervisorAgent → Orchestrator → DAG | 端到端任务完成率、路由准确率、多步编排正确性 |

### 1.3 设计目标

- **真实评测**：替换现有 mock 实现，通过 `AgentGateway.call()` 和 `BaseCopilotSkill.execute()` 真实调用 Agent
- **自主进化**：三种范式（爬山法 / Prompt 自进化 / 轨迹记忆）让 Agent 持续变好
- **安全可控**：越危险的改动，人工介入越多；所有变更可回滚、可审计
- **比赛级前端**：展示技术深度（Canvas/WebGL/Wasm/SSE Thinking/d3-force）

---

## 2. 现状分析

### 2.1 已有基础设施

| 组件 | 文件 | 状态 |
|---|---|---|
| 评测数据库表 | `backend/db/init.sql` (eval_datasets/eval_cases/evaluators/eval_experiments/eval_results/eval_online_samples) | ✅ 已建表 |
| 后端 API | `backend/routers/admin/evals.py` (CRUD + run_experiment) | ✅ 骨架完成 |
| 评测引擎 | `backend/governance/eval_center/eval_service.py` | ❌ 全是 mock（随机打分） |
| 前端页面 | `frontend/src/views/console/ConsoleEvals.vue` | ❌ 只有实验 Tab 有 mock UI |
| 前端 API | `frontend/src/api/admin/evals.js` | ✅ 接口定义完成 |
| 前端 Adapter | `frontend/src/adapters/evals.js` | ✅ 数据转换完成 |
| Agent 调用 | `backend/agents/gateway.py` (AgentGateway.call) | ✅ 可直接复用 |
| Skill 调用 | `backend/copilot/base_skill.py` (BaseCopilotSkill.execute) | ✅ 可直接复用 |
| Trace 系统 | `backend/routers/admin/traces.py` + ConsoleTraces.vue | ✅ 完整可用 |
| 记忆系统 | `backend/copilot/context.py` (3 层记忆) | ✅ 可扩展 |
| Skill 配置覆盖 | `copilot_skill_overrides` 表 | ✅ 可存 prompt 版本 |
| 定时调度 | `CopilotPatrolScheduler` (APScheduler) | ✅ 可添加评测任务 |
| 飞书告警 | `FeishuBridge` | ✅ 可发告警卡片 |

### 2.2 核心缺失

| 缺失 | 影响 |
|---|---|
| 评测引擎是 mock | 不能真实评估 Agent 质量 |
| Trace → Dataset 无桥梁 | 不能从生产日志积累 golden set |
| 无 LLM-as-Judge | 不能评估生成式输出质量 |
| 无 Prompt 版本管理 | 不能做 prompt 自进化 |
| 无 Tip 提取/存储/检索 | 不能做轨迹记忆学习 |
| 前端数据集/评估器 Tab 空 | 运营不可用 |

---

## 3. 三大自进化范式

### 3.1 范式一：Karpathy Loop（ML Agent 指标爬山）

**来源**: Andrej Karpathy `autoresearch` (2026.03)

**适用对象**: 7 个 ML Agent（fraud/forecast/customer/sentiment/inventory/association/openclaw）

**原理**: 单指标爬山 + 自动回滚

```
while budget > 0:
    1. 修改 Agent 参数（threshold/weight/config）
    2. 跑 golden set（通过 AgentGateway.call）
    3. 计算指标（accuracy/precision/recall/MAE）
    4. if 指标变好 → KEEP（记录新参数）
       else → DISCARD（回滚到上次最优）
    5. 记录到 experiment_log
```

**核心特征**:
- **评估器不可变** — Agent 不能改评估逻辑
- **git 语义回滚** — 每次参数变更有版本号，可精确回退
- **时间预算** — 每轮实验有时间上限，保证可比性
- **零 LLM 成本** — 全是本地模型 + 代码断言

**在本系统中的实现路径**:
- Agent 参数存储在 Redis/DB 中，每次修改记录版本
- 评测通过 `AgentGateway.call(agent, input_data)` 真实调用
- 评分用 Code-Based Evaluator（exact_match/field_match/threshold_check）
- 实验日志写入 `eval_experiments` + `eval_results`

### 3.2 范式二：Self-Evolving Agent（Copilot Skill Prompt 自进化）

**来源**: OpenAI Cookbook `self_evolving_agents` (2025.11)

**适用对象**: 11 个 Copilot Skill

**原理**: 多 Grader 评估 + MetapromptAgent 自动优化 prompt + 版本管理

```
for case in golden_set:
    for attempt in range(max_retry):  # max_retry = 3
        1. Skill 执行 → 生成输出
        2. 4 个 Grader 并行评分:
           - Schema 校验（Code-Based）
           - 关键信息保留（Code-Based）
           - 语义相似度（Embedding）
           - LLM-as-Judge（综合质量）
        3. 聚合分数 → is_lenient_pass?
        4. if PASS → 记录，下一条
           if FAIL → 收集失败 Grader 的 reasoning
             → MetapromptAgent 分析原因 + 生成改进 prompt
             → VersionedPrompt.update()
             → 用新 prompt 重试
    if all_attempts_failed → alert 人工介入
best_prompt = select_best_aggregate()
await human_approval() → 上线
```

**核心组件**:

```python
# Prompt 版本管理（对应 copilot_skill_overrides 表）
class PromptVersionEntry:
    version: int              # 版本号
    prompt: str               # prompt 文本
    model: str                # 模型名
    timestamp: datetime       # 创建时间
    eval_id: str              # 关联评测实验 ID
    scores: dict              # 各 grader 分数
    metadata: dict            # 元数据

class VersionedPrompt:
    def update(new_prompt) → PromptVersionEntry   # 新版本
    def current() → PromptVersionEntry            # 当前版本
    def revert_to(version) → PromptVersionEntry   # 回滚
    def history() → list[PromptVersionEntry]       # 历史
```

**4 种 Grader 设计**:

| Grader | 类型 | 阈值 | 评什么 |
|---|---|---|---|
| schema_check | Code-Based | 1.0 | 输出是否包含必要字段 |
| key_info_retention | Code-Based | 0.8 | tool_result 关键数据是否被引用 |
| semantic_similarity | Embedding | 0.85 | 输出与参考答案的语义相似度 |
| llm_judge | LLM (qwen3.5 thinking) | 0.85 | 综合质量: 准确性/忠实性/有用性/简洁性 |

**MetapromptAgent 设计**:

```python
METAPROMPT_TEMPLATE = """
# 上下文
## 原始 Prompt:
{original_prompt}

## 用户问题:
{question}

## Skill 输出:
{skill_output}

## tool_result 原始数据:
{tool_result}

## 失败原因（来自 Grader）:
{grader_feedback}

# 任务
写一个改进版的 Skill prompt，要求：
1. 直接修复 Grader 指出的问题
2. 保持原 prompt 的核心职责不变
3. 增加具体约束而非泛泛而谈
4. 输出格式保持兼容
"""
```

**安全门控**:
- Lenient Pass: 75% grader 通过 + 平均分 ≥ 0.85
- max_retry = 3，超过后停止并告警
- 最终 prompt 需人工审批才上线
- 所有版本可一键回滚

### 3.3 范式三：Trajectory-Informed Memory（轨迹记忆自学习）

**来源**: IBM 论文 *Trajectory-Informed Memory Generation for Self-Improving Agent Systems* (2026.03)

**适用对象**: 所有 Workflow 执行轨迹

**原理**: 从执行轨迹中提取结构化 Tips → 管理去重 → 运行时语义检索注入

**Phase 1: Trajectory → Tips**

```
Agent 完成一次任务（trace 写入 DB）
  → Trajectory Intelligence Extractor:
      - 解析 trace 中每一步的输入/输出/状态
      - 识别 4 类认知模式：分析、规划、校验、反思
      - 判定结果类型：干净成功 / 低效成功 / 失败后恢复 / 彻底失败
  → Decision Attribution Analyzer:
      - 因果分析：哪个决策导致了当前结果
      - 区分：直接原因 / 近因 / 根因 / 贡献因素
  → Contextual Learning Generator:
      - 生成 3 种 Tip:
        ├─ Strategy Tip（来自干净成功）: "做 X 任务时，先验证 Y 前置条件"
        ├─ Recovery Tip（来自失败恢复）: "当 X 失败时，尝试 Y 降级方案"
        └─ Optimization Tip（来自低效成功）: "用批量 API 替代循环调用"
```

**Phase 2: Tips 管理**

```
新 Tip 进入 → 泛化处理:
  - 实体抽象: "查询张三的订单" → "查询客户订单"
  - 动作归一化: "获取/拿到/检索" → 统一动词
  - 上下文剥离: 去掉任务特定限定词
→ 语义聚类:
  - 向量嵌入 → cosine similarity ≥ 0.85 归同簇
→ 簇内合并:
  - LLM 合并重复/重叠的 tips → 一条高质量指导
→ 双重存储:
  - 向量嵌入（语义检索）
  - 结构化元数据（类型/来源/置信度/引用次数）
```

**Phase 3: Runtime 注入**

```
新任务来了 → 检索相关 Tips:
  - 快速模式: cosine similarity 检索（0 LLM 调用，推荐）
    - threshold ≥ 0.6, top-k = 5
  - 精准模式: LLM 引导选择（多 1 次 LLM 调用）
    - 理解任务上下文 → 筛选最相关 tips
→ 注入 prompt 的 [Guidelines] 段
→ Agent 执行时参考这些 tips
```

**Tips 数据结构**:

```python
class AgentTip(BaseModel):
    tip_id: str                    # 唯一 ID
    tip_type: Literal["strategy", "recovery", "optimization"]
    content: str                   # Tip 正文
    trigger: str                   # 触发条件描述
    steps: list[str]               # 具体操作步骤
    source_trace_id: str           # 来源 trace run_id
    source_task_type: str          # 来源任务类型
    generalized_description: str   # 泛化后的描述（用于聚类）
    embedding: list[float]         # 向量嵌入
    confidence: float              # 置信度 0-1
    reference_count: int           # 被引用次数
    cluster_id: Optional[str]      # 所属聚类
    is_active: bool                # 是否启用
    created_at: datetime
    updated_at: datetime
```

---

## 4. 数据模型设计

### 4.1 现有表（保持不变）

- `eval_datasets` — 数据集
- `eval_cases` — 测试用例
- `evaluators` — 评估器
- `eval_experiments` — 实验
- `eval_results` — 实验结果
- `eval_online_samples` — 线上样本

### 4.2 扩展字段

```sql
-- eval_cases 增加 target 类型
ALTER TABLE eval_cases ADD COLUMN target_type VARCHAR(32)
  COMMENT '"ml_agent"|"copilot_skill"|"workflow"|"supervisor"';
ALTER TABLE eval_cases ADD COLUMN target_id VARCHAR(64)
  COMMENT 'e.g. "fraud_agent"|"fraud_skill"|"business_overview"';

-- eval_experiments 增加版本对比
ALTER TABLE eval_experiments ADD COLUMN target_version VARCHAR(64)
  COMMENT '被测对象版本标识';
ALTER TABLE eval_experiments ADD COLUMN baseline_experiment_id VARCHAR(36)
  COMMENT '对比基线实验 ID';

-- eval_results 增加 grader 详情
ALTER TABLE eval_results ADD COLUMN grader_scores JSON
  COMMENT '各 grader 的独立分数';
ALTER TABLE eval_results ADD COLUMN grader_reasoning JSON
  COMMENT '各 grader 的推理过程（含 thinking tokens）';
ALTER TABLE eval_results ADD COLUMN actual_output JSON
  COMMENT 'Agent/Skill 的实际输出';
```

### 4.3 新增表

```sql
-- Prompt 版本历史
CREATE TABLE eval_prompt_versions (
  id            VARCHAR(36) PRIMARY KEY,
  skill_name    VARCHAR(64) NOT NULL COMMENT 'Skill 名称',
  version       INT NOT NULL COMMENT '版本号',
  prompt_text   TEXT NOT NULL COMMENT 'prompt 全文',
  model_name    VARCHAR(64) COMMENT '模型名',
  eval_id       VARCHAR(36) COMMENT '关联实验 ID',
  avg_score     DECIMAL(5,4) COMMENT '该版本平均分',
  grader_scores JSON COMMENT '各 grader 分数快照',
  status        ENUM('draft','testing','approved','active','rolled_back')
                DEFAULT 'draft',
  approved_by   VARCHAR(64) COMMENT '审批人',
  approved_at   DATETIME COMMENT '审批时间',
  metadata      JSON,
  created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_skill_version (skill_name, version),
  INDEX idx_status (status)
) COMMENT='Copilot Skill prompt 版本历史';

-- 轨迹记忆 Tips
CREATE TABLE eval_agent_tips (
  tip_id            VARCHAR(36) PRIMARY KEY,
  tip_type          ENUM('strategy','recovery','optimization') NOT NULL,
  content           TEXT NOT NULL COMMENT 'Tip 正文',
  trigger_desc      TEXT COMMENT '触发条件',
  steps             JSON COMMENT '具体步骤',
  source_trace_id   VARCHAR(36) COMMENT '来源 trace',
  source_task_type  VARCHAR(64) COMMENT '来源任务类型',
  generalized_desc  TEXT COMMENT '泛化描述（用于聚类）',
  cluster_id        VARCHAR(36) COMMENT '所属聚类 ID',
  confidence        DECIMAL(3,2) DEFAULT 0.50,
  reference_count   INT DEFAULT 0 COMMENT '被引用次数',
  is_active         TINYINT(1) DEFAULT 1,
  created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at        DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_type (tip_type),
  INDEX idx_cluster (cluster_id),
  INDEX idx_active (is_active),
  INDEX idx_task_type (source_task_type)
) COMMENT='轨迹记忆 Tips';

-- Tips 向量索引（存在 Redis 或 PostgreSQL pgvector 中）
-- embedding 存储方案见 5.5 节

-- 实验循环日志（Karpathy Loop 风格）
CREATE TABLE eval_loop_log (
  id              VARCHAR(36) PRIMARY KEY,
  experiment_id   VARCHAR(36) NOT NULL,
  iteration       INT NOT NULL COMMENT '轮次',
  change_desc     TEXT COMMENT '本轮变更描述',
  params_snapshot JSON COMMENT '参数快照',
  metric_name     VARCHAR(64) COMMENT '指标名',
  metric_before   DECIMAL(10,6) COMMENT '变更前指标',
  metric_after    DECIMAL(10,6) COMMENT '变更后指标',
  decision        ENUM('keep','discard','crash') NOT NULL,
  duration_ms     INT COMMENT '本轮耗时',
  created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_exp_iter (experiment_id, iteration)
) COMMENT='实验循环日志（爬山法）';
```

---

## 5. 后端架构设计

### 5.1 模块结构

```
backend/governance/eval_center/
├── eval_service.py           # 评测引擎主逻辑（重写）
├── runners/
│   ├── __init__.py
│   ├── base_runner.py        # Runner 基类
│   ├── ml_agent_runner.py    # ML Agent 执行器（调 AgentGateway）
│   ├── skill_runner.py       # Copilot Skill 执行器（调 BaseCopilotSkill.execute）
│   ├── supervisor_runner.py  # Supervisor 路由测试
│   └── workflow_runner.py    # 端到端 Workflow 执行器
├── graders/
│   ├── __init__.py
│   ├── base_grader.py        # Grader 基类
│   ├── code_grader.py        # Code-Based (exact_match/field_match/schema_check/threshold)
│   ├── llm_judge_grader.py   # LLM-as-Judge (qwen3.5 thinking mode)
│   ├── embedding_grader.py   # 语义相似度
│   └── trace_grader.py       # 链路级评估
├── evolution/
│   ├── __init__.py
│   ├── karpathy_loop.py      # 范式一：爬山法循环
│   ├── prompt_evolver.py     # 范式二：Prompt 自进化
│   ├── versioned_prompt.py   # Prompt 版本管理
│   └── metaprompt_agent.py   # MetapromptAgent（优化 prompt 的 Agent）
├── memory/
│   ├── __init__.py
│   ├── tip_extractor.py      # 范式三 Phase1：从 trace 提取 Tips
│   ├── tip_manager.py        # 范式三 Phase2：Tips 泛化/聚类/合并
│   ├── tip_retriever.py      # 范式三 Phase3：运行时检索
│   └── tip_injector.py       # Tips 注入 prompt
└── scheduler.py              # 定时评测任务（接入 CopilotPatrolScheduler）
```

### 5.2 Runner 基类

```python
class BaseRunner(ABC):
    """评测执行器基类"""

    @abstractmethod
    async def run(self, case: EvalCase) -> RunnerResult:
        """执行单条测试用例，返回 actual_output"""
        ...

class RunnerResult(BaseModel):
    actual_output: dict          # Agent/Skill 实际输出
    latency_ms: int              # 执行耗时
    tokens_used: int = 0         # token 消耗
    error: Optional[str] = None  # 错误信息
    trace_id: Optional[str] = None  # 关联 trace ID
    metadata: dict = {}
```

**ML Agent Runner**:
```python
class MLAgentRunner(BaseRunner):
    async def run(self, case):
        agent = app.state.__dict__.get(case.target_id)
        result = await AgentGateway.call(agent, case.input_json, timeout=30)
        return RunnerResult(actual_output=result, ...)
```

**Skill Runner**:
```python
class SkillRunner(BaseRunner):
    async def run(self, case):
        skill = SkillRegistry.instance().get(case.target_id)
        context = SkillContext(user_id="eval", mode="ops", ...)
        events = []
        async for event in skill.execute(case.input_json["question"], context):
            events.append(event.to_dict())
        return RunnerResult(actual_output={"events": events}, ...)
```

### 5.3 Grader 基类

```python
class BaseGrader(ABC):
    """评分器基类"""

    @abstractmethod
    async def grade(
        self,
        case: EvalCase,
        actual_output: dict,
        evaluator_config: dict,
    ) -> GraderResult:
        ...

class GraderResult(BaseModel):
    score: float              # 0.0 - 1.0
    passed: bool              # PASS/FAIL
    reasoning: Optional[str]  # 推理过程（LLM Judge 的 thinking）
    grader_name: str          # 评分器名称
    metadata: dict = {}
```

**LLM Judge Grader（利用 qwen3.5 thinking mode）**:
```python
class LLMJudgeGrader(BaseGrader):
    JUDGE_PROMPT = """你是一个 AI 输出质量评审员。

## 评估维度
- Groundedness（忠实性）：回答是否基于提供的 tool_result，有无幻觉
- Task Completion（任务完成度）：是否真正完成用户要求
- Answer Quality（回答质量）：相关性、完整性、准确性、简洁度
- Tool Consistency（工具一致性）：tool_result 数据与最终总结是否一致

## 输入
用户问题: {question}
tool_result: {tool_result}
AI 回答: {actual_output}
参考答案（如有）: {expected_output}

## 输出格式（JSON）
{{
  "verdict": "PASS" | "FAIL",
  "score": 0.0-1.0,
  "reasoning": "详细分析..."
}}
"""

    async def grade(self, case, actual_output, evaluator_config):
        response = await llm.ainvoke(
            self.JUDGE_PROMPT.format(...),
            model="qwen3.5-plus-2026-02-15",
            enable_thinking=True,  # 启用思考模式
        )
        # 解析 thinking + output
        thinking = response.thinking_content  # 思考过程
        result = json.loads(response.content)
        return GraderResult(
            score=result["score"],
            passed=result["verdict"] == "PASS",
            reasoning=thinking + "\n---\n" + result["reasoning"],
        )
```

### 5.4 Prompt 自进化引擎

```python
class PromptEvolver:
    """Copilot Skill Prompt 自进化引擎"""

    def __init__(self, skill_name: str, golden_set: list[EvalCase]):
        self.skill_name = skill_name
        self.golden_set = golden_set
        self.versioned_prompt = VersionedPrompt(
            skill_name=skill_name,
            initial_prompt=self._load_current_prompt(),
        )
        self.graders = [
            SchemaCheckGrader(),
            KeyInfoRetentionGrader(),
            EmbeddingSimilarityGrader(),
            LLMJudgeGrader(),
        ]
        self.metaprompt_agent = MetapromptAgent()

    async def evolve(self, max_retry=3) -> EvolutionResult:
        """运行一轮完整的自进化循环"""
        results = []

        for case in self.golden_set:
            case_passed = False

            for attempt in range(max_retry):
                # 1. 用当前 prompt 执行 Skill
                runner = SkillRunner(prompt=self.versioned_prompt.current().prompt)
                run_result = await runner.run(case)

                # 2. 多 Grader 评分
                grader_results = await asyncio.gather(*[
                    g.grade(case, run_result.actual_output, {})
                    for g in self.graders
                ])

                # 3. 聚合判定
                avg_score = mean([g.score for g in grader_results])
                passed_ratio = sum(1 for g in grader_results if g.passed) / len(grader_results)
                lenient_pass = passed_ratio >= 0.75 and avg_score >= 0.85

                if lenient_pass:
                    case_passed = True
                    break

                # 4. 失败 → MetapromptAgent 优化 prompt
                feedback = self._collect_feedback(grader_results)
                new_prompt = await self.metaprompt_agent.optimize(
                    original_prompt=self.versioned_prompt.current().prompt,
                    question=case.input_json.get("question"),
                    skill_output=run_result.actual_output,
                    grader_feedback=feedback,
                )
                self.versioned_prompt.update(
                    new_prompt=new_prompt,
                    eval_scores={g.grader_name: g.score for g in grader_results},
                )

                # yield SSE event: prompt_evolved（前端实时展示）

            results.append(CaseEvolutionResult(case=case, passed=case_passed, attempts=attempt+1))

        # 选择最优版本
        best = self.versioned_prompt.select_best()
        return EvolutionResult(
            skill_name=self.skill_name,
            best_version=best,
            case_results=results,
            status="pending_approval",  # 等待人工审批
        )
```

### 5.5 轨迹记忆引擎

```python
class TipExtractor:
    """Phase 1: 从 trace 提取 Tips"""

    EXTRACTION_PROMPT = """分析以下 Agent 执行轨迹，提取可复用的经验教训。

## 轨迹信息
任务类型: {workflow_name}
状态: {status}
步骤:
{steps_formatted}

## 输出格式（JSON 数组）
[
  {{
    "tip_type": "strategy|recovery|optimization",
    "content": "简洁的经验描述",
    "trigger": "何时应用此经验",
    "steps": ["具体操作步骤1", "步骤2"],
    "confidence": 0.0-1.0
  }}
]

## 提取规则
- strategy: 来自干净成功的执行，提取有效策略
- recovery: 来自失败后恢复的执行，提取恢复模式
- optimization: 来自低效成功的执行，提取优化建议
- 只提取可泛化的经验，不要包含具体的用户名、ID 等
"""

    async def extract(self, trace: TraceDetail) -> list[AgentTip]:
        response = await llm.ainvoke(
            self.EXTRACTION_PROMPT.format(...),
            enable_thinking=True,
        )
        tips = json.loads(response.content)
        return [AgentTip(**tip, source_trace_id=trace.run_id) for tip in tips]


class TipRetriever:
    """Phase 3: 运行时检索 Tips"""

    async def retrieve(self, task_description: str, top_k=5, threshold=0.6) -> list[AgentTip]:
        """Cosine similarity 快速检索"""
        query_embedding = await embed(task_description)
        # 从 Redis/pgvector 检索
        results = await vector_store.search(
            query_embedding, top_k=top_k, threshold=threshold
        )
        return results


class TipInjector:
    """将 Tips 注入 prompt"""

    def inject(self, base_prompt: str, tips: list[AgentTip]) -> str:
        if not tips:
            return base_prompt
        guidelines = "\n".join([
            f"- [{t.tip_type}] {t.content}" for t in tips
        ])
        return f"{base_prompt}\n\n【历史经验指南】\n{guidelines}"
```

### 5.6 定时任务

```python
# 在 CopilotPatrolScheduler 中新增评测任务

# 每天凌晨 2:00 — ML Agent 回归测试（范式一）
scheduler.add_job(
    run_ml_agent_regression, 'cron', hour=2, minute=0,
    id='eval_ml_regression', replace_existing=True,
)

# 每天凌晨 3:00 — 从昨日 trace 提取 Tips（范式三）
scheduler.add_job(
    extract_daily_tips, 'cron', hour=3, minute=0,
    id='eval_tip_extraction', replace_existing=True,
)

# 每周日凌晨 4:00 — Tips 聚类合并（范式三）
scheduler.add_job(
    consolidate_tips, 'cron', day_of_week='sun', hour=4,
    id='eval_tip_consolidation', replace_existing=True,
)

# 每周一凌晨 5:00 — Skill Prompt 回归检测（范式二）
scheduler.add_job(
    run_skill_regression, 'cron', day_of_week='mon', hour=5,
    id='eval_skill_regression', replace_existing=True,
)
```

### 5.7 SSE 事件协议（前端实时展示）

```python
# 新增评测专用 SSE 事件类型
class EvalEventType(str, Enum):
    # Karpathy Loop
    LOOP_ITERATION_START = "eval:loop_iter_start"   # 新一轮实验开始
    LOOP_ITERATION_END = "eval:loop_iter_end"       # 一轮结束（keep/discard/crash）
    LOOP_METRIC_UPDATE = "eval:loop_metric"         # 指标更新
    LOOP_COMPLETE = "eval:loop_complete"             # 循环结束

    # Prompt Evolution
    SKILL_EXEC_START = "eval:skill_exec_start"      # Skill 开始执行
    SKILL_EXEC_RESULT = "eval:skill_exec_result"    # Skill 执行结果
    GRADER_SCORE = "eval:grader_score"              # 单个 Grader 评分完成
    GRADER_ALL_DONE = "eval:grader_all_done"        # 所有 Grader 评分完成
    PROMPT_THINKING = "eval:prompt_thinking"         # MetapromptAgent 思考中（thinking tokens）
    PROMPT_EVOLVED = "eval:prompt_evolved"           # 新 prompt 生成
    EVOLUTION_COMPLETE = "eval:evolution_complete"   # 进化循环完成

    # Trajectory Memory
    TIP_EXTRACTED = "eval:tip_extracted"             # 新 Tip 提取完成
    TIP_INJECTED = "eval:tip_injected"              # Tip 被注入使用
    MEMORY_CONSOLIDATED = "eval:memory_consolidated" # 记忆合并完成
```

---

## 6. 前端交互与可视化设计

### 6.1 页面结构

```
ConsoleEvals.vue (重写)
├── Tab 1: 实验竞技场 (ExperimentArena)
│   ├── AgentSelector — 选择被测 Agent
│   ├── HillClimbChart — Canvas 爬山曲线
│   ├── ExperimentTimeline — Git-style 提交历史
│   └── LiveExecutionPanel — 实时执行进度
│
├── Tab 2: Prompt 进化链 (PromptEvolution)
│   ├── SkillSelector — 选择被测 Skill
│   ├── PromptVersionTimeline — 水平版本轴 + 里程表分数
│   ├── GraderRadarChart — SVG 四维雷达图（spring 变形）
│   ├── ThinkingStream — MetapromptAgent 思考流（SSE + thinking block）
│   ├── PromptDiffPanel — Wasm char-level diff
│   └── ApprovalCard — HITL 审批卡片
│
├── Tab 3: 轨迹记忆网络 (TrajectoryMemory)
│   ├── MemoryForceGraph — d3-force 力导向图
│   ├── TipDetailCard — Tip 详情（含溯源到 trace）
│   ├── InjectionMonitor — 实时注入监控
│   └── MemoryGrowthChart — 记忆增长面积图
│
└── Tab 4: 趋势总览 (TrendDashboard)
    ├── PassRateHeatmap — Agent pass_rate 热力图
    ├── RegressionAlert — 回归告警
    └── CostTracker — 成本追踪
```

### 6.2 Tab 1: 实验竞技场（Karpathy Loop）

#### 交互流程

```
1. 用户选择 Agent (dropdown) → 选择 golden set (dropdown)
2. 点击 "开始实验循环" → 设置参数（轮次上限、时间预算）
3. SSE 连接建立 → 实时推送每轮结果
4. 每轮显示：
   - HillClimbChart: 新点弹入（KEEP）或抖出（DISCARD）
   - ExperimentTimeline: 新条目滑入
   - LiveExecutionPanel: 进度条 + 当前 case
5. 循环结束 → 显示最优参数 + 总结
```

#### 核心组件规格

**HillClimbChart（Canvas 实时曲线）**:
- 技术: 原生 Canvas 2D（不用 ECharts，展示底层能力）
- 尺寸: 100% 宽 × 280px 高
- X 轴: 实验轮次（自动扩展）
- Y 轴: 指标值（auto scale）
- KEEP 点: `--v2-text-1` 实心圆，spring 弹入动画（duration 400ms, bounce 1.2）
- DISCARD 点: `--v2-error` 空心圆 + 叉号，shake 动画（duration 200ms）后淡出
- 连线: KEEP→KEEP 实线，KEEP→DISCARD 虚线分叉
- 当前最优: 水平虚线 + 右侧标签
- hover 某点: tooltip 显示该轮详情

**ExperimentTimeline（Git-style）**:
- 左侧竖线连接各节点（实线=keep，虚线断开=discard）
- 每个节点: 状态圆点 + 变更描述 + 指标变化 + 耗时
- KEEP 节点绿色圆点，DISCARD 红色叉号
- 最新节点在顶部，滚动加载历史
- 点击节点 → 右侧展开参数 diff

**LiveExecutionPanel**:
- 当前轮次 + 进度条（CSS transition width）
- 已完成/总共 case 数
- 预估剩余时间
- 实时 token 消耗

#### 里程表数字动画（Odometer）

```vue
<!-- 机械滚轮数字，展示当前最优指标 -->
<OdometerNumber :value="bestMetric" :decimals="4" />
```

- 每位数字独立滚轮，CSS transform + transition
- 数字变化时向上或向下滚动到新值
- monochrome，Geist Mono 字体

### 6.3 Tab 2: Prompt 进化链（Self-Evolving）

#### 交互流程

```
1. 用户选择 Skill → 看到当前 prompt 版本和分数历史
2. 点击 "启动进化" → 选择 golden set → 设置 max_retry
3. SSE 流式展示:
   a. Skill 执行 → 输出气泡
   b. 4 个 Grader 逐个亮灯 → 雷达图变形
   c. 如失败 → ThinkingStream 展示 MetapromptAgent 思考
   d. 新 prompt → DiffPanel 对比
   e. 重试 → 雷达图再次变形
4. 循环结束 → ApprovalCard 审批
5. 审批通过 → prompt 上线 → 版本轴新增节点
```

#### 核心组件规格

**PromptVersionTimeline（水平版本轴）**:
- 水平滚动，每个版本节点:
  - 版本号 (v0, v1, v2...)
  - 里程表数字显示 avg_score
  - 节点颜色: active=绿色呼吸灯, testing=黄色, rolled_back=灰色
- 点击任意两个节点 → 弹出 Diff
- 最新版本右侧显示状态 badge（draft/testing/approved/active）

**GraderRadarChart（SVG 四维雷达图）**:
- 技术: SVG path + CSS transition
- 4 个维度: Schema / 忠实性 / 完整性 / 质量
- 每次评分完成 → 雷达形状 spring 弹性变形到新值
- 失败维度: 对应轴变红 + pulse 动画
- 旧形状半透明保留对比

**ThinkingStream（MetapromptAgent 思考流）**:
- 复用 `CopilotThinkingBlock` 组件
- SSE 流式接收 thinking tokens
- 思考过程用缩进 + 灰色背景展示
- 最终 prompt 输出后自动切换到 DiffPanel
- █ 闪烁光标（已有）

**PromptDiffPanel（Wasm char-level diff）**:
- 左右并排: 旧版本 vs 新版本
- 增加的行: `--v2-success-bg` 背景
- 删除的行: `--v2-error-bg` 背景
- 修改的行内: char-level 高亮差异字符
- 技术: Wasm diff 模块（如已实现）或 js-diff 降级

**ApprovalCard（HITL 审批）**:
- 固定在底部的卡片，进化完成后滑入
- 显示: skill_name, v_old → v_new, pass_rate 变化
- 3 个按钮: 查看 Diff / 批准上线 / 回滚
- 批准后: 写入 `eval_prompt_versions`(status=approved) + `copilot_skill_overrides`

### 6.4 Tab 3: 轨迹记忆网络（Trajectory Memory）

#### 交互流程

```
1. 进入页面 → 看到力导向图（Tips 聚类网络）
2. 网络持续有"粒子飞入"动画（模拟 Tips 持续积累）
3. 点击聚类节点 → 展开内部 Tips 列表
4. 点击具体 Tip → TipDetailCard（含溯源到 trace 链接）
5. 可手动启用/禁用某条 Tip
6. 右侧面板: InjectionMonitor 实时显示哪些 Tips 正在被使用
7. 底部: MemoryGrowthChart 展示记忆增长趋势
```

#### 核心组件规格

**MemoryForceGraph（d3-force 力导向图）**:
- 技术: d3-force + Canvas 渲染（大数据量用 Canvas，不用 SVG）
- 节点: 每个聚类一个圆，半径 ∝ 内部 Tip 数量
- 边: 聚类间语义关联强度，线宽 ∝ 关联度
- 颜色: monochrome 灰度，不同 tip_type 用不同灰度
  - Strategy: `--v2-text-2`
  - Recovery: `--v2-text-3`
  - Optimization: `--v2-text-4`
- 交互:
  - 拖拽节点 → 其他节点物理响应
  - hover 节点 → 显示聚类名 + Tip 数量
  - 点击节点 → 展开为多个子节点（单个 Tips）
- 动画:
  - 新 Tip 进入: 粒子从边缘飞入 → 被最近聚类吸附（magnetic physics）
  - 聚类合并: 两个节点弹性靠近 → 融合为一个更大节点

**TipDetailCard（Tip 详情）**:
- 侧栏 Drawer 展开
- 内容: tip_type badge + content + trigger + steps
- 溯源: "来源 trace" 链接 → 点击跳转到 ConsoleTraceDetail
- 统计: 置信度 + 引用次数
- 操作: 启用/禁用 toggle + 手动编辑

**InjectionMonitor（实时注入监控）**:
- 右侧面板，实时 SSE 接收 `eval:tip_injected` 事件
- 每次 Copilot 对话发起时，显示:
  - 用户问题
  - 匹配到的 Tips（分数排序）
  - 注入位置和 token 增量
- 最近 20 条注入记录滚动列表

**MemoryGrowthChart（面积图）**:
- 技术: Canvas 面积图
- X 轴: 日期
- Y 轴: Tips 数量
- 三层堆叠: Strategy / Recovery / Optimization
- 灰度区分（深→浅）
- hover 某天 → tooltip 显示当天新增 top3 Tips

### 6.5 Tab 4: 趋势总览

**PassRateHeatmap**:
- 行: Agent/Skill 名称
- 列: 周/日
- 单元格: 灰度深浅表示 pass_rate（越深越好）
- 回归标记: 分数下降的格子红色边框 pulse
- 点击格子 → 跳转到对应实验详情

**CostTracker**:
- 4 个统计卡: LLM 调用次数/成本、Agent 调用次数、Tips 生成数、总计
- 月度趋势迷你折线图

### 6.6 通用动画规范

| 动画 | 参数 | 使用场景 |
|---|---|---|
| Spring 弹入 | duration: 400ms, bounce: 1.15 | 新数据点、雷达图变形 |
| Shake 抖动 | duration: 200ms, amplitude: 4px | DISCARD、FAIL |
| Fade 淡出 | duration: 300ms, opacity: 0→1 | 新卡片、新节点 |
| Slide 滑入 | duration: 350ms, transform: translateY | Timeline 新条目、Drawer |
| Pulse 呼吸 | duration: 2000ms, opacity: 0.5↔1 | 当前最优、活跃状态 |
| Odometer 滚轮 | duration: 600ms, per-digit | 数字变化 |
| Magnetic 吸附 | duration: 800ms, easing: spring | Tips 飞入聚类 |

所有动画使用 CSS `transition` 或 `@keyframes`，不用 JS requestAnimationFrame（除 Canvas）。

---

## 7. 安全边界与门控机制

### 7.1 安全层级

```
                     自动化程度 ↑
                          │
  第五层  ML 模型再训练     │  ← Shadow + Canary + 人工审批（暂不实现）
  第四层  路由规则调整       │  ← Sandbox + 人工确认
  第三层  Prompt 优化        │  ← A/B 评测 + 人工审批 + 自动回滚
  ─────────────────────────│──── 以上需要人工门控 ──────
  第二层  Golden Set 积累   │  ← 人工标注，安全
  第一层  记忆/Tips 积累    │  ← 全自动，安全
                          │
                     安全性 ↑
```

### 7.2 不可变规则

| 规则 | 说明 |
|---|---|
| **评估器不可被评测对象修改** | Agent 不能改 Grader 逻辑 |
| **Tips 不改代码** | Tips 只注入 prompt，不修改 Agent 源代码 |
| **Prompt 变更需审批** | 自动生成的 prompt 需人工确认才上线 |
| **所有变更可回滚** | VersionedPrompt 支持一键回退到任意历史版本 |
| **审计日志完整** | 每次变更记录 who/when/why/diff |
| **pass_rate 门槛** | 新版本 pass_rate 必须 ≥ 旧版本才允许上线 |

### 7.3 自动回滚触发条件

```python
# 上线后 24h 内，如果检测到回归，自动回滚
if new_pass_rate < old_pass_rate - REGRESSION_THRESHOLD:
    await rollback_prompt(skill_name, to_version=previous)
    await feishu_alert(f"[评测中心] {skill_name} prompt v{new} 回归，已自动回滚到 v{old}")
```

### 7.4 飞书告警集成

| 事件 | 告警级别 | 发送目标 |
|---|---|---|
| ML Agent pass_rate 低于阈值 | 🔴 紧急 | 运维群 |
| Skill prompt 进化完成待审批 | 🟡 通知 | 管理员 |
| Prompt 自动回滚 | 🔴 紧急 | 运维群 |
| 日常回归报告 | 🟢 信息 | 管理员 |
| 新 Tips 提取完成 | 🟢 信息 | 管理员 |

---

## 8. 成本估算

### 8.1 一次性投入（初始 golden set + 首轮进化）

| 范式 | LLM 调用 | API 成本 |
|---|---|---|
| 范式一（ML Agent × 7，各 50 条） | 0 | **¥0** |
| 范式二（Skill × 11，各 30 条 × 3 轮收敛） | ~1650 次 | **¥15-25** |
| 范式三（无初始成本） | 0 | **¥0** |
| **合计** | | **~¥25** |

### 8.2 月度维护

| 项目 | 频率 | 月 LLM 成本 |
|---|---|---|
| ML Agent 每日回归 | 每天 350 次本地调用 | **¥0** |
| Skill 每周回归 | 每周 330 × LLM Judge | **¥20** |
| Tips 每日提取 | 每天 ~50 条 trace | **¥6** |
| Tips 每周合并 | 每周 1 次批量 | **¥2** |
| Tips 运行时检索 | Cosine（免费） | **¥0** |
| **月合计** | | **~¥30** |

### 8.3 开发工时估算

| 阶段 | 内容 | 预估工时 |
|---|---|---|
| P0 | 后端 Runner + Code-Based Grader + 替换 mock | 4-6h |
| P1 | LLM Judge Grader + Prompt 版本管理 | 4-6h |
| P2 | Prompt 自进化引擎 + MetapromptAgent | 6-8h |
| P3 | Tips 提取/管理/检索 | 6-8h |
| P4 | 前端 Tab 1（实验竞技场） | 8-10h |
| P5 | 前端 Tab 2（Prompt 进化链 + Thinking） | 10-12h |
| P6 | 前端 Tab 3（轨迹记忆网络） | 8-10h |
| P7 | 前端 Tab 4（趋势总览） | 4-6h |
| P8 | 定时任务 + 飞书告警 + 审批流 | 4-6h |
| **合计** | | **~55-70h** |

---

## 9. 实施路线图

### Phase 1: 评测引擎真实化（P0-P1）

**目标**: 替换 mock，能真实跑评测

```
Week 1:
├── backend/governance/eval_center/runners/ — 4 个 Runner
├── backend/governance/eval_center/graders/ — Code-Based + LLM Judge
├── 重写 eval_service.py — 接入 Runner + Grader
├── DB migration — 新增字段
└── 验证: 手动触发实验 → 看到真实 pass_rate
```

### Phase 2: Prompt 自进化（P2）

**目标**: Copilot Skill prompt 能自动优化

```
Week 2:
├── eval_prompt_versions 表
├── VersionedPrompt 版本管理
├── MetapromptAgent（qwen3.5 thinking）
├── PromptEvolver 自进化引擎
├── SSE 事件推送（thinking 流）
└── 验证: 选一个 Skill 跑一轮进化 → prompt 变更 → 分数提升
```

### Phase 3: 轨迹记忆（P3）

**目标**: 自动从 trace 学习经验

```
Week 3:
├── eval_agent_tips 表
├── TipExtractor（Phase 1）
├── TipManager（Phase 2 — 泛化/聚类/合并）
├── TipRetriever（Phase 3 — cosine 检索）
├── TipInjector — 接入 CopilotEngine
├── 定时任务注册
└── 验证: 跑几条 trace → 提取出 Tips → 下次对话注入 → 回答质量提升
```

### Phase 4: 前端重写（P4-P7）

**目标**: 比赛级可视化

```
Week 4-5:
├── ConsoleEvals.vue 重写为 4 Tab 架构
├── Tab 1: HillClimbChart (Canvas) + ExperimentTimeline + OdometerNumber
├── Tab 2: PromptVersionTimeline + GraderRadarChart (SVG spring)
│          + ThinkingStream (SSE) + PromptDiffPanel + ApprovalCard
├── Tab 3: MemoryForceGraph (d3-force Canvas) + TipDetailCard
│          + InjectionMonitor + MemoryGrowthChart
├── Tab 4: PassRateHeatmap + CostTracker
└── 验证: 完整演示流程可跑通
```

### Phase 5: 闭环集成（P8）

**目标**: 完整闭环运维

```
Week 6:
├── ConsoleTraces → "加入评测集" 按钮
├── 定时回归 + 飞书告警
├── 审批流上线
├── 自动回滚机制
└── 验证: 端到端 — trace → 标注 → 评测 → 进化 → 审批 → 上线 → 监控
```

---

## 附录

### A. 参考资料

1. **Karpathy Loop**: Andrej Karpathy `autoresearch` (2026.03) — 爬山法自动实验
2. **OpenAI Self-Evolving Agents**: OpenAI Cookbook (2025.11) — Prompt 自进化 + 多 Grader 评估
3. **IBM Trajectory Memory**: *Trajectory-Informed Memory Generation for Self-Improving Agent Systems* (2026.03) — 从执行轨迹提取结构化经验
4. **Amazon Agent Eval**: *Evaluating AI agents: Real-world lessons from building agentic systems at Amazon* — 全面评估框架
5. **Pragmatic Engineer Evals**: *A pragmatic guide to LLM evals for devs* — Code-Based vs LLM-as-Judge

### B. 技术栈

| 层 | 技术 |
|---|---|
| LLM | qwen3.5-plus-2026-02-15（thinking mode） |
| 向量存储 | PostgreSQL pgvector（已有 PG 16）或 Redis Vector |
| Canvas 图表 | 原生 Canvas 2D API |
| 力导向图 | d3-force + Canvas 渲染 |
| Diff | Wasm char-level diff 或 js-diff 降级 |
| 动画 | CSS spring transitions + Canvas requestAnimationFrame |
| SSE | 复用现有 useCopilotStream.js |
| 定时调度 | APScheduler（已有） |
| 告警 | FeishuBridge（已有） |
