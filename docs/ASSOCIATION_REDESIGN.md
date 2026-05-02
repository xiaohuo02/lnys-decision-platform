# 关联分析页面重构设计文档

> **版本**: v1.0  
> **日期**: 2026-04-08  
> **状态**: Draft — 待评审  
> **涉及模块**: `frontend/src/views/business/AssociationAnalysis.vue` 及关联组件/后端  
> **前置依赖**: `usePageCopilot.js` (已由库存页重构产出，直接复用)

---

## 1. 背景与目标

### 1.1 现状问题

| # | 问题 | 现状描述 | 影响 |
|---|------|---------|------|
| P1 | AI 洞察是伪实现 | `insightText` 是 `computed()` 拼模板字符串，无 LLM 调用 | 失去 AI 平台核心卖点 |
| P2 | 无 Agent 联动 | 页面纯 REST → `AssociationService`，不经过 Agent/Copilot | `AssociationSkill` + `AssociationAgent` 形同虚设 |
| P3 | 无跨 Agent 编排 | 无法从关联分析页发起 "预测需求"(forecast)、"客户分析"(customer) | 决策信息割裂；搭配推荐无法考虑客群偏好/库存状态 |
| P4 | 无知识库接入 | 无法查阅交叉营销 SOP、陈列策略文档、供应商捆绑协议 | 运营只看到关联规则数字，不知如何执行 |
| P5 | 关联网络缺少可视化 | 无商品关联拓扑图，仅有 Tag 平铺；用户无法直觉感知"哪些商品簇"频繁共现 | 对标 Neo4j/Gephi 差距极大 |
| P6 | 推荐交互原始 | 手动输入 SKU 编码获取推荐，无法从表格/图谱直接触发 | 操作门槛高，不符合"点击即探索"原则 |
| P7 | 表格无深度 | 无 Sparkline、无 mini bar、Lift/Conf 纯数字无视觉映射 | 对标 Linear/Datadog 差距大 |
| P8 | 高级组件闲置 | 已有 `SplitInspector`、`ChatPanel`、`Odometer`、`CopilotArtifactRenderer` 但未使用 | 设计系统 ROI 低 |

### 1.2 设计目标

1. **智能体联动**: 页面内嵌 Copilot Chat，可调用 association/inventory/forecast/kb_rag/sentiment/customer_intel 等任意 Skill
2. **知识库兼容**: 右侧 KB Tab 接入 `kb_rag` skill，后续新增知识库只需后端注入 collection，前端零改动
3. **关联网络可视化**: 新增 Force-Directed Graph（Canvas 2D 渲染），直观呈现商品共现拓扑
4. **交互对标**: 对齐 Linear + Vercel + Neo4j Bloom 级别的视觉与交互品质
5. **架构可复用**: 直接复用 `usePageCopilot` composable，一行代码接入

### 1.3 对标参考

| 平台 | 借鉴点 |
|------|--------|
| **Neo4j Bloom** | Force-Directed 关联网络图，节点大小=频次，边粗细=Lift，hover展开邻居，click锁定探索 |
| **Linear** | SplitInspector 三栏布局、行点击→右侧 Detail Panel |
| **Vercel** | 极简 KPI strip + Odometer 动画数字、hairline 分隔 |
| **ChatGPT** | 页面内嵌 AI Chat、streaming artifact、follow-up suggestions |
| **Datadog** | Heatmap 矩阵、表格内嵌 mini bar、drill-down 交互 |
| **Shopify Analytics** | 交叉销售可视化、商品搭配推荐卡片、营销 SOP 联动 |
| **Notion AI** | 上下文感知——选中规则/节点后 AI 自动理解 "你在看哪条关联" |

---

## 2. 目标布局

