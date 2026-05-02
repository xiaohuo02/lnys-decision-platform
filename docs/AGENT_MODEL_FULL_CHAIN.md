# Agent & 模型全链路架构图

> **项目**: 柠优生活大数据智能决策平台 (LNYS)  
> **LLM 模型**: `qwen3.5-plus-2026-02-15` via 阿里云 DashScope  
> **生成时间**: 2026-04-12

---

## 1. 系统总览

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         用户入口 (Frontend)                                  │
├──────────┬──────────┬───────────────┬──────────────┬────────────────────────┤
│  BizCopilot  │ OpsCopilot │ AnalyzeProgress │ 飞书@机器人   │ APScheduler 巡检    │
│  (运营助手)  │ (运维助手) │ (经营分析启动)  │ (FeishuBridge)│ (CopilotPatrol)     │
└──────┬───┴─────┬────┴───────┬───────┴──────┬───────┴────────────┬───────────┘
       │         │            │              │                    │
       ▼         ▼            ▼              ▼                    ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                          后端路由层 (FastAPI)                                 │
├──────────────────┬───────────────────────┬───────────────────────────────────┤
│ /api/copilot/    │ /admin/copilot/       │ /api/v1/analyze                  │
│  stream (Biz SSE)│  stream (Ops SSE)     │  (触发 LangGraph Workflow)       │
└────────┬─────────┴──────────┬────────────┴───────────────┬───────────────────┘
         │                    │                            │
         ▼                    ▼                            ▼
┌───────────────────────┐  ┌─────────────────────────────────────┐
│   CopilotEngine       │  │   SupervisorAgent (请求路由)         │
│   (Skill 路由 + 执行) │  │   (规则/LLM 意图分类 → Workflow)    │
└───────────┬───────────┘  └──────────────────┬──────────────────┘
            │                                 │
            ▼                                 ▼
   ┌────────────────┐              ┌──────────────────────┐
   │  11 Copilot    │              │  4 LangGraph         │
   │  Skills        │              │  Workflows           │
   └────────────────┘              └──────────────────────┘
```

---

## 2. 双引擎架构：CopilotEngine vs SupervisorAgent

系统有两套并行的调度机制，分别服务不同入口：

```
                    ┌──────────────────────────────────┐
                    │            用户请求              │
                    └──────────────┬───────────────────┘
                                  │
                   ┌──────────────┴──────────────┐
                   ▼                             ▼
          ┌────────────────┐           ┌─────────────────────┐
          │ CopilotEngine  │           │  SupervisorAgent     │
          │ (Copilot 面板) │           │  (LangGraph 分析)    │
          ├────────────────┤           ├─────────────────────┤
          │ 入口: SSE 流   │           │ 入口: /api/v1/      │
          │ 路由: LLM      │           │ 路由: 规则 + LLM    │
          │  Function Call │           │  意图分类            │
          │ 执行: Skill    │           │ 执行: Workflow       │
          │ 输出: SSE 事件 │           │ 输出: state dict     │
          └───────┬────────┘           └──────────┬──────────┘
                  │                               │
         ┌────────┴────────┐            ┌─────────┴──────────┐
         ▼                 ▼            ▼         ▼       ▼       ▼
    ┌─────────┐     ┌──────────┐   ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐
    │ Skills  │     │ 通用对话 │   │ WF-A │ │ WF-B │ │ WF-C │ │ WF-D │
    │ (11个)  │     │ (LLM)   │   │经营览│ │风险审│ │客服话│ │运维诊│
    └─────────┘     └──────────┘   └──────┘ └──────┘ └──────┘ └──────┘
```

---

## 3. CopilotEngine 全链路

```
用户消息
  │
  ▼
