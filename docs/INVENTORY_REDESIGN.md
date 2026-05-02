# 库存智能管理页面重构设计文档

> **版本**: v1.1  
> **日期**: 2026-04-08  
> **状态**: Draft — 待评审  
> **涉及模块**: `frontend/src/views/business/InventoryManagement.vue` 及关联组件/后端
>
> **变更记录**:  
> - v1.1: 新增 §2.5 独立 Copilot 页 vs 页面内嵌架构定位（Thread 共享、状态同步、Skill 作用域、UI 差异化）

---

## 1. 背景与目标

### 1.1 现状问题

| # | 问题 | 现状描述 | 影响 |
|---|------|---------|------|
| P1 | AI 洞察是伪实现 | `InsightPanelV2` 内部是 `computed()` 拼字符串，无 LLM 调用 | 失去 AI 平台核心卖点 |
| P2 | 无 Agent 联动 | 页面纯 REST → `InventoryService`，不经过 Agent/Copilot | `InventoryAgent` + `InventorySkill` 形同虚设 |
| P3 | 无跨 Agent 编排 | 无法从库存页发起 "预测需求"(forecast)、"关联分析"(association) | 决策信息割裂 |
| P4 | 无知识库接入 | 无 KB 入口，补货 SOP、供应商协议需切换系统查看 | 运营效率低 |
| P5 | 交互深度不足 | 矩阵仅 CSS 格子，表格无 sparkline，KPI 无动画 | 对标 Linear/Vercel 差距大 |
| P6 | 高级组件闲置 | 已有 `SplitInspector`、`ChatPanel`、`Odometer` 但未使用 | 设计系统 ROI 低 |

### 1.2 设计目标

1. **智能体联动**: 页面内嵌 Copilot Chat，可调用 inventory/forecast/association/kb_rag/sentiment 等任意 Skill
2. **知识库兼容**: 右侧 KB Tab 接入 `kb_rag` skill，后续新增知识库只需后端注入 collection，前端零改动
3. **交互对标**: 对齐 Linear + Vercel + ChatGPT 级别的视觉与交互品质
4. **架构可复用**: 新建的 `usePageCopilot` composable 可直接用于其他业务页（销售预测、客户分析等）

### 1.3 对标参考

| 平台 | 借鉴点 |
|------|--------|
| **Linear** | SplitInspector 三栏布局、行点击→右侧 Detail Panel、⌘K 命令面板 |
| **Vercel** | 极简 KPI strip + Odometer 动画数字、hairline 分隔、Zinc 单色调 |
| **ChatGPT** | 页面内嵌 AI Chat（非独立页面）、streaming artifact、follow-up suggestions |
| **Notion AI** | 上下文感知——选中行后 AI 自动理解 "你在看哪个 SKU" |
| **Datadog** | Sparkline 内嵌表格列、Heatmap 矩阵、drill-down 动画 |

---

## 2. 目标布局

```
┌──────────────────────────────────────────────────────────────────┐
│  PageHeaderV2: 库存智能管理                      [⌘K]  [AI ◀▸] │
├─────────────────────────────────┬────────────────────────────────┤
│  Main Content (scrollable)      │  Right Panel (tab-switch)      │
│                                 │                                │
│  ┌─ KPI Strip (Odometer) ────┐ │  ┌─ [🤖 AI] [📋 Detail] [📚 KB] ─┐ │
│  │ Health% │ SKU │ ⚠ │ 🔴 │ │  │                              │ │
│  │  69%    │ 26  │  6 │ 2  │ │  │  Scoped Copilot Chat         │ │
│  └───────────────────────────┘ │  │  ・streaming markdown        │ │
│                                 │  │  ・inline InventoryArtifact  │ │
│  ┌─ Smart Alert Table ───────┐ │  │  ・cross-agent artifacts     │ │
│  │ ☑│SKU │Stock ▎▎│Safety│补│ │  │                              │ │
│  │  │    │sparkline│     │货│ │  │  Suggested Follow-ups:       │ │
│  │  │    │(7d SVG) │     │  │ │  │  "紧急SKU下月需求预测"       │ │
│  └───────────────────────────┘ │  │  "查询补货SOP文档"           │ │
│                                 │  │  "通知采购群补货"            │ │
│  ┌─ ABC-XYZ Heatmap ────────┐ │  └──────────────────────────────┘ │
│  │  AX:3│AY:2│AZ:1          │ │                                │
│  │  BX:4│BY:5│BZ:2          │ │  [Detail Tab]                  │
│  │  CX:3│CY:4│CZ:2          │ │  选中 SKU 的详细信息、趋势图、 │
│  └───────────────────────────┘ │  Agent 历史分析记录             │
│                                 │                                │
│  ┌─ Trend Chart (30d) ──────┐ │  [KB Tab]                      │
│  │  全局库存健康度趋势        │ │  搜索补货政策/SOP/供应商协议   │
│  └───────────────────────────┘ │  由 kb_rag skill 驱动          │
│                                 │                                │
├─────────────────────────────────┴────────────────────────────────┤
│  Command Bar: 输入库存相关问题...    [@inventory] [@forecast]     │
└──────────────────────────────────────────────────────────────────┘
```