```
┌──────────────────────────────────────────────────────────────────┐
│  PageHeaderV2: 关联分析                           [⌘K]  [AI ◀▸] │
├─────────────────────────────────┬────────────────────────────────┤
│  Main Content (scrollable)      │  Right Panel (tab-switch)      │
│                                 │                                │
│  ┌─ KPI Strip (Odometer) ────┐ │  ┌─ [🤖 AI] [📋 Detail] [📚 KB] ─┐ │
│  │ Rules │ MaxLift│MaxConf│N │ │  │                              │ │
│  │  42   │ 5.10  │ 0.812│ 6 │ │  │  Scoped Copilot Chat         │ │
│  └───────────────────────────┘ │  │  ・streaming markdown        │ │
│                                 │  │  ・inline AssociationArtifact│ │
│  ┌─ Association Network ─────┐ │  │  ・cross-agent artifacts     │ │
│  │                           │ │  │                              │ │
│  │   [A001]──3.8──[A003]     │ │  │  Suggested Follow-ups:       │ │
│  │      \        /           │ │  │  "这些商品如何做搭配陈列？"   │ │
│  │   [B002]──2.1──[D003]     │ │  │  "查询交叉营销SOP"           │ │
│  │      Force-Directed Graph │ │  │  "通知运营群设置组合促销"     │ │
│  └───────────────────────────┘ │  └──────────────────────────────┘ │
│                                 │                                │
│  ┌─ Rules Table (Sortable) ──┐ │  [Detail Tab]                  │
│  │ #│前项 │→│后项 │Sup│Conf│  │ │  选中规则/商品的详细信息：     │
│  │  │Tags │ │Tags │▎▎ │▎▎▎ │  │ │  ・规则完整指标               │
│  │  │     │ │     │bar│bar │Lift│ │  ・关联商品列表               │
│  └───────────────────────────┘ │  ・Agent 历史分析记录           │
│                                 │                                │
│  ┌─ Smart Recommend ─────────┐ │  [KB Tab]                      │
│  │ 选中商品的搭配推荐卡片     │ │  搜索交叉营销策略/陈列SOP      │
│  │ (由 AI + 规则双重驱动)     │ │  /捆绑协议文档                 │
│  └───────────────────────────┘ │  由 kb_rag skill 驱动          │
│                                 │                                │
├─────────────────────────────────┴────────────────────────────────┤
│  Command Bar: 输入关联分析问题...  [@association] [@inventory]    │
└──────────────────────────────────────────────────────────────────┘
```

**布局实现**: 使用已有 `SplitInspector.vue`（2 栏模式：main + right 320px），右侧面板支持折叠。

---

## 2.5 独立 Copilot 页 vs 页面内嵌 — 架构定位

与库存页重构方案 (INVENTORY_REDESIGN.md §2.5) 完全一致，此处不重复。核心差异点：

| 维度 | 关联分析内嵌版 |
|------|---------------|
| **默认 Skills** | `['association_skill', 'kb_rag']` |
| **自动初始问题** | `"当前商品关联规则概览和强关联商品对"` |
| **上下文注入** | `selected_rule` (规则详情) / `selected_node` (图谱节点 SKU) / `filter_min_lift` |
| **Thread page_origin** | `'association'` |
| **@ 可扩展 Skills** | `@inventory` `@forecast` `@customer_intel` `@sentiment` `@fraud` |

---

## 3. 核心改造详解

### 3.1 usePageCopilot 接入（一行代码）

```js
// AssociationAnalysis.vue — <script setup>
const ai = usePageCopilot('association', ['association_skill', 'kb_rag'])
```

已有 `usePageCopilot.js` (304 行) 提供完整能力：
- SSE streaming + 16 event type 解析
- Thread 管理（创建/恢复/切换/跳转独立页）
- page_context 自动注入
- Skill 作用域引导
- AI 后端不可用时优雅降级

### 3.2 关联网络可视化 — AssociationGraph.vue（新建）

**核心组件**，是本页面区别于库存页的最大特色。

#### 设计规范

```
渲染引擎: Canvas 2D (不用 WebGL，关联规则通常 < 500 节点，Canvas 足够)
布局算法: Force-Directed (d3-force)，引入 d3-force 的 forceSimulation
           ─ 不引入完整 d3，仅用 d3-force 子包 (~15KB gzip)

节点 (Node):
  - 形状: 圆形
  - 大小: 按 SKU 出现频次映射 (r = 6~24px)
  - 颜色: var(--v2-text-1) 填充 + var(--v2-bg-card) 描边
  - 标签: SKU 名称 (Geist Sans, var(--v2-text-xs))
  - Hover: 半径 +4px + 1px brand 描边，tooltip 显示 SKU 编码/名称/出现次数
  - Click: 锁定选中态 (2px brand 描边)
           → 高亮相连边和邻居节点，未连接节点降低透明度
           → 右侧切到 Detail Tab 显示该 SKU 的所有关联规则
           → 更新 AI 上下文 setContext({ selected_node: skuCode })
           → 推荐区自动显示该 SKU 的搭配推荐

边 (Edge):
  - 粗细: 按 Lift 值映射 (strokeWidth = 0.5 ~ 4px)
  - 颜色: var(--v2-text-4)，Lift > 3 时用 var(--v2-text-2)
  - Hover: 显示 tooltip { 前项→后项, Lift, Confidence }

交互:
  - 拖拽: 节点可自由拖拽重新定位
  - 缩放: 滚轮缩放 + 双指 pinch
  - 筛选: 与顶部 min_lift 筛选联动，动态增减节点和边
  - 双击节点: 触发 AI 提问 "分析 {SKU名称} 的关联商品和搭配推荐"

颜色约束 (Zinc 单色调):
  - 无彩色。仅通过透明度和线粗区分强度。
  - 选中/高亮时才出现 brand-primary (极克制)。
```