┌─────────────────────────────────────────────────────────────────┐
│ CopilotEngine.run()                                             │
│                                                                 │
│  ① ContextManager.build()                                       │
│     ├── Layer 3: copilot_rules (静态配置)         ← MySQL       │
│     ├── Layer 2: copilot_memory (用户记忆 top-K)  ← MySQL       │
│     └── Layer 1: thread_history (最近5轮)         ← Redis       │
│                                                                 │
│  ② PermissionChecker.get_allowed_skills()         ← RBAC       │
│     └── 过滤用户角色可用的 Skill 集合                            │
│                                                                 │
│  ③ _route_to_skill()                              🔷 LLM 调用1 │
│     ├── openai.AsyncOpenAI → Function Calling                   │
│     │   model: qwen3.5-plus-2026-02-15                          │
│     │   tools: [11个 Skill 的 function schema]                  │
│     │   tool_choice: auto                                       │
│     ├── 成功 → 路由到匹配 Skill                                 │
│     └── 失败 → _keyword_fallback() (关键词匹配)                 │
│                                                                 │
│  ④ Skill.execute()                                              │
│     └── 调用底层 Service → 返回结构化数据 (TOOL_RESULT)         │
│                                                                 │
│  ⑤ _synthesize_answer()                           🔷 LLM 调用2 │
│     ├── openai.AsyncOpenAI → Streaming                          │
│     │   model: qwen3.5-plus-2026-02-15                          │
│     │   将 Skill 返回的 JSON 数据 + 用户问题                    │
│     │   → 生成中文自然语言分析总结                               │
│     └── yield TEXT_DELTA 事件 → SSE 推送前端                    │
│                                                                 │
│  ⑥ 或: _general_chat()                            🔷 LLM 调用  │
│     └── 无 Skill 匹配时的通用 LLM 流式对话                      │
│                                                                 │
│  ⑦ _write_copilot_run()                           → MySQL      │
│     └── 写 runs + run_steps 表                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.1 CopilotEngine LLM 调用点汇总

| 调用点 | 方法 | 客户端 | 用途 | 流式 |
|--------|------|--------|------|------|
| 路由 | `_route_to_skill()` | `openai.AsyncOpenAI` | Function Calling 选择 Skill | 否 |
| 综合回答 | `_synthesize_answer()` | `openai.AsyncOpenAI` | Skill 数据→自然语言总结 | 是 |
| 通用对话 | `_general_chat()` | `openai.AsyncOpenAI` | 无 Skill 匹配时的自由对话 | 是 |

---

## 4. 11 个 Copilot Skills 详解

```
┌───────────────────────────────────────────────────────────────────┐
│                    SkillRegistry (自动发现)                        │
│                                                                   │
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────┐  │
│  │ inventory_skill  │  │ forecast_skill   │  │ sentiment_skill│  │
│  │ 库存分析         │  │ 销售预测         │  │ 舆情分析       │  │
│  │ → InventoryOpt   │  │ → SalesForecast  │  │ → SentimentInt │  │
│  │   Service        │  │   Service        │  │   Service      │  │
│  └──────────────────┘  └──────────────────┘  └────────────────┘  │
│                                                                   │
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────┐  │
│  │ customer_intel   │  │ fraud_skill      │  │ association    │  │
│  │ 客户洞察         │  │ 欺诈风控         │  │ 关联推荐       │  │
│  │ → CustomerIntel  │  │ → FraudScoring   │  │ → Association  │  │
│  │   Service        │  │   Service        │  │   Service      │  │
│  └──────────────────┘  └──────────────────┘  └────────────────┘  │
│                                                                   │
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────┐  │
│  │ kb_rag_skill     │  │ memory_skill     │  │ trace_skill    │  │
│  │ 知识库检索       │  │ 记忆管理         │  │ Trace 查询     │  │
│  │ → KBRag Service  │  │ → Memory Center  │  │ → Trace DB     │  │
│  └──────────────────┘  └──────────────────┘  └────────────────┘  │
│                                                                   │
│  ┌──────────────────┐  ┌──────────────────┐                      │
│  │ system_skill     │  │ ocr_skill        │                      │
│  │ 系统状态         │  │ OCR 识别 (骨架)  │                      │
│  │ → Health Check   │  │ → 待接入模型     │                      │
│  └──────────────────┘  └──────────────────┘                      │
└───────────────────────────────────────────────────────────────────┘

Skill → Service 映射:
  inventory_skill      → inventory_optimization_service
  forecast_skill       → sales_forecast_service
  sentiment_skill      → sentiment_intelligence_service → sentiment_llm_service 🔷
  customer_intel_skill → customer_intelligence_service
  fraud_skill          → fraud_scoring_service
  association_skill    → association_service
  kb_rag_skill         → kb_rag_service
  memory_skill         → ContextManager / copilot_memory
  trace_skill          → runs / run_steps 查询
  system_skill         → 系统健康检查 + settings 读取
  ocr_skill            → (骨架, 待接入)
```