**布局实现**: 使用已有 `SplitInspector.vue`，`main` slot 放数据面板，`right` slot 放三 Tab 上下文面板。右侧面板支持折叠（折叠时 main 撑满全宽）。

---

## 2.5 独立 Copilot 页 vs 页面内嵌 — 架构定位

### 2.5.1 行业共识：两者共存，不是重复

项目已有独立 Copilot 页（`BizCopilot.vue` → `UnifiedCopilotPanel`，612 行 SFC）。页面内嵌**不是**把同一个 Chat 缩小塞进右侧，而是服务不同交互模式：

| 维度 | 独立 Copilot 页 (`BizCopilot.vue`) | 页面内嵌 (库存页右侧 AI Tab) |
|------|-------------------------------------|-------------------------------|
| **用户心智** | "我有问题，去找 AI" | "我在干活，AI 主动帮我" |
| **上下文** | 用户手动描述（"A001 库存多少"） | 自动注入（`page_context.selected_sku`） |
| **对话深度** | 多轮深度探索、跨业务域 | 短对话为主，action-oriented |
| **History** | 完整侧栏，可回溯所有线程 | 仅当前页面相关线程（下拉选择器） |
| **Mode Switch** | Auto / Think / Research 三模式 | 固定 Auto（降低认知负荷） |
| **Skill 范围** | 全部 11 个 skill | 默认库存相关，可 @ 扩展 |
| **UI 复杂度** | 全功能 | 精简版（无 History sidebar、无 Mode Switch） |

**行业参考**: Microsoft 365 Copilot 同时有独立 Chat 和各 App 内嵌，内嵌使用率占 70%+。Salesforce Einstein 同理。

### 2.5.2 Thread 共享机制

**核心原理**: 两者共享同一个 `copilot_threads` 表，通过 `page_origin` 字段区分来源。

```
copilot_threads 表结构（已有字段）:
┌─────────────────────────────────────────────────────────┐
│ id  │ user_id │ mode │ page_origin │ title       │ ...  │
├─────────────────────────────────────────────────────────┤
│ t1  │ u001    │ biz  │ inventory   │ 库存预警...  │      │  ← 内嵌页创建
│ t2  │ u001    │ biz  │ NULL        │ 客户分析...  │      │  ← 独立页创建
│ t3  │ u001    │ biz  │ forecast    │ 销售预测...  │      │  ← 其他业务页
└─────────────────────────────────────────────────────────┘
```

**Thread 生命周期**:

```
用户在库存页提问
  → usePageCopilot.ask()
  → SSE body: { question, page_context: { page: 'inventory', ... } }
  → 后端 CopilotEngine
  → persistence.get_or_create_thread(page_origin='inventory')
  → Thread 创建 (page_origin = 'inventory')
  → 用户继续对话...

  [场景 A] 需要深度分析
  → 点击 "在 Copilot 中打开" 按钮
  → router.push({ name: 'BizCopilot', query: { thread_id: 'xxx' } })
  → UnifiedCopilotPanel 加载该 thread，继续对话（完整功能）

  [场景 B] 用户离开再返回库存页
  → 右侧 AI Tab 调用 listThreads(page_origin='inventory')
  → 显示历史 thread 下拉列表
  → 用户选择 → 从后端重新加载 messages
```

**关键决策**: **不做实时双向同步**——用户同时只在一个页面。Thread 通过后端持久化作为共享状态，页面切换时从后端 reload 即可。

### 2.5.3 usePageCopilot 中的 Thread 管理

在 §3.1 的 `usePageCopilot` 基础上补充 thread 共享逻辑：

```js
// ── Thread 共享 ──

const currentThreadId = ref('')
const threadHistory = ref([])

// 加载当前页面的历史 threads（按 page_origin 过滤）
async function loadPageThreads() {
  try {
    const res = await listThreads({ mode, page_origin: pageName, limit: 20 })
    threadHistory.value = res.data?.threads || res.threads || []
  } catch { threadHistory.value = [] }
}

// 恢复上次的 thread（页面挂载时调用）
async function resumeLastThread() {
  await loadPageThreads()
  if (!threadHistory.value.length) return false
  const last = threadHistory.value[0]  // 按 updated_at DESC 排序
  currentThreadId.value = last.id
  try {
    const res = await getThreadMessages(last.id, { limit: 50 })
    messages.value = (res.data?.messages || res.messages || []).map(formatMsg)
    return true
  } catch { return false }
}

// 切换到另一个历史 thread
async function switchThread(threadId) {
  currentThreadId.value = threadId
  try {
    const res = await getThreadMessages(threadId, { limit: 50 })
    messages.value = (res.data?.messages || res.messages || []).map(formatMsg)
  } catch { messages.value = [] }
}

// 开始新 thread
function startNewThread() {
  currentThreadId.value = ''
  messages.value = []
}

// "在 Copilot 中打开" — 跳转独立页并携带 thread_id
function openInFullCopilot(router) {
  if (!currentThreadId.value) return
  router.push({ name: 'BizCopilot', query: { thread_id: currentThreadId.value } })
}

// ask() 中发送时携带 thread_id
await copilot.send(url, {
  question: q,
  thread_id: currentThreadId.value || undefined,  // ← 关键
  mode,
  page_context: { page: pageName, ... },
}, {
  onDone: (result) => {
    // 从 SSE header 或 run_start event 获取 thread_id
    if (result.threadId && !currentThreadId.value) {
      currentThreadId.value = result.threadId
    }
    ...
  },
})
```