#### 数据转换

```js
// 将规则表 → 图数据结构
function rulesToGraph(rules) {
  const nodeMap = new Map()
  const edges = []

  rules.forEach(rule => {
    const ants = toArr(rule.antecedents)
    const cons = toArr(rule.consequents)
    ;[...ants, ...cons].forEach(sku => {
      if (!nodeMap.has(sku)) {
        nodeMap.set(sku, {
          id: sku,
          name: _skuToName(sku, rule),
          frequency: 0,
        })
      }
      nodeMap.get(sku).frequency++
    })

    // 为每对 antecedent → consequent 创建边
    ants.forEach(a => {
      cons.forEach(c => {
        edges.push({
          source: a,
          target: c,
          lift: rule.lift,
          confidence: rule.confidence,
          support: rule.support,
        })
      })
    })
  })

  return {
    nodes: [...nodeMap.values()],
    edges,
  }
}
```

#### 性能保障

- 节点 < 100：直接 Canvas 绑定 requestAnimationFrame
- 节点 100~500：simulation warmup 300 ticks 后静止，交互时才唤醒
- 节点 > 500：自动降级为 Top 100 Lift 的子图 + 提示 "显示部分高关联节点"

### 3.3 右侧面板三 Tab 设计

#### Tab 1: AI Copilot

- 使用已有 `ChatPanel.vue` 渲染消息流
- 通过 `usePageCopilot` 驱动 SSE streaming
- 聊天流中内嵌 `CopilotArtifactRenderer` → 渲染 `GenericTableArtifact` / `InventoryArtifact` 等
- 底部显示 `suggestions` chips
- **页面加载时自动触发**: `ask("当前商品关联规则概览和强关联商品对")`

**上下文感知机制**:

```js
// 用户点击图谱节点时
function onNodeClick(node) {
  selectedNode.value = node
  rightTab.value = 'detail'
  ai.setContext({
    selected_node: node.id,
    selected_node_name: node.name,
    node_frequency: node.frequency,
  })
}

// 用户点击规则表行时
function onRuleClick(rule) {
  selectedRule.value = rule
  rightTab.value = 'detail'
  ai.setContext({
    selected_rule: {
      antecedents: rule.antecedents,
      consequents: rule.consequents,
      lift: rule.lift,
      confidence: rule.confidence,
    },
  })
}
```

#### Tab 2: Rule / SKU Detail

替代当前的 `ExplainDrawer`，改为右侧 inline panel，根据选中类型切换内容：

**选中规则时**:
- 前项/后项商品 Tag（含 SKU 名称）
- 完整指标：Support / Confidence / Lift / Conviction / Leverage
- 该规则的商品在网络图中高亮
- Action 按钮："让 AI 分析此搭配的营销价值" → 切到 AI Tab 自动提问

**选中图谱节点时**:
- SKU 基础信息（编码、名称）
- 关联规则列表（该 SKU 参与的所有规则，按 Lift 排序）
- 推荐搭配列表（前 5 个最强关联商品）
- Action 按钮："查看此 SKU 库存状态" → `askAgent('inventory_skill', ...)`

#### Tab 3: Knowledge Base

- 搜索框 → 调用 `kb_rag` skill
- 自动根据当前选中商品推荐相关营销文档
- 典型知识库内容：交叉营销策略、搭配陈列 SOP、组合促销模板、供应商捆绑协议
- 展示格式：文档标题 + 来源标注 + 相关片段 highlight

```js
async function searchKB(query) {
  await ai.askAgent('kb_rag', query || `关联分析 交叉营销 ${selectedNode.value?.name || ''} 搭配推荐`)
}
```

**后续扩展（零前端改动）**: 新增知识库 collection → 后端导入文档 → `kb_rag` skill 自动检索到 → 前端 sources 列表自动显示新来源。

### 3.4 跨 Agent 联动矩阵

| 用户操作 / 问题 | 触发 Skill | 返回 Artifact | 渲染位置 |
|----------------|-----------|--------------|---------|
| 页面加载 → 自动问 "关联规则概览" | `association_skill` | `GenericTableArtifact` | AI Tab |
| 选中高 Lift 商品对 → "怎么做搭配促销" | `association_skill` + LLM | (文本建议) | AI Tab |
| 问 "A001 下月销量预测" | `forecast` | `ForecastArtifact` | AI Tab |
| 问 "A001 库存够不够做促销" | `inventory_skill` | `InventoryArtifact` | AI Tab |
| 问 "买这对商品的客户画像" | `customer_intel` | `CustomerArtifact` | AI Tab |
| 问 "这个搭配的客户评价如何" | `sentiment` | `SentimentArtifact` | AI Tab |
| 点击 suggestion "通知运营群设置组合促销" | `ActionExecutor` → Feishu | (操作确认 toast) | 页面 toast |
| 问 "交叉营销 SOP" | `kb_rag` | `SearchResultsArtifact` | AI Tab / KB Tab |
| 问 "这对商品有欺诈风险吗" | `fraud` | (文本回复) | AI Tab |