---

## 5. SupervisorAgent → LangGraph Workflows

```
用户请求 (自然语言)
  │
  ▼
┌─────────────────────────────────────────────────────────────────┐
│ SupervisorAgent.aroute()                                         │
│                                                                  │
│  ① 显式指定 request_type → 直接路由 (conf=1.0)                  │
│                                                                  │
│  ② 规则关键词匹配                                                │
│     ├── 风险/欺诈/冻结      → risk_review                       │
│     ├── 订单/快递/投诉/客服  → openclaw                          │
│     ├── 运维/监控/告警/日志  → ops_copilot                       │
│     └── 经营/分析/预测/舆情  → business_overview                 │
│     命中 → conf ≥ 0.6 → 直接返回                                │
│                                                                  │
│  ③ conf < 0.6 → _llm_classify()               🔷 LLM 调用      │
│     ├── langchain_openai.ChatOpenAI                              │
│     │   model: qwen3.5-plus-2026-02-15                           │
│     │   System Prompt: 请求路由分类器                             │
│     │   返回 JSON: {route, confidence, reason}                   │
│     └── 失败 → 降级到规则结果 / business_overview                │
│                                                                  │
│  输出: SupervisorOutput(route, confidence, route_plan)           │
└──────────────────────────┬──────────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              ▼            ▼            ▼            ▼
       ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
       │ WF-A     │ │ WF-B     │ │ WF-C     │ │ WF-D     │
       │ 经营总览 │ │ 风险审核 │ │ 客服会话 │ │ 运维诊断 │
       └──────────┘ └──────────┘ └──────────┘ └──────────┘
```

---

## 6. Workflow A — 经营总览分析 (business_overview)

```
                          ┌───────────────┐
                          │    START      │
                          └───────┬───────┘
                                  │
                                  ▼
                    ┌───────────────────────────┐
                    │  data_preparation         │  DataPreparationService
                    │  数据质量检查 + OMO 融合  │  (纯 Python, 无 LLM)
                    └─────────────┬─────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              ▼                   ▼                   ▼
  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
  │ customer_intel   │ │ sales_forecast   │ │ sentiment_intel  │
  │ 客户洞察 (RFM/  │ │ 销售预测 (SARIMA │ │ 舆情分析 (BERT/  │
  │  CLV/流失)       │ │  /XGB/Stacking)  │ │  LDA/TF-IDF)     │
  │ ── ML 模型 ──   │ │ ── ML 模型 ──   │ │ ── ML 模型 ──    │
  │ churn_xgb        │ │ sarima           │ │ svc_sentiment    │
  │ BG-NBD           │ │ prophet          │ │ tfidf_vec        │
  │ Gamma-Gamma      │ │ xgb_sales        │ │ lda_dict         │
  │ KMeans           │ │ lgbm_hybrid      │ │ bert_chinese 🧠  │
  └────────┬─────────┘ │ stacking_weights │ └────────┬─────────┘
           │            └────────┬─────────┘          │
           └───────────────────┬─┘ ┌──────────────────┘
                               │   │
                               ▼   ▼
                    ┌──────────────────────┐
                    │  fraud_scoring       │  FraudScoringService
                    │  欺诈风控            │  ── ML 模型 ──
                    │  IsoForest + LGB     │  iso_forest / fraud_lgb
                    │  AutoEncoder         │  ae_scaler
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  inventory           │  InventoryOptimizationService
                    │  库存优化            │  (运筹学: EOQ + 安全库存)
                    │  ABC-XYZ 分类        │  (无 ML 模型)
                    └──────────┬───────────┘
                               │
                               ▼
                ┌────────────────────────────────┐
                │  insight_composer              │  🔷 LLM 调用
                │  InsightComposerAgent          │
                │  ─────────────────────────────│
                │  输入: 各节点 artifact summary │
                │  LLM: qwen3.5-plus-2026-02-15 │
                │  输出: executive_summary       │
                │        risk_highlights         │
                │        action_plan             │
                │  降级: 模板拼接 (LLM 不可用)  │
                └────────────────┬───────────────┘
                                 │
                                 ▼
                          ┌──────────┐
                          │   END    │
                          └──────────┘
```

---

## 7. Workflow B — 高风险交易审核 (risk_review)