### 2.5.4 独立 Copilot 页接收 thread_id（小改）

`UnifiedCopilotPanel.vue` 需补充：从 URL query 自动加载指定 thread。

```js
// UnifiedCopilotPanel.vue — onMounted 补充
import { useRoute } from 'vue-router'

const route = useRoute()

onMounted(() => {
  fetchThreads()
  // 从业务页跳转来时，自动加载携带的 thread
  if (route.query.thread_id) {
    loadThread(route.query.thread_id)
  }
  inputRef.value?.focus()
})
```

**改动范围**: 仅在 `onMounted` 追加 3 行，不影响现有逻辑。

### 2.5.5 后端补充：list_threads 支持 page_origin 过滤

`persistence.list_threads()` 已有 `mode` 过滤，追加 `page_origin` 可选参数：

```python
# persistence.py — list_threads 方法签名补充
async def list_threads(
    self,
    user_id: str,
    mode: Optional[str] = None,
    page_origin: Optional[str] = None,   # ← 新增
    status: str = "active",
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    ...
    if page_origin:
        sql += "AND page_origin = :page_origin "
        params["page_origin"] = page_origin
    ...
```

对应路由层也需透传此参数（`copilot_config.py` 或新增专用路由）。

### 2.5.6 Skill 作用域策略

| 场景 | `defaultSkills` | `@` 手动扩展 | 说明 |
|------|----------------|-------------|------|
| 库存页内嵌 | `['inventory_skill', 'kb_rag']` | 可 `@forecast` `@association` 等 | 默认只走库存+知识库 |
| 独立 Copilot 页 | 全部 11 个 | 全部可用 | CopilotEngine 自动路由 |

内嵌页通过 `defaultSkills` 引导默认路由，但**不做硬性屏蔽**——用户可通过 Command Bar 的 `@forecast`、`@sentiment` 等 mention 手动触发任意 skill。这样既降低噪音，又不丧失灵活性。

### 2.5.7 UI 差异化清单

内嵌版 AI Tab 相对于 `UnifiedCopilotPanel`（612 行）的精简与新增项：

| UnifiedCopilotPanel 功能 | 内嵌版处理 | 原因 |
|-------------------------|-----------|------|
| History Sidebar (260px) | ❌ **移除**，改为顶部 Thread 下拉选择器 | 右侧面板宽度有限（320px） |
| Mode Switch (Auto/Think/Research) | ❌ **移除**，固定 Auto | 降低认知负荷，库存场景不需要 Think/Research |
| Welcome 空状态 + Quick Questions | ✅ 保留但**简化** | 改为 3 个库存相关 suggestion chips |
| @ Mention Popup | ✅ 保留 | 跨 Agent 联动的核心入口 |
| Context Pills | ✅ 保留 + **增强** | 自动显示选中 SKU、矩阵筛选条件 |
| Streaming Markdown + █ Cursor | ✅ 保留 | 核心交互体验 |
| CopilotArtifactRenderer | ✅ 保留 | GenUI 能力的核心 |
| Suggestions Chips | ✅ 保留，**视觉更突出** | Action-oriented 是内嵌版的核心 |
| Feedback (👍👎) | ✅ 保留 | 持续数据收集 |
| Sources / Fact Check | ✅ 保留 | 可信度展示 |
| **"在 Copilot 中打开"** 按钮 | ✅ **新增** | Thread 共享跳转入口 |
| **Thread 下拉选择器** | ✅ **新增** | 替代 History Sidebar |
| **自动初始洞察** | ✅ **新增** | 页面加载自动 ask，独立页无此行为 |

### 2.5.8 上下文自动注入 vs 手动描述

这是内嵌版的核心价值——**零成本上下文传递**：

```
── 独立 Copilot 页 ──────────────────────────────────────
User: A001 这个 SKU 库存还有多少？需要补货吗？
       ↑ 用户需手动输入 SKU 编号，手动描述场景

── 库存页内嵌 ──────────────────────────────────────────
[用户点击表格中 A001 行]
  → AI 上下文自动更新:
    { selected_sku: 'A001',
      sku_name: '黄岩蜜橘（5斤装）',
      current_stock: 12,
      safety_stock: 45,
      alert_level: 'critical' }

User: 需要补货吗？
       ↑ 不需要说 SKU 编号，AI 已经知道全部信息
       
AI:  A001 黄岩蜜橘当前库存 12 件，低于安全库存 45 件，
     建议立即补货 120 件（EOQ 计算）...
     [InventoryArtifact 嵌入]
     [💡 Suggestion: "预测下月蜜橘需求" | "通知采购群" | "查补货SOP"]
```

