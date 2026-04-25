<template>
  <div class="ar">
    <PageHeaderV2 title="关联分析" desc="购物篮规则 · 商品关联网络 · AI 搭配推荐">
      <template #actions>
        <label class="ar__lift-label">Min Lift</label>
        <input type="number" v-model.number="filterMinLift" class="ar__lift-input" min="0" step="0.1" />
        <button class="ar__action-btn" @click="refresh" title="刷新">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 2v6h-6M3 12a9 9 0 0115.36-6.36L21 8M3 22v-6h6M21 12a9 9 0 01-15.36 6.36L3 16"/></svg>
        </button>
        <button class="ar__toggle-panel" :class="{ 'ar__toggle-panel--active': showRight }" @click="showRight = !showRight" title="AI 面板">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="3"/><line x1="15" y1="3" x2="15" y2="21"/></svg>
        </button>
      </template>
    </PageHeaderV2>

    <SplitInspector :hide-right="!showRight">
      <!-- ═══ Main ═══ -->
      <template #main>
        <div class="ar__main">

          <!-- ① KPI Strip -->
          <div class="ar__kpis">
            <StatCardV2 label="规则总数" sub="关联规则" clickable @click="kpiFilter = ''">
              <template #value><Odometer :value="rules.length" /></template>
            </StatCardV2>
            <StatCardV2 label="最高 Lift" sub="关联强度" clickable @click="kpiFilter = ''">
              <template #value><Odometer :value="topLiftNum" :decimals="2" /></template>
            </StatCardV2>
            <StatCardV2 label="最高 Conf" sub="置信度" clickable @click="kpiFilter = ''">
              <template #value><Odometer :value="topConfNum" :decimals="3" /></template>
            </StatCardV2>
            <StatCardV2 label="强关联对" sub="Lift > 3" clickable @click="kpiFilter = kpiFilter === 'strong' ? '' : 'strong'">
              <template #value><Odometer :value="strongPairCount" /></template>
            </StatCardV2>
          </div>

          <!-- ② Association Network Graph -->
          <SectionCardV2 title="关联热力图" subtitle="商品关联强度矩阵 · Lift 越高关联越强" class="ar__graph-section">
            <template #header>
              <AIInlineLabel v-if="graphDegraded" text="降级" size="xs" />
            </template>
            <SkeletonBlockV2 v-if="graphLoading" :rows="4" />
            <AssociationGraph
              v-else
              :nodes="graphNodes"
              :edges="graphEdges"
              :selected-id="selectedNodeId"
              @node-click="onNodeClick"
              @node-dblclick="onNodeDblClick"
            />
          </SectionCardV2>

          <!-- ③ Rules Table -->
          <SectionCardV2 title="关联规则 Top N" :flush="true" class="ar__rules-section">
            <template #header><AIInlineLabel v-if="rulesDegraded" text="降级" size="xs" /></template>
            <SkeletonBlockV2 v-if="rulesLoading" :rows="6" />
            <ErrorStateV2 v-else-if="rulesError" :desc="rulesError" @retry="loadRules" />
            <div v-else-if="displayRules.length" class="ar__table-wrap">
              <table class="ar__table">
                <thead>
                  <tr>
                    <th class="ar__th-idx">#</th>
                    <th>前项</th>
                    <th class="ar__th-arrow">→</th>
                    <th>后项</th>
                    <th class="ar__th-r">Sup</th>
                    <th class="ar__th-r">Conf</th>
                    <th class="ar__th-r">Lift</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(row, idx) in displayRules"
                    :key="idx"
                    class="ar__row"
                    :class="{ 'ar__row--selected': selectedRule === row }"
                    @click="onRuleClick(row)"
                  >
                    <td class="ar__td-idx">{{ idx + 1 }}</td>
                    <td><div class="ar__items"><span v-for="(a, i) in toArr(row.antecedent_names || row.antecedents)" :key="i" class="ar__tag" :title="toArr(row.antecedents)[i]">{{ a }}</span></div></td>
                    <td class="ar__td-arrow">→</td>
                    <td><div class="ar__items"><span v-for="(c, i) in toArr(row.consequent_names || row.consequents)" :key="i" class="ar__tag ar__tag--cons" :title="toArr(row.consequents)[i]">{{ c }}</span></div></td>
                    <td class="ar__td-num">{{ row.support?.toFixed(4) }}</td>
                    <td class="ar__td-num">{{ row.confidence?.toFixed(3) }}</td>
                    <td class="ar__td-num">
                      <div class="ar__lift-cell">
                        <LiftMiniBar :value="row.lift" :max="maxLift" />
                        <span :class="liftClass(row.lift)">{{ row.lift?.toFixed(2) }}</span>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <EmptyStateV2 v-else title="暂无关联规则" />
          </SectionCardV2>

          <!-- ④ Smart Recommend -->
          <SmartRecommend
            :base-sku="selectedNodeId"
            :items="recItems"
            :loading="recLoading"
            :error="recError"
            @ask-ai="onAskAI"
            @ask-agent="onAskAgent"
            @retry="loadRecommend"
          />
        </div>
      </template>

      <!-- ═══ Right Panel ═══ -->
      <template #right>
        <PageAICopilotPanel
          ref="aiPanelRef"
          :ai="ai"
          welcome-title="AI 关联分析助手"
          welcome-desc="商品关联规则、搭配推荐、交叉营销策略"
          collection="association"
          command-bar-placeholder="询问关联分析问题...  @ 选择智能体"
          :quick-questions="quickQuestions"
          :mention-catalog="mentionCatalog"
        >
          <template #detail>
            <RuleDetailPanel
              :rule="selectedRule"
              :node="selectedNode"
              :sku-rules="skuRulesList"
              @ask-ai="onAskAI"
              @ask-agent="onAskAgent"
              @select-rule="onRuleClick"
            />
          </template>
        </PageAICopilotPanel>
      </template>
    </SplitInspector>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { associationApi } from '@/api/business'