```
                          ┌───────────┐
                          │   START   │
                          └─────┬─────┘
                                │
                                ▼
                  ┌───────────────────────────┐
                  │  fraud_scoring            │  FraudScoringService
                  │  批量欺诈评分             │  ── ML 模型 ──
                  │  IsoForest + LGB + AE     │  iso_forest / fraud_lgb
                  │  输出: high_risk_count    │
                  └─────────────┬─────────────┘
                                │
                                ▼
                  ┌───────────────────────────┐
                  │  prepare_review           │  RiskReviewAgent
                  │  创建审核案例             │  🔷 LLM 调用
                  │  _llm_risk_summary()      │  qwen3.5-plus-2026-02-15
                  │  生成风险审核摘要         │  (langchain ChatOpenAI)
                  └─────────────┬─────────────┘
                                │
                                ▼
                  ┌───────────────────────────┐
                  │  hitl_interrupt            │  ⏸ HITL 人工审核
                  │  ─────────────────────── │
                  │  高风险 → LangGraph       │
                  │    interrupt() 暂停       │
                  │  PG Checkpoint 保存状态   │
                  │  ─────────────────────── │
                  │  人工审核后 Command        │
                  │    (resume=decision)      │
                  │  approve / reject / edit  │
                  └─────────────┬─────────────┘
                                │
                                ▼
                  ┌───────────────────────────┐
                  │  post_review              │
                  │  记录决策 + 更新状态      │
                  └─────────────┬─────────────┘
                                │
                                ▼
                          ┌──────────┐
                          │   END    │
                          └──────────┘
```

---

## 8. Workflow C — OpenClaw 客服会话 (openclaw_session)

```
                          ┌───────────┐
                          │   START   │
                          └─────┬─────┘
                                │
                                ▼
                  ┌───────────────────────────┐
                  │  respond                  │  OpenClawCustomerAgent
                  │  ─────────────────────── │
                  │  1. 意图分类 (规则)      │
                  │     退换货/物流/投诉/     │
                  │     账户/FAQ/未知         │
                  │  2. FAQ 知识库匹配       │
                  │  3. _llm_reply()          │  🔷 LLM 调用
                  │     qwen3.5-plus-2026-02-15
                  │     (os.getenv fallback)  │
                  │  输出: reply, intent,     │
                  │    confidence, handoff    │
                  └─────────────┬─────────────┘
                                │
                     ┌──────────┴──────────┐
                     │ handoff?             │
                     ├── True ─────────┐   │
                     │                 ▼   │
                     │    ┌──────────────┐ │
                     │    │  handoff     │ │
                     │    │  创建转人工  │ │
                     │    │  review_case │ │
                     │    └──────┬───────┘ │
                     │           │         │
                     ├── False ──┘─────────┘
                     ▼
               ┌──────────┐
               │   END    │
               └──────────┘
```

---

## 9. Workflow D — 运维诊断 (ops_diagnosis)

```
                          ┌───────────┐
                          │   START   │
                          └─────┬─────┘
                                │
                                ▼
                  ┌───────────────────────────┐
                  │  ops_respond              │  OpsCopilotAgent
                  │  ─────────────────────── │
                  │  1. 意图分类 (规则)      │
                  │     系统状态/日志/告警/   │
                  │     trace/部署/数据库     │
                  │  2. 查询 DB 指标数据     │
                  │  3. _llm_enhance()        │  🔷 LLM 调用
                  │     qwen3.5-plus-2026-02-15
                  │     (os.getenv fallback)  │
                  │  输出: answer, intent,    │
                  │    confidence, sources,   │
                  │    suggested_actions      │
                  └─────────────┬─────────────┘
                                │
                                ▼
                          ┌──────────┐
                          │   END    │
                          └──────────┘
```

---