### 2.5.9 状态同步边界

明确**不做**和**要做**的同步：

| 同步项 | 是否实现 | 说明 |
|--------|---------|------|
| Thread 消息实时双向同步 | ❌ 不做 | 用户同时只在一个页面，无需实时同步 |
| WebSocket push 通知 | ❌ 不做 | 复杂度高，收益低 |
| 切换页面时 reload thread | ✅ 做 | `onMounted → resumeLastThread()` |
| thread_id URL 传递 | ✅ 做 | "在 Copilot 中打开" 核心机制 |
| page_origin 过滤 | ✅ 做 | 内嵌页只看本页 thread |
| thread 标题自动生成 | ✅ 已有 | CopilotEngine 首条消息后 LLM 生成 |

---

## 3. 核心改造详解

### 3.1 usePageCopilot — 页面级 Copilot composable（新建）

**目的**: 封装 `useCopilotStream`，为业务页面提供开箱即用的 AI 对话能力，自动注入页面上下文。

```js
// composables/usePageCopilot.js

import { ref, computed } from 'vue'
import { useCopilotStream } from './useCopilotStream'
import { COPILOT_STREAM_URL } from '@/api/admin/copilot'

/**
 * @param {string}   pageName     — 页面标识，如 'inventory'
 * @param {string[]} defaultSkills — 默认关联的 skill id 列表
 * @param {string}   mode         — 'ops' | 'biz'
 */
export function usePageCopilot(pageName, defaultSkills = [], mode = 'biz') {
  const copilot = useCopilotStream()
  const messages = ref([])
  const pageContext = ref({})    // 动态上下文（选中行、筛选条件等）

  function setContext(ctx) {
    pageContext.value = { ...pageContext.value, ...ctx }
  }

  async function ask(question, extraMentions = []) {
    const q = question.trim()
    if (!q) return

    messages.value.push({ role: 'user', content: q, timestamp: Date.now() })

    const mentions = [
      ...defaultSkills.map(id => ({ type: 'skill', id })),
      ...extraMentions,
    ]

    const url = COPILOT_STREAM_URL[mode]
    await copilot.send(url, {
      question: q,
      mode,
      page_context: {
        page: pageName,
        think_mode: 'auto',
        mentions,
        ...pageContext.value,
      },
    }, {
      onDone: (result) => {
        messages.value.push({
          role: 'assistant',
          content: copilot.text.value,
          artifacts: [...copilot.artifacts.value],
          suggestions: [...copilot.suggestions.value],
          sources: [...copilot.sources.value],
          intent: copilot.intent.value,
          confidence: copilot.confidence.value,
          timestamp: Date.now(),
        })
      },
    })
  }

  // 快捷方法：触发特定 Agent
  function askAgent(skillId, question) {
    return ask(question, [{ type: 'skill', id: skillId }])
  }

  return {
    // 透传 stream 状态
    streaming: copilot.streaming,
    text: copilot.text,
    thinking: copilot.thinking,
    isThinking: copilot.isThinking,
    activeSkill: copilot.activeSkill,
    artifacts: copilot.artifacts,
    suggestions: copilot.suggestions,
    sources: copilot.sources,
    error: copilot.error,
    // Page-level
    messages,
    pageContext,
    setContext,
    ask,
    askAgent,
    stop: copilot.stop,
  }
}
```

**可复用性**: 其他页面（SalesForecast、CustomerAnalysis 等）只需：

```js
const ai = usePageCopilot('forecast', ['forecast', 'kb_rag'])
```

### 3.2 右侧面板三 Tab 设计

#### Tab 1: AI Copilot

- 使用已有 `ChatPanel.vue` 组件渲染消息流
- 通过 `usePageCopilot` 驱动 SSE streaming
- 聊天流中内嵌 `CopilotArtifactRenderer` → 渲染 `InventoryArtifact` / `ForecastArtifact` 等
- 底部显示 `suggestions` chips（由后端 skill 返回）
- 页面加载时自动触发一次 `ask("当前库存整体健康状况和补货建议")`

**上下文感知机制**:

```js
// 用户点击表格行时
function onRowClick(row) {
  selectedSku.value = row
  rightTab.value = 'detail'
  // 同时更新 AI 的上下文，后续提问自动携带
  ai.setContext({ selected_sku: row.sku_code, alert_level: row.alert_level })
}
```

#### Tab 2: SKU Detail

替代当前的 `ExplainDrawer`（抽屉遮罩层），改为右侧 inline panel：

