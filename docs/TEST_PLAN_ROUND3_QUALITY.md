# LNYS 第三轮测试：回答质量与任务完成度验收

## 1. 测试目标

从"能跑通"升级到"回答可信、可用、完成任务"。  
不再测功能是否 crash，而是测 **商业级回答质量**。

## 2. 评估维度（6 类）

| 维度 | 代码 | 核心问题 |
|------|------|----------|
| Groundedness | G | 回答是否基于真实 tool_result，有无幻觉/编造 |
| Task Completion | TC | 是否真正完成了用户要求的动作 |
| Answer Quality | AQ | 相关性、完整性、准确性、可执行性、简洁度 |
| Tool→Summary 一致性 | TSC | tool_result 数据与最终文字总结是否一致 |
| Blind Regression | BR | 未针对性修复过的盲测 case |
| Multi-turn Quality | MT | 多轮追问/纠错/上下文延续的回答质量 |

## 3. 评分结构（每条 case）

```json
{
  "case_id": "G1",
  "category": "groundedness",
  "question": "...",
  "skill_expected": "fraud_skill",
  "skill_actual": "fraud_skill",
  "skill_match": true,
  "has_tool_result": true,
  "scores": {
    "groundedness": 4,      // 0-5: 回答是否基于工具结果
    "task_completion": 5,    // 0-5: 是否完成了用户任务
    "answer_quality": 3,     // 0-5: 回答质量综合评分
    "tool_consistency": 4,   // 0-5: 工具数据与总结一致性
    "overall": 4.0           // 加权平均
  },
  "failure_tags": ["GENERIC_TEMPLATE"],
  "verdict": "PASS_FUNCTION_FAIL_QUALITY",
  "evidence": "tool_result 返回 top_risk_transactions 含 5 条记录，但总结未引用任何具体交易 ID 或金额"
}
```

## 4. 失败标签体系

### 4.1 Groundedness 失败
| 标签 | 定义 |
|------|------|
| `HALLUCINATION` | 回答包含 tool_result 中不存在的数据/数字/实体 |
| `TOOL_RESULT_IGNORED` | tool 返回了数据但总结完全没引用 |
| `CONTRADICTS_TOOL` | 总结结论与 tool_result 数据矛盾（如工具说下降，总结说上升） |
| `FABRICATED_NUMBERS` | 总结中出现的具体数字在 tool_result 中找不到来源 |

### 4.2 Task Completion 失败
| 标签 | 定义 |
|------|------|
| `FAKE_COMPLETION` | 说"已完成/已分析"但实际没调用任何工具 |
| `WRONG_TASK` | 执行了错误的任务（路由到错误 skill） |
| `PARTIAL_COMPLETION` | 只完成了部分任务 |
| `NO_ACTION` | 用户要求执行动作，系统只给了建议没执行 |

### 4.3 Answer Quality 失败
| 标签 | 定义 |
|------|------|
| `GENERIC_TEMPLATE` | 回答是通用模板，没有基于实际数据定制 |
| `VERBOSE_EMPTY` | 大量文字但无实质内容 |
| `ANSWER_IRRELEVANT` | 答非所问 |
| `NOT_ACTIONABLE` | 声称给建议但建议空泛不可执行 |
| `EXCESSIVE_REPETITION` | 重复相同内容 |
| `MISSING_KEY_INFO` | 缺少用户明确要求的关键信息 |

### 4.4 Tool→Summary 一致性失败
| 标签 | 定义 |
|------|------|
| `DATA_MISMATCH` | 总结中的数字与 tool_result 不一致 |
| `CHERRY_PICKING` | 选择性引用，忽略重要数据点 |
| `TEMPLATE_OVER_DATA` | 模板结构压过了实际数据呈现 |

### 4.5 Multi-turn 失败
| 标签 | 定义 |
|------|------|
| `CONTEXT_LOST` | 无法关联上一轮对话内容 |
| `REFERENCE_WRONG` | 引用了错误的历史信息 |
| `RESET_CONVERSATION` | 每轮都重新开始，没有延续 |

## 5. 判定标准

| 判定 | 条件 |
|------|------|
| `QUALITY_PASS` | overall ≥ 3.5 且无严重 failure tag |
| `FUNCTION_PASS_QUALITY_FAIL` | 功能通过（正确 skill + 有 tool_result + 有 run_end）但 overall < 3.5 |
| `FUNCTION_FAIL` | 错误 skill / 无 tool_result / 无 run_end |

严重 failure tags（任何一个即判 QUALITY_FAIL）：
`HALLUCINATION`, `CONTRADICTS_TOOL`, `FAKE_COMPLETION`, `FABRICATED_NUMBERS`