## 10. 所有 LLM 调用点汇总

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                      LLM 调用全景图                                          │
│                      Model: qwen3.5-plus-2026-02-15                         │
│                      Base URL: dashscope.aliyuncs.com                       │
├──────────────────────┬──────────────────┬───────────────────────────────────┤
│  调用者               │  客户端           │  用途                             │
├──────────────────────┼──────────────────┼───────────────────────────────────┤
│                      │                  │                                   │
│  ◆ CopilotEngine     │                  │                                   │
│  ├ _route_to_skill   │ openai.Async     │ Function Calling 路由            │
│  ├ _synthesize_answer│ openai.Async     │ Skill 数据→自然语言总结 (流式)   │
│  └ _general_chat     │ openai.Async     │ 通用对话 (流式)                  │
│                      │                  │                                   │
│  ◆ SupervisorAgent   │                  │                                   │
│  └ _llm_classify     │ langchain OpenAI │ 意图分类路由 (Workflow 选择)      │
│                      │                  │                                   │
│  ◆ OpenClawAgent     │                  │                                   │
│  └ _llm_reply        │ langchain OpenAI │ 客服回复生成                      │
│                      │                  │                                   │
│  ◆ OpsCopilotAgent   │                  │                                   │
│  └ _llm_enhance      │ langchain OpenAI │ 运维回答增强                      │
│                      │                  │                                   │
│  ◆ RiskReviewAgent   │                  │                                   │
│  └ _llm_risk_summary │ langchain OpenAI │ 风险审核摘要生成                  │
│                      │                  │                                   │
│  ◆ InsightComposer   │                  │                                   │
│  └ _llm_compose      │ langchain OpenAI │ 经营洞察报告合成                  │
│                      │                  │                                   │
│  ◆ SentimentLLM      │                  │                                   │
│  │  Service           │                  │                                   │
│  ├ Tier 2: CoT       │ langchain OpenAI │ 单次 LLM 舆情推理                │
│  └ Tier 3: SC 3路    │ langchain OpenAI │ Self-Consistency 三路投票        │
│                      │                  │                                   │
│  ◆ MemoryConsolidator│                  │                                   │
│  ├ compact_convers.  │ langchain OpenAI │ 多轮对话压缩                      │
│  └ consolidate_run   │ langchain OpenAI │ Run 学习记忆提取                  │
│                      │                  │                                   │
│  ◆ ErrorClassifier   │                  │                                   │
│  └ classify          │ (fallback_model) │ 错误分类 (降级用)                 │
├──────────────────────┴──────────────────┴───────────────────────────────────┤
│  总计: 12 个 LLM 调用点                                                     │
│  配置来源: settings.LLM_API_KEY / LLM_BASE_URL / LLM_MODEL_NAME            │
│  部分 Agent 有 os.getenv() 硬编码 fallback                                  │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 11. ML 模型全景图 (非 LLM)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          本地 ML 模型                                        │
├──────────────┬────────────────────┬──────────────────────────────────────────┤
│  Agent        │  模型文件           │  类型 / 算法                            │
├──────────────┼────────────────────┼──────────────────────────────────────────┤
│              │                    │                                          │
│  Sentiment   │ svc_sentiment.pkl  │ SVM 情感分类                            │
│  Agent       │ tfidf_sentiment.pkl│ TF-IDF 向量化                           │
│  (BERT +     │ lda_dict.pkl       │ LDA 主题模型                            │
│   LDA +      │ bert_chinese/      │ BERT-Chinese 微调模型 🧠               │
│   TF-IDF)    │                    │                                          │
│              │                    │                                          │
│  Customer    │ churn_xgb.pkl      │ XGBoost 流失预测                        │
│  Agent       │ bgf.pkl            │ BG-NBD 客户活跃度                       │
│  (RFM/CLV)   │ ggf.pkl            │ Gamma-Gamma 客户价值                    │
│              │ kmeans.pkl         │ KMeans 客户分群                          │
│              │ scaler_rfm.pkl     │ StandardScaler                          │
│              │                    │                                          │
│  Forecast    │ sarima.pkl         │ SARIMA 时间序列                         │
│  Agent       │ prophet.pkl        │ Facebook Prophet                        │
│  (多模型集成)│ sales_xgb.pkl      │ XGBoost 回归                            │
│              │ lgbm_hybrid.pkl    │ LightGBM 混合                           │
│              │ stacking_weights   │ Stacking 集成权重                       │
│              │                    │                                          │
│  Fraud       │ iso_forest.pkl     │ Isolation Forest 异常检测               │
│  Agent       │ fraud_lgb.pkl      │ LightGBM 欺诈分类                      │
│  (三路融合)  │ ae_scaler.pkl      │ AutoEncoder 预处理                      │
│              │                    │                                          │
│  Association │ association_rules  │ FP-Growth 关联规则                      │
│  Agent       │  .csv              │                                          │
│              │                    │                                          │
│  Inventory   │ (无 ML 模型)       │ 运筹学公式: EOQ + 安全库存             │
│  Agent       │                    │                                          │
│              │                    │                                          │
│  Data Agent  │ (无 ML 模型)       │ 数据质量检查 + OMO 融合                │
├──────────────┴────────────────────┴──────────────────────────────────────────┤
│  总计: 14 个本地模型文件 + 1 个 BERT 预训练模型                              │
│  存储路径: settings.ART_* (artifact_store/)                                  │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 12. 端到端完整链路示例