- **基础信息**: SKU 编号、名称、门店、ABC-XYZ 分类
- **库存状态**: 当前/安全/EOQ/补货量/预警级别/紧急度
- **库存趋势折线图**: 30 天库存水位变化（纯 SVG path）
- **Agent 历史**: 该 SKU 最近被哪些 Agent 分析过（来自 `copilot_action_log`）
- **Action 按钮**: "让 AI 分析此 SKU" → 自动切到 AI tab 并提问

#### Tab 3: Knowledge Base

- 搜索框 → 调用 `kb_rag` skill
- 自动根据当前 SKU 分类推荐相关文档
- 展示格式：文档标题 + 来源标注 + 相关片段 highlight
- 后端扩展机制：新增知识库 collection → 自动出现在搜索结果中，**前端零改动**

```js
// KB 搜索实现
async function searchKB(query) {
  await ai.askAgent('kb_rag', query || `库存管理 ${selectedSku.value?.sku_code || ''} 补货`)
}
```

### 3.3 跨 Agent 联动矩阵

| 用户操作 / 问题 | 触发 Skill | 返回 Artifact | 渲染位置 |
|----------------|-----------|--------------|---------|
| 页面加载 → 自动问 "库存概览" | `inventory_skill` | `InventoryArtifact` | AI Tab |
| 选中紧急 SKU → "预测下月需求" | `forecast` | `ForecastArtifact` | AI Tab |
| 选中多行 → "关联商品分析" | `association` | `GenericTable` | AI Tab |
| 点击 suggestion "通知采购群" | `ActionExecutor` → Feishu | (操作确认 toast) | 页面 toast |
| 问 "补货 SOP" | `kb_rag` | `SearchResults` | AI Tab / KB Tab |
| 问 "客户对缺货怎么评价" | `sentiment` | `SentimentArtifact` | AI Tab |
| 问 "这个 SKU 欺诈风险" | `fraud` | (文本回复) | AI Tab |

**实现原理**: `useCopilotStream.send()` 发送 `page_context.mentions` → 后端 `CopilotEngine` 路由到对应 Skill → SSE 返回 artifact_start/delta/end → 前端 `CopilotArtifactRenderer` 动态挂载对应 Vue 组件。

**后端已完备**（无需改动的部分）:
- `backend/copilot/engine.py` — LLM 路由 + skill 执行
- `backend/copilot/skills/` — 11 个 skill 已就绪
- `backend/copilot/events.py` — 16 种 SSE event type
- `backend/copilot/registry.py` — auto_discover 自动注册

### 3.4 交互增强

#### 3.4.1 KPI Cards → Odometer 动画

**改动**: `StatCardV2` 的 value 使用 `Odometer.vue` 包裹。

```html
<StatCardV2 label="SKU 总数">
  <template #value>
    <Odometer :value="status.total_skus ?? 0" />
  </template>
</StatCardV2>
```

- 数据加载完成时数字从 0 滚动到实际值（easeOutQuart 缓动）
- 点击 KPI 卡片 → 过滤表格（如点击 "紧急" → 表格只显示 critical）

#### 3.4.2 Alert Table → Smart Table + Sparkline

新增 `StockSparkline.vue`：纯 SVG inline 组件，无依赖。

```html
<!-- 表格列中嵌入 -->
<el-table-column label="趋势" width="80">
  <template #default="{ row }">
    <StockSparkline :data="row.stock_history_7d" :safety="row.safety_stock" />
  </template>
</el-table-column>
```

**Sparkline 设计规范**:
- 尺寸: 64×24px
- 线色: `var(--v2-text-3)` (zinc-500)
- 安全库存线: 虚线 `var(--v2-error)` (红色)
- 低于安全线部分: 面积填充 `rgba(220,38,38,0.08)`

**批量操作**: 表格左侧 checkbox → 选中多行 → 底部浮出 action bar：
- "一键生成补货单"
- "让 AI 分析选中 SKU"
- "通知采购群"

#### 3.4.3 ABC-XYZ Matrix → Interactive Heatmap

新建 `InventoryHeatmap.vue`：

```
设计规范:
- 3×3 grid，行 = A/B/C (价值)，列 = X/Y/Z (波动性)
- 颜色 intensity: 按 SKU 数量映射到 zinc-100 → zinc-800 灰阶
  （非红绿，遵循 Zinc 单色调设计语言）
- Hover: 弹出 tooltip 显示 { cell, count, top3 SKU, strategy }
- Click: 
  ① 过滤左侧 Alert Table
  ② 右侧 AI Tab 自动提问 "AX 分类的 SKU 补货建议"
- Active 态: 2px brand-primary 描边 + 微弱阴影
- 格子内: 分类标签 (AX) + 数量 + 策略摘要 (单行截断)
```

#### 3.4.4 趋势图（30 天全局库存健康度）

新增区块：纯 SVG path 折线图（不引入 ECharts 依赖）。

```
数据: GET /inventory/trend → [{ date, health_pct, warning_count, critical_count }]
展示: 一条灰色折线 (health_pct) + 红色面积 (critical 区域)
尺寸: 宽度 100%，高度 120px
交互: hover 显示日期 + 数值 tooltip
```