## 6. 30 条测试用例

### G: Groundedness（5 条）

| ID | 问题 | 期望 Skill | 验证重点 |
|----|------|------------|----------|
| G1 | 最近有多少高风险交易？拦截率是多少？ | fraud_skill | 总结中数字必须来自 tool_result |
| G2 | 列出需要紧急补货的前5个SKU及补货量 | inventory_skill | 总结必须列出具体 SKU 编码和数量 |
| G3 | 当前客户流失率和高价值客户占比分别是多少？ | customer_intel_skill | 必须引用具体百分比 |
| G4 | 最新舆情中负面评论占比多少？举几个例子 | sentiment_skill | 必须引用具体负面评论内容 |
| G5 | 下个月销售预测数据是多少？同比增长还是下降？ | forecast_skill | 预测数字必须与 tool_result 一致 |

### TC: Task Completion（5 条）

| ID | 问题 | 期望行为 | 验证重点 |
|----|------|----------|----------|
| TC1 | 帮我生成一份本月经营分析报告 | 触发 business_overview workflow | 必须真正启动工作流而非只是聊天 |
| TC2 | 执行一次风控审查 | 触发 risk_review workflow | 必须有 run_id 和 workflow 状态 |
| TC3 | 在知识库里搜索关于退货流程的规定 | kb_rag_skill 返回文档 | 必须返回实际文档片段，非编造 |
| TC4 | 分析一下哪些商品适合搭配销售 | association_skill 返回关联规则 | 必须有具体商品对和支持度数据 |
| TC5 | 分析一下库存中哪些品类最需要关注 | inventory_skill | 必须有数据支撑的品类排序 |

### AQ: Answer Quality（5 条）

| ID | 问题 | 验证重点 |
|----|------|----------|
| AQ1 | 我们的业务最近怎么样？ | 模糊问题：应结构化回答或引导细化，不能编造 |
| AQ2 | 库存分析，重点关注即将断货的品类 | 应聚焦断货风险，不能泛泛而谈 |
| AQ3 | 风控数据里最关键的三个发现是什么？ | 应优先排序，不能全部堆砌 |
| AQ4 | 客户画像分析，重点是高价值客户消费习惯 | 应有深度洞察，不能只给统计数字 |
| AQ5 | 针对当前舆情给出具体的应对方案 | 建议必须可执行，不能空泛 |

### TSC: Tool→Summary 一致性（5 条）

| ID | 问题 | 验证重点 |
|----|------|----------|
| TSC1 | 库存优化建议 | artifact 中的 urgent_count 必须出现在文字总结中 |
| TSC2 | 欺诈风险评分 | tool_result 中的 risk_score/risk_level 必须与总结一致 |
| TSC3 | 销售趋势分析 | forecast 数值方向（涨/跌）必须与总结结论一致 |
| TSC4 | 客户分群结果 | 分群数量和各群特征必须与 tool_result 一致 |
| TSC5 | 关联规则挖掘结果 | 关联商品对必须与 tool_result 一致 |

### BR: Blind Regression（5 条）

| ID | 问题 | 验证重点 |
|----|------|----------|
| BR1 | 库存和销售之间有什么关系？ | 跨域问题路由合理性 |
| BR2 | 不要分析，只告诉我库存低于安全线的SKU数量 | 指令跟随：简短直答 vs 冗长分析 |
| BR3 | 这个预测数据准确吗？我不太相信 | 处理用户质疑的能力 |
| BR4 | 帮我同时看看库存情况和客户情况 | 多意图处理 |
| BR5 | 用一句话总结当前最紧急的业务问题 | 精炼总结能力 |

### MT: Multi-turn Quality（5 条，每条 2-3 轮）

| ID | 轮次 | 问题 | 验证重点 |
|----|------|------|----------|
| MT1 | T1 | 分析一下库存状况 | 基线回答 |
| MT1 | T2 | 刚才提到的紧急补货SKU，能详细说说原因吗？ | 上下文引用 |
| MT2 | T1 | 客户流失率是多少？ | 基线数据 |
| MT2 | T2 | 那高价值客户的流失情况呢？ | 追问细化 |
| MT3 | T1 | 最近有异常交易吗？ | 基线回答 |
| MT3 | T2 | 不是这个，我问的是退款相关的异常 | 纠错能力 |
| MT4 | T1 | 当前舆情概况 | 基线回答 |
| MT4 | T2 | 针对你刚才提到的负面评论，给出处理建议 | 任务延续 |
| MT5 | T1 | 销售预测结果 | 基线回答 |
| MT5 | T2 | 和库存数据对比一下，有没有潜在的缺货风险？ | 跨 skill 关联 |