### 示例 A: 用户在 BizCopilot 问「舆情分析」

```
[前端] BizCopilot.vue → POST /api/copilot/stream (SSE)
  │
  ▼
[Router] copilot_biz.py → CopilotEngine.run(mode="biz")
  │
  ├── ① ContextManager.build() → 加载 rules + memory + history
  │
  ├── ② PermissionChecker → 过滤可用 Skills
  │
  ├── ③ _route_to_skill()                        🔷 LLM #1
  │     openai Function Calling
  │     → 选中 sentiment_skill
  │
  ├── ④ SentimentSkill.execute()
  │     └── SentimentIntelligenceService.analyze()
  │         └── SentimentLLMService
  │             ├── Tier 1: BERT 本地推断          🧠 ML
  │             ├── conf < 0.85 → Tier 2: LLM CoT 🔷 LLM #2
  │             └── conf < 0.70 → Tier 3: SC 3路   🔷 LLM #3,#4,#5
  │
  ├── ⑤ _synthesize_answer()                     🔷 LLM #6
  │     Skill 结构化数据 → 中文分析总结 (流式)
  │
  └── ⑥ SSE 事件流 → 前端渲染
        TEXT_DELTA / TOOL_RESULT / RUN_END
```

### 示例 B: 用户触发「经营总览分析」

```
[前端] AnalyzeProgress.vue → POST /api/v1/analyze
  │
  ▼
[Router] analyze.py → SupervisorAgent.aroute()
  │
  ├── ① 规则匹配: "经营" → business_overview (conf=0.7)
  │
  └── ② run_business_overview()  (LangGraph Workflow)
        │
        ├── data_preparation         (Python)
        ├── customer_intel           (XGBoost/BG-NBD/KMeans)    🧠 ML ×4
        ├── sales_forecast           (SARIMA/Prophet/XGB/LGBM)  🧠 ML ×5
        ├── sentiment_intel          (BERT/SVM/LDA)             🧠 ML ×3
        ├── fraud_scoring            (IsoForest/LGB)            🧠 ML ×2
        ├── inventory                (运筹学 EOQ)
        └── insight_composer         (LLM 合成报告)             🔷 LLM
              │
              └── executive_summary + risk_highlights + action_plan
```

### 示例 C: 高风险交易审核 (HITL)

```
[触发] → SupervisorAgent → risk_review
  │
  ├── fraud_scoring          (IsoForest/LGB)                    🧠 ML
  ├── prepare_review         (RiskReviewAgent._llm_risk_summary) 🔷 LLM
  ├── hitl_interrupt          ⏸ 暂停等待人工
  │     │
  │     │  [PG Checkpoint 持久化]
  │     │
  │     ▼  [管理员在前端审核]
  │     approve / reject / edit
  │     │
  │     ▼  Command(resume=decision)
  │
  └── post_review → 记录决策 → END
```

---

## 13. 治理层链路