### 3.5 Command Bar（底部命令栏）

新建 `InventoryCommandBar.vue`：

```
位置: 页面底部固定
功能:
- 输入框: auto-resize textarea（复用 ChatPanel 的 input 逻辑）
- @ mention: 输入 @ 弹出 skill 选择器（inventory/forecast/association/kb_rag）
- Context pills: 显示当前筛选条件（选中的矩阵格、预警级别等）
- 发送 → 调用 usePageCopilot.ask()，结果显示在右侧 AI Tab
- ⌘K 快捷键: 聚焦到 Command Bar
```

---

## 4. 后端补充改动

### 4.1 新增 `/inventory/trend` 端点

```python
# backend/routers/inventory.py

@router.get("/trend", summary="30天库存健康度趋势")
async def get_inventory_trend(
    days: int = Query(30, ge=7, le=90),
    svc: InventoryService = Depends(_svc),
):
    return await svc.get_trend(days)
```

### 4.2 InventoryService.get_trend()

```python
# backend/services/inventory_service.py

async def get_trend(self, days: int = 30) -> dict:
    """生成最近 N 天的库存健康度趋势数据"""
    # 优先从 Redis 缓存读取
    # 降级: 基于 CSV 快照 + 随机波动模拟
    # 返回: { "trend": [{ "date": "2026-04-01", "health_pct": 72.1, ... }] }
```

### 4.3 Alert 数据补充 `stock_history_7d` 字段

在 `get_alerts()` 返回中补充每个 SKU 的 7 天库存历史（用于 Sparkline）：

```python
# 如无真实历史数据，基于当前库存 + CV 模拟 7 个数据点
if "stock_history_7d" not in df.columns:
    df["stock_history_7d"] = df.apply(
        lambda r: _simulate_7d_history(r["current_stock"], r.get("CV", 0.5)),
        axis=1,
    )
```

---

## 5. 文件清单

### 新建文件

| 文件 | 类型 | 说明 |
|------|------|------|
| `frontend/src/composables/usePageCopilot.js` | Composable | 页面级 Copilot 封装（可复用） |
| `frontend/src/components/inventory/InventoryHeatmap.vue` | Component | ABC-XYZ 交互热力图 |
| `frontend/src/components/inventory/StockSparkline.vue` | Component | 7 天库存趋势 SVG |
| `frontend/src/components/inventory/InventoryCommandBar.vue` | Component | 底部命令栏 |
| `frontend/src/components/inventory/KBSearchPanel.vue` | Component | 知识库搜索面板 |
| `frontend/src/components/inventory/InventoryTrendChart.vue` | Component | 30 天趋势折线图 |
| `frontend/src/components/inventory/SkuDetailPanel.vue` | Component | SKU 详情右侧面板 |

### 重写文件

| 文件 | 改动范围 | 说明 |
|------|---------|------|
| `frontend/src/views/business/InventoryManagement.vue` | **全量重写** | SplitInspector 布局 + 所有新组件集成 |

### 小改文件

| 文件 | 改动范围 | 说明 |
|------|---------|------|
| `frontend/src/api/business/inventory.js` | +1 方法 | 新增 `getTrend()` |
| `frontend/src/components/copilot/UnifiedCopilotPanel.vue` | +3 行 | `onMounted` 支持从 URL query 加载 `thread_id`（§2.5.4） |
| `backend/routers/inventory.py` | +1 端点 | 新增 `GET /inventory/trend` |
| `backend/services/inventory_service.py` | +2 方法 | `get_trend()` + alerts 补充 `stock_history_7d` |
| `backend/schemas/inventory_schemas.py` | +1 schema | `InventoryTrendItem` |
| `backend/copilot/persistence.py` | +3 行 | `list_threads()` 追加 `page_origin` 过滤参数（§2.5.5） |
| `backend/routers/admin/copilot_config.py` | +1 参数 | threads 列表接口透传 `page_origin` query param |

### 不需要改动的文件

| 文件 | 原因 |
|------|------|
| `backend/copilot/` 大部分 | Engine/Skills/Events/Registry 已完备（仅 `persistence.py` 追加 3 行） |
| `backend/agents/inventory_agent.py` | Agent 契约不变 |
| `frontend/src/composables/useCopilotStream.js` | usePageCopilot 封装它，不修改 |
| `frontend/src/components/copilot/artifacts/InventoryArtifact.vue` | Artifact 渲染不变 |
| `frontend/src/components/v2/` 全部 | 只使用，不修改 |

---

## 6. 知识库兼容性设计

### 6.1 当前机制

```
用户提问 → CopilotEngine → 路由到 kb_rag skill → 检索向量库 → 返回 sources + text
```

### 6.2 前端适配

- KB Tab 内的搜索调用 `usePageCopilot.askAgent('kb_rag', query)`
- 结果通过 SSE `sources` event 渲染为文档卡片列表
- 自动补充 `page_context.page = 'inventory'`，后端 kb_rag skill 可据此过滤 collection