**实现原理**: 与库存页完全一致——`usePageCopilot.ask()` → SSE → `CopilotEngine` → Skill → Artifact → `CopilotArtifactRenderer` 动态挂载。

### 3.5 交互增强

#### 3.5.1 KPI Cards → Odometer 动画

```html
<StatCardV2 label="规则总数">
  <template #value><Odometer :value="rules.length" /></template>
</StatCardV2>
<StatCardV2 label="最高 Lift">
  <template #value><Odometer :value="topLift" :decimals="2" /></template>
</StatCardV2>
<StatCardV2 label="最高 Conf">
  <template #value><Odometer :value="topConf" :decimals="3" /></template>
</StatCardV2>
<StatCardV2 label="强关联对">
  <template #value><Odometer :value="strongPairCount" /></template>
</StatCardV2>
```

- 4 列 Grid（新增"强关联对" = Lift > 3 的规则数）
- 数据加载完成时数字从 0 滚动到实际值（easeOutQuart 缓动）
- 点击 "强关联对" KPI → 规则表筛选 Lift > 3 + 图谱只显示强关联

#### 3.5.2 Rules Table → Smart Table + Mini Bars

替代当前 `el-table` 的纯数字列，增加视觉映射：

```
Support 列: 右侧 mini 灰色 bar (宽度按比例映射)
Confidence 列: 右侧 mini 灰色 bar
Lift 列: 数字 + 颜色强度
  - Lift > 3: var(--v2-text-1) + font-weight:700 (强关联)
  - Lift 1.5~3: var(--v2-text-2) + font-weight:600
  - Lift < 1.5: var(--v2-text-3) (弱关联)
```

新增 `LiftMiniBar.vue`：纯 SVG inline 组件，20×12px。

```html
<el-table-column label="Lift" width="100" sortable>
  <template #default="{ row }">
    <div class="ar__lift-cell">
      <LiftMiniBar :value="row.lift" :max="maxLift" />
      <span :class="liftClass(row.lift)">{{ row.lift?.toFixed(2) }}</span>
    </div>
  </template>
</el-table-column>
```

**行交互**:
- Hover：高亮图谱中对应的边和节点
- Click：右侧切 Detail Tab 显示规则详情
- 行选中态与图谱选中态双向同步

#### 3.5.3 Smart Recommend → Context-Aware 推荐区

取代当前手动输入 SKU 的推荐方式：

```
触发方式 (任选其一，均自动触发):
1. 点击图谱中任意节点 → 自动推荐该 SKU 的搭配商品
2. 点击规则表中任意行 → 自动推荐该前项商品的搭配
3. 手动在 Command Bar 输入 → AI 返回推荐

推荐卡片设计:
┌─────────────────────────────┐
│  SKU: A003 · 永春芦柑(3斤装)  │
│  Lift 3.80  Conf 72%        │
│  ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈ │
│  📋 关联来源: 购物篮共现      │
│  [查看库存] [AI分析搭配价值]   │
│  [加入促销方案]               │
└─────────────────────────────┘

卡片内 Action 按钮:
- "查看库存": askAgent('inventory_skill', `${sku} 库存状态`)
- "AI分析搭配价值": ask(`分析 ${baseSku} 和 ${recSku} 的搭配营销价值`)
- "加入促销方案": Action → 触发 HITL 确认流程
```

#### 3.5.4 Top 关联关系可视化 → Pair Cards 增强

保留现有 Pair Cards 区域，但增强交互：

- Hover：对应图谱边高亮 + 微弱脉冲动画
- Click：双向同步——选中 Pair 后图谱缩放到该边的位置
- 新增"策略标签"：基于 Lift/Conf 自动标注策略类型
  - Lift > 4: "核心搭配"
  - Lift 2~4: "推荐搭配"
  - Conf > 0.8: "高确定性"

### 3.6 Command Bar（底部命令栏）

新建 `AssociationCommandBar.vue`：

```
位置: 页面底部固定
功能:
- 输入框: auto-resize textarea
- @ mention: 输入 @ 弹出 skill 选择器（association/inventory/forecast/customer_intel/kb_rag）
- Context pills: 显示当前选中的节点/规则/筛选条件
- 发送 → 调用 usePageCopilot.ask()，结果显示在右侧 AI Tab
- ⌘K 快捷键: 聚焦到 Command Bar
```