import { usePageCopilot } from '@/composables/usePageCopilot'
import { PageHeaderV2, StatCardV2, SectionCardV2, EmptyStateV2, ErrorStateV2, SkeletonBlockV2, AIInlineLabel, SplitInspector, Odometer, PageAICopilotPanel } from '@/components/v2'
import {
  AssociationGraph, LiftMiniBar, RuleDetailPanel,
  SmartRecommend,
} from '@/components/association'

// ── AI Copilot ──
const ai = usePageCopilot('association', ['association_skill', 'kb_rag'])
const aiPanelRef = ref(null)

const quickQuestions = [
  '当前商品关联规则概览',
  '哪些商品最适合做搭配促销？',
  '交叉营销策略建议',
]

const mentionCatalog = [
  { id: 'association_skill', label: '关联分析', type: 'skill', icon: '🔗' },
  { id: 'customer_intel', label: '客群洞察', type: 'skill', icon: '👥' },
  { id: 'kb_rag', label: '知识库', type: 'collection', icon: '📚' },
]

// ── UI state ──
const showRight = ref(true)
const filterMinLift = ref(1.5)
const kpiFilter = ref('')

// ── toArr helper ──
const toArr = (v) => {
  if (Array.isArray(v)) return v
  if (typeof v === 'string') {
    if (v.startsWith('frozenset')) { const m = v.match(/\{(.+?)\}/); return m ? m[1].split(',').map(s => s.trim().replace(/'/g, '')) : [v] }
    return v.split(/[,+]/).map(s => s.trim()).filter(Boolean)
  }
  return v ? [String(v)] : []
}

// ── Rules data ──
const rulesLoading = ref(false)
const rulesError = ref('')
const rulesDegraded = ref(false)
const rules = ref([])

async function loadRules() {
  rulesLoading.value = true; rulesError.value = ''
  try {
    const d = await associationApi.getRules({ top_n: 50, min_lift: filterMinLift.value })
    rules.value = Array.isArray(d) ? d : (d?.data ?? [])
    rulesDegraded.value = !!d?._meta?.degraded
  } catch (e) {
    rulesError.value = e?.response?.data?.message || '加载规则失败'
  } finally {
    rulesLoading.value = false
  }
}

// ── Graph data ──
const graphLoading = ref(false)
const graphDegraded = ref(false)
const graphNodes = ref([])
const graphEdges = ref([])

async function loadGraph() {
  graphLoading.value = true
  try {
    const d = await associationApi.getGraph({ min_lift: filterMinLift.value, max_nodes: 100 })
    const data = d?.data ?? d ?? {}
    graphNodes.value = data.nodes || []
    graphEdges.value = data.edges || []
    graphDegraded.value = !!d?._meta?.degraded
  } catch {
    graphNodes.value = []; graphEdges.value = []
  } finally {
    graphLoading.value = false
  }
}

// ── Recommend data ──
const recLoading = ref(false)
const recError = ref('')
const recItems = ref([])

async function loadRecommend() {
  if (!selectedNodeId.value) { recItems.value = []; return }
  recLoading.value = true; recError.value = ''
  try {
    const d = await associationApi.getRecommend(selectedNodeId.value, { top_n: 5 })
    recItems.value = Array.isArray(d) ? d : (d?.data ?? [])
  } catch (e) {
    recError.value = e?.response?.data?.message || '推荐加载失败'
  } finally {
    recLoading.value = false
  }
}

// ── SKU rules for detail panel ──
const skuRulesList = ref([])
async function loadSkuRules(skuCode) {
  try {
    const d = await associationApi.getSkuRules(skuCode, { top_n: 20 })
    skuRulesList.value = Array.isArray(d) ? d : (d?.data ?? [])
  } catch { skuRulesList.value = [] }
}

// ── Computed ──
const topLiftNum = computed(() => rules.value.length ? Math.max(...rules.value.map(r => r.lift ?? 0)) : 0)
const topConfNum = computed(() => rules.value.length ? Math.max(...rules.value.map(r => r.confidence ?? 0)) : 0)
const strongPairCount = computed(() => rules.value.filter(r => r.lift > 3).length)
const maxLift = computed(() => topLiftNum.value || 6)

const displayRules = computed(() => {
  if (kpiFilter.value === 'strong') return rules.value.filter(r => r.lift > 3)
  return rules.value
})

function liftClass(lift) {
  if (lift > 3) return 'ar__lift--strong'
  if (lift > 1.5) return 'ar__lift--mid'
  return 'ar__lift--weak'
}

// ── Selection state ──
const selectedRule = ref(null)
const selectedNode = ref(null)
const selectedNodeId = computed(() => selectedNode.value?.id || '')

function onRuleClick(rule) {
  selectedRule.value = rule
  selectedNode.value = null
  showRight.value = true
  aiPanelRef.value?.switchTab('detail')
  ai.setContext({
    selected_rule: {
      antecedents: rule.antecedents,
      consequents: rule.consequents,
      lift: rule.lift,
      confidence: rule.confidence,
    },
    selected_node: null,
  })
}

function onNodeClick(node) {
  selectedNode.value = node
  selectedRule.value = null
  showRight.value = true
  aiPanelRef.value?.switchTab('detail')
  ai.setContext({
    selected_node: node.id,
    selected_node_name: node.name,
    node_frequency: node.frequency,
    selected_rule: null,
  })
  loadRecommend()
  loadSkuRules(node.id)
}

function onNodeDblClick(node) {
  onAskAI(`分析 ${node.name || node.id} 的关联商品和搭配推荐`)
}

function onAskAI(question) {
  showRight.value = true
  aiPanelRef.value?.askAndSwitch(question)
}

function onAskAgent(skillId, question) {
  showRight.value = true
  ai.askAgent(skillId, question)
}

// ── Refresh all ──
function refresh() {
  loadRules()
  loadGraph()
}

// ── Watch filter → reload ──
watch(filterMinLift, () => refresh())

// ── Init ──
onMounted(async () => {
  refresh()
  await ai.init()
  // [TEMP] 暂停自动 AI 问答，后续测试完毕再打开
  // if (!ai.messages.value.length) {
  //   ai.ask('当前商品关联规则概览和强关联商品对')
  // }
})
</script>

<style scoped>
.ar { display: flex; flex-direction: column; gap: var(--v2-space-3); height: 100%; }

/* ── KPI ── */
.ar__kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--v2-space-3); }

/* ── Graph ── */
.ar__graph-section { margin-bottom: 0; }

/* ── Rules table ── */
.ar__rules-section { margin-bottom: 0; }
.ar__items { display: flex; flex-wrap: wrap; gap: 3px; }
.ar__tag { font-size: var(--v2-text-xs); padding: 1px 8px; background: var(--v2-brand-bg); color: var(--v2-brand-primary); border-radius: var(--v2-radius-sm); font-weight: 500; white-space: nowrap; }
.ar__tag--cons { background: var(--v2-success-bg); color: var(--v2-success-text); }

.ar__table-wrap { overflow: auto; max-height: 400px; }
.ar__table { width: 100%; border-collapse: collapse; font-size: var(--v2-text-sm); }
.ar__table th { position: sticky; top: 0; z-index: 1; background: var(--v2-bg-sunken); padding: 7px 10px; font-size: 10px; font-weight: 600; color: var(--v2-text-3); text-transform: uppercase; letter-spacing: .3px; text-align: left; border-bottom: 1px solid var(--v2-border-2); white-space: nowrap; }
.ar__th-idx { width: 32px; }
.ar__th-arrow { width: 24px; text-align: center !important; color: var(--v2-text-4); }
.ar__th-r { text-align: right !important; }
.ar__table td { padding: 6px 10px; border-bottom: 1px solid var(--v2-border-2); vertical-align: middle; }
.ar__row { cursor: pointer; transition: background var(--v2-trans-fast); }
.ar__row:hover { background: rgba(0,0,0,0.02); }
.ar__row--selected { background: rgba(0,0,0,0.04) !important; }
.ar__td-idx { font-size: 10px; color: var(--v2-text-4); font-variant-numeric: tabular-nums; }
.ar__td-arrow { text-align: center; color: var(--v2-text-4); font-size: var(--v2-text-xs); }
.ar__td-num { text-align: right; font-variant-numeric: tabular-nums; font-size: var(--v2-text-xs); color: var(--v2-text-1); }

.ar__lift-cell { display: flex; align-items: center; gap: 6px; justify-content: flex-end; }
.ar__lift--strong { color: var(--v2-text-1); font-weight: 700; }
.ar__lift--mid { color: var(--v2-text-2); font-weight: 600; }
.ar__lift--weak { color: var(--v2-text-3); }


/* ── Header controls ── */
.ar__lift-label { font-size: var(--v2-text-xs); color: var(--v2-text-3); white-space: nowrap; }
.ar__lift-input { width: 64px; padding: 4px 8px; border: 1px solid var(--v2-border-1); border-radius: var(--v2-radius-md); font-size: var(--v2-text-xs); text-align: center; background: var(--v2-bg-card); color: var(--v2-text-1); outline: none; font-family: 'Geist Mono', monospace; transition: border-color var(--v2-trans-fast); }
.ar__lift-input:focus { border-color: var(--v2-text-1); }
.ar__action-btn { display: flex; align-items: center; justify-content: center; width: 28px; height: 28px; border: 1px solid var(--v2-border-1); border-radius: var(--v2-radius-md); background: var(--v2-bg-card); color: var(--v2-text-3); cursor: pointer; transition: all var(--v2-trans-fast); }
.ar__action-btn:hover { color: var(--v2-text-1); background: var(--v2-bg-sunken); }

/* ── Toggle button ── */
.ar__toggle-panel { display: flex; align-items: center; justify-content: center; width: 28px; height: 28px; border: 1px solid var(--v2-border-1); border-radius: var(--v2-radius-md); background: var(--v2-bg-card); color: var(--v2-text-3); cursor: pointer; transition: all var(--v2-trans-fast); }
.ar__toggle-panel:hover { color: var(--v2-text-1); }
.ar__toggle-panel--active { background: var(--v2-text-1); color: #fff; border-color: var(--v2-text-1); }

/* ── Main content scroll ── */
.ar__main { display: flex; flex-direction: column; gap: var(--v2-space-4); padding: var(--v2-space-3); overflow-y: auto; }


/* ── Responsive ── */
@media (max-width: 1100px) {
  .ar__kpis { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 600px) {
  .ar__kpis { grid-template-columns: 1fr; }
}
</style>