### 6.3 后续扩展（零前端改动）

```
新增知识库 → 后端新建 collection / 导入文档 → kb_rag skill 自动检索到
→ 前端 sources 列表自动显示新来源
→ 无需任何前端代码变更
```

---

## 7. 数据流全景

```
┌─────────────┐     ┌───────────────────┐     ┌──────────────────┐
│  用户操作     │     │  usePageCopilot   │     │  Backend          │
│              │     │  (SSE Client)      │     │                   │
│ 1.页面加载   │────▶│ ask("库存概览")    │────▶│ CopilotEngine     │
│ 2.点击行     │     │ setContext(sku)    │     │   ↓               │
│ 3.输入问题   │     │ ask(question)      │     │ InventorySkill    │
│ 4.点击suggest│     │ askAgent(skillId)  │     │ ForecastSkill     │
│ 5.搜索KB    │     │                    │     │ KBRagSkill        │
└─────────────┘     └────────┬──────────┘     │ AssociationSkill  │
                             │                 │ SentimentSkill    │
                    SSE Events (streaming)     └────────┬──────────┘
                             │                          │
                    ┌────────▼──────────┐      ┌───────▼─────────┐
                    │  右侧 AI Tab       │      │  Services       │
                    │  ・text streaming   │      │  ・Inventory     │
                    │  ・artifacts        │◀─────│  ・Forecast      │
                    │  ・suggestions      │      │  ・KB RAG        │
                    │  ・sources          │      │  ・Association   │
                    └────────┬──────────┘      └─────────────────┘
                             │
                   ┌─────────▼──────────┐
                   │  copilot_threads    │   ← Thread 共享层
                   │  (MySQL 持久化)      │
                   │  page_origin 标记    │
                   └─────────┬──────────┘
                             │
              ┌──────────────▼──────────────┐
              │  "在 Copilot 中打开" 跳转     │
              │  → BizCopilot.vue            │
              │  → UnifiedCopilotPanel       │
              │  → loadThread(thread_id)     │
              │  → 继续完整功能对话           │
              └─────────────────────────────┘
```

---

## 8. 设计规范

### 8.1 配色（遵循 Zinc 单色调）

| 元素 | 色值 | 说明 |
|------|------|------|
| Heatmap 低 | `var(--v2-gray-100)` | SKU 数量 ≤ 2 |
| Heatmap 中 | `var(--v2-gray-300)` | SKU 数量 3~5 |
| Heatmap 高 | `var(--v2-gray-600)` | SKU 数量 > 5 |
| Critical 标记 | `var(--v2-error)` | 仅用于紧急状态，不做装饰 |
| Sparkline 线 | `var(--v2-text-3)` | zinc-500 |
| Sparkline 危险区 | `rgba(220,38,38,0.08)` | 低于安全线的面积 |
| AI Tab 背景 | `var(--v2-ai-purple-bg)` | 与 InsightPanelV2 一致 |

### 8.2 字体

- 数值列 / KPI: `font-variant-numeric: tabular-nums` (已有)
- SKU 编号: `Geist Mono` (已有)
- 正文: `Geist Sans` (已有)

### 8.3 动画

| 场景 | 实现 | 时长 |
|------|------|------|
| KPI 数字加载 | `Odometer.vue` easeOutQuart | 800ms |
| 右侧面板展开/折叠 | CSS transition `width` | 300ms |
| 矩阵格子 hover | `border-color` transition | `var(--v2-trans-fast)` |
| Sparkline 绘制 | SVG stroke-dashoffset animation | 600ms |
| AI 打字光标 | `cp__cursor` blink animation | 1s (已有) |

### 8.4 响应式

| 断点 | 布局 |
|------|------|
| ≥ 1400px | SplitInspector 2 栏 (main + right 320px) |
| 1100~1400px | SplitInspector 2 栏 (main + right 280px) |
| < 1100px | 单栏，右侧面板变为底部 Sheet / Drawer |

---

## 9. 实施阶段

### Phase 1: 核心架构（优先级最高）

**目标**: 页面能与 Agent 对话，AI 不再是假的；内嵌版与独立 Copilot 页通过 Thread 共享打通。

| 任务 | 文件 | 工作量 |
|------|------|--------|
| 新建 `usePageCopilot.js`（含 Thread 管理 §2.5.3） | composables/ | 0.5d |
| 重构 `InventoryManagement.vue` 为 SplitInspector 布局 | views/business/ | 1d |
| 右侧 AI Tab（嵌入 ChatPanel + CopilotArtifactRenderer） | 内嵌于主页面 | 0.5d |
| 页面加载自动 ask + 行选中上下文注入 | 内嵌于主页面 | 0.5d |
| Thread 共享：persistence `page_origin` 过滤（§2.5.5） | backend/copilot/ | 0.2d |
| Thread 共享：UnifiedCopilotPanel 接收 URL query（§2.5.4） | components/copilot/ | 0.1d |
| Thread 共享："在 Copilot 中打开" + Thread 下拉选择器 | 内嵌于主页面 | 0.3d |