---

## 4. 后端补充改动

### 4.1 新增 `/association/graph` 端点

```python
# backend/routers/association.py

@router.get("/graph", summary="关联网络图谱数据（节点+边）")
async def get_graph(
    min_lift: float = Query(1.5, ge=0.0),
    max_nodes: int = Query(100, le=500),
    svc: AssociationService = Depends(_svc),
):
    return await svc.get_graph(min_lift, max_nodes)
```

### 4.2 AssociationService.get_graph()

```python
# backend/services/association_service.py

async def get_graph(self, min_lift: float = 1.5, max_nodes: int = 100) -> dict:
    """将关联规则转换为图谱数据 { nodes, edges }"""
    if self._rules_df.empty:
        if settings.ENABLE_MOCK_DATA:
            return degraded(_mock_graph_data(), "mock data")
        raise AppError(503, "关联规则数据暂未就绪")

    df = self._rules_df.copy()
    if "lift" in df.columns:
        df = df[df["lift"] >= min_lift]

    node_map = {}
    edges = []

    for _, row in df.iterrows():
        ants = row.get("antecedents", "").split(",")
        cons = row.get("consequents", "").split(",")
        for sku in ants + cons:
            sku = sku.strip()
            if sku and sku not in node_map:
                node_map[sku] = {
                    "id": sku,
                    "name": _sku_to_name(sku),
                    "frequency": 0,
                }
            if sku:
                node_map[sku]["frequency"] += 1

        for a in ants:
            for c in cons:
                a, c = a.strip(), c.strip()
                if a and c:
                    edges.append({
                        "source": a,
                        "target": c,
                        "lift": round(float(row.get("lift", 0)), 2),
                        "confidence": round(float(row.get("confidence", 0)), 3),
                        "support": round(float(row.get("support", 0)), 4),
                    })

    # 按 frequency 取 Top N 节点
    nodes = sorted(node_map.values(), key=lambda n: n["frequency"], reverse=True)[:max_nodes]
    node_ids = {n["id"] for n in nodes}
    edges = [e for e in edges if e["source"] in node_ids and e["target"] in node_ids]

    return ok({"nodes": nodes, "edges": edges})
```

### 4.3 新增 `/association/sku/{sku_code}/rules` 端点

```python
@router.get("/sku/{sku_code}/rules", summary="指定 SKU 参与的所有关联规则")
async def get_sku_rules(
    sku_code: str,
    top_n: int = Query(20, le=50),
    svc: AssociationService = Depends(_svc),
):
    return await svc.get_sku_rules(sku_code, top_n)
```

用于 Detail Tab 中展示选中 SKU 的全部关联规则（比全局 Top N 更精准）。

### 4.4 AssociationSkill 增强（小改）

当前 `AssociationSkill` 只返回 `association_graph` 类型 artifact。增加场景判断：

```python
# backend/copilot/skills/association_skill.py — execute() 中补充

# 如果用户问的是特定 SKU 的搭配推荐
if context.page_context.get("selected_node"):
    sku = context.page_context["selected_node"]
    # 调用 recommend 逻辑，返回推荐结果
    ...

# 如果用户问的是搭配营销策略（涉及跨 Skill）
# → CopilotEngine 的 LLM 路由会自动分发，此处无需改动
```

---

## 5. 文件清单

### 新建文件

| 文件 | 类型 | 说明 |
|------|------|------|
| `frontend/src/components/association/AssociationGraph.vue` | Component | Canvas 2D Force-Directed 关联网络图 |
| `frontend/src/components/association/LiftMiniBar.vue` | Component | 表格内 Lift 值 mini bar (纯 SVG) |
| `frontend/src/components/association/RuleDetailPanel.vue` | Component | 右侧规则/SKU 详情面板 |
| `frontend/src/components/association/SmartRecommend.vue` | Component | 上下文感知推荐卡片区 |
| `frontend/src/components/association/AssociationCommandBar.vue` | Component | 底部命令栏 |
| `frontend/src/components/association/KBSearchPanel.vue` | Component | 知识库搜索面板 (可复用库存页的同名组件模式) |

### 重写文件

| 文件 | 改动范围 | 说明 |
|------|---------|------|
| `frontend/src/views/business/AssociationAnalysis.vue` | **全量重写** | SplitInspector 布局 + 所有新组件集成 |

### 小改文件