```
┌─────────────────────────────────────────────────────────────────┐
│                       Governance 治理层                          │
│                                                                  │
│  ┌──────────────────┐                                            │
│  │  InputGuard      │  所有 Workflow 入口 + Copilot 均经过       │
│  │  输入安全检查    │  ├── 注入攻击检测                         │
│  │                  │  ├── 敏感词过滤                            │
│  │                  │  └── 文本消毒 (sanitize)                  │
│  └──────────────────┘                                            │
│                                                                  │
│  ┌──────────────────┐                                            │
│  │  ErrorClassifier │  🔷 LLM 调用 (降级分类)                  │
│  │  错误分类器      │  fallback_model: qwen3.5-plus-2026-02-15 │
│  │  + RetryHandler  │  execute_with_retry() 重试策略            │
│  └──────────────────┘                                            │
│                                                                  │
│  ┌──────────────────┐                                            │
│  │  MemoryConsolid. │  🔷 LLM 调用 ×2                          │
│  │  记忆整合器      │  ├── compact_conversation (对话压缩)      │
│  │  3 层压缩        │  └── consolidate_run (记忆提取)           │
│  └──────────────────┘                                            │
│                                                                  │
│  ┌──────────────────┐                                            │
│  │  TraceContext    │  所有 Workflow 运行写入                     │
│  │  链路追踪        │  ├── runs 表 (运行记录)                   │
│  │                  │  └── run_steps 表 (步骤明细)              │
│  └──────────────────┘                                            │
│                                                                  │
│  ┌──────────────────┐                                            │
│  │  OutputGuard     │  hook_pipeline.py                          │
│  │  输出安全检查    │  ├── 敏感信息检测 (api_key, password)     │
│  │                  │  └── PII 脱敏                              │
│  └──────────────────┘                                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 14. 基础设施层

```
┌─────────────────────────────────────────────────────────────────┐
│                       Infrastructure                             │
│                                                                  │
│  ┌──────────────────┐  ┌──────────────────┐                     │
│  │  AgentGateway    │  │  OrchestratorAgent│                     │
│  │  统一调用网关    │  │  DAG 编排 (预留) │                     │
│  │  超时保护 30s    │  │  asyncio.gather   │                     │
│  │  异常降级 None   │  │  Redis Pub/Sub    │                     │
│  └──────────────────┘  └──────────────────┘                     │
│                                                                  │
│  ┌──────────────────┐  ┌──────────────────┐                     │
│  │  BaseAgent       │  │  BaseWorkflow    │                     │
│  │  ReAct 认知循环  │  │  LangGraph 骨架  │                     │
│  │  perceive→reason │  │  StateGraph      │                     │
│  │  →act→reflect→   │  │  PG Checkpoint   │                     │
│  │  output          │  │  interrupt/resume │                     │
│  └──────────────────┘  └──────────────────┘                     │
│                                                                  │
│  ┌──────────────────────────────────────────────────────┐       │
│  │  数据存储                                             │       │
│  │  ├── MySQL 8.0   — 业务表 + copilot 表 + runs/steps │       │
│  │  ├── Redis 7     — 对话历史 + 共享记忆 + 进度通道    │       │
│  │  └── PostgreSQL 16 — LangGraph Checkpoint            │       │
│  └──────────────────────────────────────────────────────┘       │
│                                                                  │
│  ┌──────────────────────────────────────────────────────┐       │
│  │  外部服务                                             │       │
│  │  ├── 阿里云 DashScope  — LLM API (qwen3.5-plus)     │       │
│  │  └── 飞书 lark-oapi    — WebSocket + 消息卡片        │       │
│  └──────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

---

## 15. 配置来源链

```
┌─────────────────────────────────────────────────────────────────┐
│                  LLM 配置流转                                    │
│                                                                  │
│  .env / .env.prod                                                │
│    │  LLM_API_KEY=sk-ce078db286c64dfe8e542c2daa48a4a0           │
│    │  LLM_BASE_URL=https://dashscope.aliyuncs.com/...           │
│    │  LLM_MODEL_NAME=qwen3.5-plus-2026-02-15                   │
│    ▼                                                             │
│  backend/config.py → settings (Pydantic BaseSettings)           │
│    │  LLM_API_KEY: str                                          │
│    │  LLM_BASE_URL: str                                         │
│    │  LLM_MODEL_NAME: str = "qwen3.5-plus-2026-02-15"          │
│    │                                                             │
│    ├──→ CopilotEngine       (settings.LLM_*)                   │
│    ├──→ SupervisorAgent     (settings.LLM_*)                   │
│    ├──→ SentimentLLMService (settings.LLM_*)                   │
│    ├──→ InsightComposerAgent(settings.LLM_*)                   │
│    │                                                             │
│    └──→ os.getenv() fallback (Agent 级别)                       │
│         ├── OpenClawAgent        getenv("LLM_MODEL_NAME",       │
│         ├── OpsCopilotAgent       "qwen3.5-plus-2026-02-15")   │
│         ├── RiskReviewAgent                                     │
│         └── MemoryConsolidator                                  │
└─────────────────────────────────────────────────────────────────┘
```