**验收标准**:
- [ ] 页面右侧 AI Tab 可输入问题并获得 streaming 回复
- [ ] 点击表格行后，AI 上下文自动包含选中 SKU
- [ ] AI 回复中嵌入 InventoryArtifact 可正常渲染
- [ ] Suggestions 可点击触发后续提问
- [ ] "在 Copilot 中打开" 跳转后独立页能加载并继续对话
- [ ] 返回库存页后 AI Tab 能恢复上次 thread
- [ ] Thread 下拉选择器显示本页历史对话

### Phase 2: 交互增强

**目标**: 视觉对标 Linear/Vercel 水平。

| 任务 | 文件 | 工作量 |
|------|------|--------|
| `StockSparkline.vue` | components/inventory/ | 0.5d |
| `InventoryHeatmap.vue` | components/inventory/ | 0.5d |
| KPI 使用 Odometer + 点击过滤 | 主页面内 | 0.3d |
| `SkuDetailPanel.vue` (右侧 Detail Tab) | components/inventory/ | 0.5d |
| 表格批量操作 action bar | 主页面内 | 0.3d |

### Phase 3: 知识库 + Command Bar

**目标**: 完成知识库闭环 + 高级交互。

| 任务 | 文件 | 工作量 |
|------|------|--------|
| `KBSearchPanel.vue` | components/inventory/ | 0.5d |
| `InventoryCommandBar.vue` | components/inventory/ | 0.5d |
| ⌘K 快捷键绑定 | 主页面内 | 0.2d |

### Phase 4: 趋势图 + Action 集成

**目标**: 全功能上线。

| 任务 | 文件 | 工作量 |
|------|------|--------|
| 后端 `GET /inventory/trend` + `stock_history_7d` | backend/ | 0.5d |
| `InventoryTrendChart.vue` | components/inventory/ | 0.5d |
| 飞书通知 Action 集成 | 主页面 + api | 0.3d |
| 前端 `getTrend()` API | api/business/ | 0.1d |

---

## 10. 风险与缓解

| 风险 | 缓解策略 |
|------|---------|
| Copilot SSE 后端未启动 / LLM key 缺失 | AI Tab 降级为静态文本（复用当前 computed 逻辑作为 fallback） |
| KB collection 为空 | KB Tab 显示 "暂无知识库文档，请联系管理员上传" |
| CSV 数据不存在 | 已有 Mock 数据降级机制，保持不变 |
| 右侧面板在小屏上挤压 | < 1100px 自动切为底部 Sheet |
| usePageCopilot 跨页面复用时 context 泄漏 | composable 内部 onUnmounted 自动 stop + reset |
| Thread 跳转后独立页找不到 thread | `loadThread` 已有 try-catch，找不到时 fallback 为新对话 |
| 内嵌版与独立页消息不一致 | 不做实时同步；每次进入页面从后端 reload，保证最终一致 |

---

## 11. 后续可复用

`usePageCopilot` 设计完成后，以下页面可快速升级为同等智能交互：

| 页面 | 调用方式 |
|------|---------|
| `SalesForecast.vue` | `usePageCopilot('forecast', ['forecast', 'kb_rag'])` |
| `CustomerAnalysis.vue` | `usePageCopilot('customer', ['customer_intel', 'kb_rag'])` |
| `SentimentAnalysis.vue` | `usePageCopilot('sentiment', ['sentiment', 'kb_rag'])` |
| `FraudDetection.vue` | `usePageCopilot('fraud', ['fraud', 'kb_rag'])` |
| `AssociationAnalysis.vue` | `usePageCopilot('association', ['association', 'kb_rag'])` |

每个页面只需 **1 行代码** 即可接入完整 AI + 知识库能力。

---

## 12. 验收 Checklist

- [ ] P1: 右侧 AI Tab streaming 对话正常
- [ ] P1: 页面加载自动生成 AI 洞察
- [ ] P1: 行选中后 AI 上下文感知
- [ ] P1: Suggestions 可点击
- [ ] P1: Thread 共享 — "在 Copilot 中打开" 跳转后独立页能加载并继续对话
- [ ] P1: Thread 共享 — 返回库存页后 AI Tab 能恢复上次 thread
- [ ] P1: Thread 共享 — page_origin 过滤正常（内嵌页只看 inventory 相关 thread）
- [ ] P2: KPI Odometer 动画
- [ ] P2: Alert Table Sparkline 渲染
- [ ] P2: ABC-XYZ Heatmap hover/click 交互
- [ ] P2: Detail Tab SKU 详情
- [ ] P3: KB Tab 搜索 + 文档渲染
- [ ] P3: Command Bar 输入 + @ mention
- [ ] P4: 30 天趋势图
- [ ] P4: 飞书通知 Action
- [ ] 全局: 响应式 < 1100px 正常
- [ ] 全局: AI 后端不可用时优雅降级