| 文件 | 改动范围 | 说明 |
|------|---------|------|
| `frontend/src/api/business/association.js` | +2 方法 | 新增 `getGraph()` + `getSkuRules()` |
| `backend/routers/association.py` | +2 端点 | `GET /graph` + `GET /sku/{sku_code}/rules` |
| `backend/services/association_service.py` | +2 方法 | `get_graph()` + `get_sku_rules()` |
| `backend/copilot/skills/association_skill.py` | ~20 行 | 支持 `selected_node` 上下文 |

### 不需要改动的文件

| 文件 | 原因 |
|------|------|
| `frontend/src/composables/usePageCopilot.js` | 直接复用，不修改 |
| `frontend/src/composables/useCopilotStream.js` | usePageCopilot 封装它，不修改 |
| `backend/copilot/engine.py` | Engine 路由/Skill 执行已完备 |
| `backend/copilot/registry.py` | auto_discover 已注册 association_skill |
| `backend/copilot/events.py` | 16 种 event type 已覆盖 |
| `backend/copilot/persistence.py` | Thread 管理 + page_origin 过滤已由库存页重构完成 |
| `frontend/src/components/copilot/` 全部 | 只使用，不修改 |
| `frontend/src/components/v2/` 全部 | 只使用，不修改 |

### 依赖新增

| 包名 | 用途 | 大小 |
|------|------|------|
| `d3-force` | Force-Directed 布局算法 | ~15KB gzip |
| `d3-quadtree` | d3-force 的依赖 | ~5KB gzip |

> 注意：**不引入完整 d3**，仅用力导向布局子包。

---

## 6. 知识库兼容性设计

### 6.1 当前机制

```
用户提问 → CopilotEngine → 路由到 kb_rag skill → 检索向量库 → 返回 sources + text
```

### 6.2 前端适配

- KB Tab 内搜索调用 `usePageCopilot.askAgent('kb_rag', query)`
- 结果通过 SSE `sources` event 渲染为文档卡片列表
- 自动补充 `page_context.page = 'association'`，后端 kb_rag skill 可据此过滤 collection

### 6.3 典型知识库内容 (运营价值)

| 文档类型 | 示例 | 使用场景 |
|---------|------|---------|
| 交叉营销策略 | "高关联商品搭配促销方案模板" | 看到强关联规则后查询执行方案 |
| 陈列 SOP | "货架搭配陈列标准操作流程" | 据关联规则指导门店陈列 |
| 组合促销模板 | "满减/买赠组合促销设置指南" | 从关联结果直接落地促销 |
| 供应商捆绑协议 | "供应商 A 捆绑采购折扣条款" | 关联商品联合采购降本 |

### 6.4 后续扩展（零前端改动）

```
新增知识库 → 后端新建 collection / 导入文档 → kb_rag skill 自动检索到
→ 前端 sources 列表自动显示新来源
→ 无需任何前端代码变更
```

---

## 7. 数据流全景

```
┌──────────────────┐    ┌───────────────────┐    ┌───────────────────┐
│  用户操作          │    │  usePageCopilot   │    │  Backend          │
│                   │    │  (SSE Client)      │    │                   │
│ 1.页面加载        │───▶│ ask("关联规则概览") │───▶│ CopilotEngine     │
│ 2.点击图谱节点    │    │ setContext(node)   │    │   ↓               │
│ 3.点击规则表行    │    │ setContext(rule)   │    │ AssociationSkill  │
│ 4.输入问题        │    │ ask(question)      │    │ InventorySkill    │
│ 5.点击 suggest    │    │ handleSuggestion() │    │ ForecastSkill     │
│ 6.搜索 KB         │    │ askAgent('kb_rag') │    │ CustomerIntelSkill│
│ 7.拖拽/缩放图谱   │    │                    │    │ KBRagSkill        │
└──────────────────┘    └────────┬──────────┘    │ SentimentSkill    │
                                 │                └────────┬──────────┘
                        SSE Events (streaming)            │
                                 │                 ┌──────▼──────────┐
                        ┌────────▼──────────┐      │  Services       │
                        │  右侧 AI Tab       │      │  ・Association   │
                        │  ・text streaming   │      │  ・Inventory     │
                        │  ・artifacts        │◀─────│  ・Forecast      │
                        │  ・suggestions      │      │  ・KB RAG        │
                        │  ・sources          │      │  ・Customer      │
                        └────────┬──────────┘      └─────────────────┘
                                 │
                        ┌────────▼──────────┐
                        │  REST API          │
                        │  /association/     │
                        │   rules            │──▶ 规则表 + 图谱
                        │   graph            │──▶ 网络图数据
                        │   recommend/{sku}  │──▶ 推荐卡片
                        │   sku/{sku}/rules  │──▶ SKU 详情
                        └───────────────────┘

图谱节点选中 → setContext → AI 上下文更新 → 后续提问自动感知
规则表行选中 → setContext → Detail Tab 更新 + 推荐区联动
```

---

## 8. 设计规范

### 8.1 配色（遵循 Zinc 单色调）

| 元素 | 色值 | 说明 |
|------|------|------|
| 图谱节点填充 | `var(--v2-text-1)` / 频次映射透明度 | 频次越高越实 |
| 图谱节点描边 | `var(--v2-bg-card)` | 与背景分离 |
| 图谱边 (普通) | `var(--v2-text-4)` | 低调 |
| 图谱边 (强关联 Lift>3) | `var(--v2-text-2)` | 略深 |
| 选中高亮 | `var(--v2-brand-primary)` 2px 描边 | 极克制使用 |
| 前项 Tag | `var(--v2-brand-bg)` + `var(--v2-brand-primary)` | 沿用现有 |
| 后项 Tag | `var(--v2-success-bg)` + `var(--v2-success-text)` | 沿用现有 |
| LiftMiniBar | `var(--v2-text-4)` → `var(--v2-text-2)` 渐变映射 | 灰阶 |
| AI Tab 背景 | `var(--v2-ai-purple-bg)` | 与 InsightPanelV2 一致 |

### 8.2 字体

- 数值列 / KPI: `font-variant-numeric: tabular-nums`
- SKU 编号: `Geist Mono`
- 正文: `Geist Sans`
- 图谱节点标签: `Geist Sans, var(--v2-text-xs)`

### 8.3 动画

| 场景 | 实现 | 时长 |
|------|------|------|
| KPI 数字加载 | `Odometer.vue` easeOutQuart | 800ms |
| 右侧面板展开/折叠 | CSS transition `width` | 300ms |
| 图谱节点 hover | 半径 scale transition | 200ms |
| 图谱力导向模拟 | d3-force alphaDecay | ~2s 到稳定 |
| 图谱选中高亮 | 边/节点 opacity transition | `var(--v2-trans-fast)` |
| 表格行 hover → 图谱高亮 | requestAnimationFrame | 即时 |
| 推荐卡片出现 | opacity + translateY(8px) | 300ms stagger |
| AI 打字光标 | `cp__cursor` blink animation | 1s (已有) |

### 8.4 响应式

| 断点 | 布局 |
|------|------|
| ≥ 1400px | SplitInspector 2 栏 (main + right 320px) |
| 1100~1400px | SplitInspector 2 栏 (main + right 280px) |
| < 1100px | 单栏，右侧面板变为底部 Sheet / Drawer；图谱高度缩小为 240px |

---

## 9. 实施阶段

### Phase 1: 核心架构 + AI 联动（优先级最高）

**目标**: 页面能与 Agent 对话，AI 不再是假的；内嵌版与独立 Copilot 页通过 Thread 共享打通。

| 任务 | 文件 | 工作量 |
|------|------|--------|
| 重构 `AssociationAnalysis.vue` 为 SplitInspector 布局 | views/business/ | 1d |
| 接入 `usePageCopilot('association', ['association_skill', 'kb_rag'])` | 内嵌于主页面 | 0.3d |
| 右侧 AI Tab（嵌入 ChatPanel + CopilotArtifactRenderer） | 内嵌于主页面 | 0.5d |
| 页面加载自动 ask + 规则/节点选中上下文注入 | 内嵌于主页面 | 0.5d |
| Thread 共享："在 Copilot 中打开" + Thread 下拉选择器 | 内嵌于主页面 | 0.3d |

**验收标准**:
- [ ] 右侧 AI Tab 可输入问题并获得 streaming 回复
- [ ] AI 回复中嵌入 Artifact 可正常渲染
- [ ] Suggestions 可点击触发后续提问
- [ ] "在 Copilot 中打开" 跳转后独立页能加载并继续对话
- [ ] 返回关联分析页后 AI Tab 能恢复上次 thread

### Phase 2: 关联网络图谱（核心特色）

**目标**: 直观呈现商品关联拓扑，点击即探索。

| 任务 | 文件 | 工作量 |
|------|------|--------|
| 后端 `GET /association/graph` 端点 | backend/ | 0.5d |
| `AssociationGraph.vue` — Canvas 2D + d3-force | components/association/ | 2d |
| 图谱节点 click/hover → 右侧 Detail + 推荐联动 | 内嵌于主页面 | 0.5d |
| 图谱与规则表双向同步选中 | 内嵌于主页面 | 0.3d |
| 图谱与 AI 上下文联动 (setContext) | 内嵌于主页面 | 0.2d |

**验收标准**:
- [ ] 图谱正确渲染节点 + 边
- [ ] 节点大小反映频次，边粗细反映 Lift
- [ ] 节点 hover 显示 tooltip，click 高亮邻居
- [ ] 双击节点触发 AI 提问
- [ ] min_lift 筛选联动图谱更新
- [ ] 性能：100 节点满帧

### Phase 3: 表格增强 + 推荐区 + Detail Panel

**目标**: 对标 Linear/Datadog 表格交互品质。

| 任务 | 文件 | 工作量 |
|------|------|--------|
| `LiftMiniBar.vue` | components/association/ | 0.3d |
| Rules Table 增强（mini bars + 行交互） | 主页面内 | 0.5d |
| `RuleDetailPanel.vue` (右侧 Detail Tab) | components/association/ | 0.5d |
| `SmartRecommend.vue` (上下文感知推荐) | components/association/ | 0.5d |
| KPI 使用 Odometer + 点击过滤 | 主页面内 | 0.3d |

### Phase 4: 知识库 + Command Bar + 后端补充

**目标**: 完成知识库闭环 + 高级交互。

| 任务 | 文件 | 工作量 |
|------|------|--------|
| `KBSearchPanel.vue` | components/association/ | 0.5d |
| `AssociationCommandBar.vue` | components/association/ | 0.5d |
| ⌘K 快捷键绑定 | 主页面内 | 0.2d |
| 后端 `GET /association/sku/{sku}/rules` | backend/ | 0.3d |
| `AssociationSkill` 增强 (selected_node 上下文) | backend/copilot/skills/ | 0.3d |
| 飞书通知 Action 集成（"通知运营群设置促销"） | 主页面 + api | 0.3d |

---

## 10. 风险与缓解

| 风险 | 缓解策略 |
|------|---------|
| Copilot SSE 后端未启动 / LLM key 缺失 | AI Tab 降级为静态文本（复用当前 computed 逻辑作为 fallback） |
| KB collection 为空 | KB Tab 显示 "暂无知识库文档，请联系管理员上传" |
| CSV 数据不存在 | 已有 Mock 数据降级机制 (`_MOCK_RULES`)，图谱也对应生成 Mock 图 |
| 关联规则过多 (> 500 节点) | 图谱自动截取 Top 100 频次节点 + 提示 "显示部分高关联" |
| d3-force 在低端设备卡顿 | Canvas 2D 足够轻量；备选方案：预计算布局后静态渲染 |
| 右侧面板在小屏上挤压 | < 1100px 自动切为底部 Sheet |
| usePageCopilot 跨页面 context 泄漏 | composable 内部 onUnmounted 自动 stop + reset（已实现） |
| Thread 跳转后独立页找不到 thread | `loadThread` 已有 try-catch，fallback 为新对话 |

---

## 11. 后续可复用

本次新建的组件可为其他业务页面提供复用价值：

| 组件 | 可复用场景 |
|------|-----------|
| `AssociationGraph.vue` | 任何需要展示网络拓扑的场景（客户关系网络、供应链拓扑） |
| `LiftMiniBar.vue` | 任何表格中需要 mini bar 可视化数值的场景 |
| `SmartRecommend.vue` 模式 | 客户分析页的"相似客户推荐"、库存页的"替代品推荐" |
| `KBSearchPanel.vue` | 所有业务页的知识库入口（已设计为可复用模式） |

`usePageCopilot` 接入其他页面仍然只需 1 行代码：

```js
// 已在 INVENTORY_REDESIGN.md 中列出
const ai = usePageCopilot('association', ['association_skill', 'kb_rag'])
```

---

## 12. 验收 Checklist

- [ ] P1: 右侧 AI Tab streaming 对话正常
- [ ] P1: 页面加载自动生成 AI 关联洞察
- [ ] P1: Suggestions 可点击
- [ ] P1: Thread 共享 — "在 Copilot 中打开" 跳转后能继续对话
- [ ] P1: Thread 共享 — 返回关联分析页后 AI Tab 能恢复上次 thread
- [ ] P2: 关联网络图谱 Canvas 渲染正常
- [ ] P2: 图谱节点 hover/click/drag 交互正常
- [ ] P2: 图谱双击节点触发 AI 提问
- [ ] P2: 图谱与规则表双向选中同步
- [ ] P2: 图谱 min_lift 筛选联动
- [ ] P3: Rules Table LiftMiniBar 渲染
- [ ] P3: Detail Panel 规则/SKU 详情显示
- [ ] P3: SmartRecommend 上下文感知推荐
- [ ] P3: KPI Odometer 动画 + 点击过滤
- [ ] P4: KB Tab 搜索 + 文档渲染
- [ ] P4: Command Bar 输入 + @ mention
- [ ] P4: 飞书通知 Action
- [ ] 全局: 响应式 < 1100px 正常
- [ ] 全局: AI 后端不可用时优雅降级
- [ ] 全局: Zinc 单色调设计语言一致性
