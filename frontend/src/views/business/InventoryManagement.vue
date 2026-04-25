<template>
  <div class="iv">
    <PageHeaderV2 title="库存管理" desc="补货预警 · ABC-XYZ 矩阵 · AI 辅助决策">
      <template #actions>
        <button class="iv__panel-toggle" @click="rightPanelOpen = !rightPanelOpen">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M15 3v18"/></svg>
          {{ rightPanelOpen ? '收起面板' : '展开面板' }}
        </button>
      </template>
    </PageHeaderV2>

    <SplitInspector :hide-right="!rightPanelOpen">
      <!-- ═══════ MAIN PANEL ═══════ -->
      <template #main>
        <!-- C-α: 从 Dashboard 跳转带入的 intent 提示 -->
        <DegradedBannerV2
          v-if="fromDashboardNotice"
          level="info"
          :title="fromDashboardNotice.title"
          :desc="fromDashboardNotice.desc"
          :closable="true"
          @close="fromDashboardNotice = null"
        />
        <!-- ① KPI Row -->
        <div class="iv__kpis">
          <StatCardV2
            class="iv__kpi-hero"
            label="健康度"
            :value="status.overall_health_pct != null ? status.overall_health_pct.toFixed(0)+'%' : '--'"
            trend-dir="up"
            sub="库存整体健康"
            @click="kpiFilter = kpiFilter === 'health' ? '' : 'health'"
          />
          <StatCardV2 label="SKU 总数" :value="status.total_skus ?? '--'" sub="在管商品" />
          <StatCardV2
            label="预警"
            :value="status.warning_count ?? '--'"
            trend-dir="down"
            sub="需关注"
            @click="setAlertFilter('warning')"
          />
          <StatCardV2
            label="紧急"
            :value="status.critical_count ?? '--'"
            trend-dir="down"
            sub="需立即补货"
            @click="setAlertFilter('critical')"
          />
          <StatCardV2 label="周转天数" :value="status.avg_turnover_days ?? '--'" sub="平均周转" />
        </div>

        <!-- ② Alert Table + Heatmap -->
        <div class="iv__body">
          <SectionCardV2 title="补货预警清单" :flush="true" class="iv__alerts-card" data-section="alerts">
            <template #header>
              <div class="iv__alert-filters">
                <button
                  v-for="f in alertFilters"
                  :key="f.value"
                  class="iv__filter-btn"
                  :class="{ 'iv__filter-btn--active': alertLevel === f.value }"
                  @click="alertLevel = f.value; loadAlerts()"
                >{{ f.label }}</button>
              </div>
            </template>
            <SkeletonBlockV2 v-if="alertsLoading" :rows="6" />
            <ErrorStateV2 v-else-if="alertsError" :desc="alertsError" @retry="loadAlerts" />
            <div v-else-if="filteredAlerts.length" class="iv__table-wrap">
              <table class="iv__table">
                <thead>
                  <tr>
                    <th>SKU</th>
                    <th>名称</th>
                    <th class="iv__th-r">当前</th>
                    <th class="iv__th-r">安全</th>
                    <th class="iv__th-r">补货</th>
                    <th>级别</th>
                    <th>趋势</th>
                    <th class="iv__th-r">天数</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="row in filteredAlerts"
                    :key="row.sku_code"
                    class="iv__row"
                    :class="{ 'iv__row--selected': selectedSku?.sku_code === row.sku_code }"
                    @click="selectRow(row)"
                  >
                    <td class="iv__td-code">{{ row.sku_code }}</td>
                    <td class="iv__td-name">{{ row.sku_name || '-' }}</td>
                    <td class="iv__td-num" :class="{ 'iv__td-danger': row.current_stock < row.safety_stock }">{{ row.current_stock }}</td>
                    <td class="iv__td-num">{{ row.safety_stock }}</td>
                    <td class="iv__td-num iv__td-primary">{{ row.reorder_qty ?? '-' }}</td>
                    <td>
                      <span class="iv__badge" :class="`iv__badge--${row.alert_level}`">{{ row.alert_level }}</span>
                    </td>
                    <td>
                      <StockSparkline
                        v-if="row.stock_history_7d?.length"
                        :data="row.stock_history_7d"
                        :color="row.alert_level === 'critical' ? '#ef4444' : row.alert_level === 'warning' ? '#f59e0b' : '#18181b'"
                      />
                    </td>
                    <td class="iv__td-num">{{ row.urgency_days ?? '-' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <EmptyStateV2 v-else title="暂无预警" />
          </SectionCardV2>

          <div class="iv__side-col">
            <!-- Heatmap -->
            <SectionCardV2 title="ABC-XYZ 矩阵" subtitle="点击格子过滤">
              <SkeletonBlockV2 v-if="matrixLoading" :rows="3" :cols="3" />
              <ErrorStateV2 v-else-if="matrixError" :desc="matrixError" @retry="loadMatrix" />
              <InventoryHeatmap
                v-else-if="matrixData.length"
                :data="matrixData"
                :active-cell="activeCell"
                @cell-click="toggleCell"
              />
              <EmptyStateV2 v-else title="暂无矩阵数据" />
            </SectionCardV2>

            <!-- Strategy -->
            <SectionCardV2 title="补货策略" subtitle="当前选中">
              <div v-if="activeCell" class="iv__strategy">
                <div class="iv__strat-cell">{{ activeCell }}</div>
                <p class="iv__strat-text">{{ activeCellStrategy }}</p>
              </div>
              <div v-else class="iv__strat-hint">点击矩阵格子查看对应策略建议</div>
            </SectionCardV2>
          </div>
        </div>

        <!-- ③ Trend Chart -->
        <SectionCardV2 title="库存健康趋势" subtitle="30天" class="iv__trend-section">
          <InventoryTrendChart :data="trendData" :height="180" />
        </SectionCardV2>
      </template>

      <!-- ═══════ RIGHT PANEL ═══════ -->
      <template #right>
        <div class="iv__right">
          <!-- Tab Bar -->
          <div class="iv__tabs">
            <button
              v-for="tab in tabs"
              :key="tab.id"
              class="iv__tab"
              :class="{ 'iv__tab--active': activeTab === tab.id }"
              @click="activeTab = tab.id"
            >
              <span v-html="tab.icon"></span>
              {{ tab.label }}
            </button>
          </div>

          <!-- Tab: AI Copilot -->
          <div class="iv__tab-content" v-show="activeTab === 'ai'">
            <!-- Thread Selector -->
            <div class="iv__thread-bar" v-if="ai.threadHistory.value.length > 0">
              <select
                class="iv__thread-select"
                :value="ai.currentThreadId.value"
                @change="onThreadChange($event.target.value)"
              >
                <option value="">新对话</option>
                <option
                  v-for="t in ai.threadHistory.value"
                  :key="t.id"
                  :value="t.id"
                >{{ t.title || t.id.slice(0, 8) + '...' }}</option>
              </select>
              <button class="iv__thread-open" @click="ai.openInFullCopilot(router)" title="在 Copilot 中打开">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3"/></svg>
              </button>
            </div>

            <!-- Messages -->
            <div class="iv__messages" ref="messagesRef">
              <!-- Welcome -->
              <div class="iv__ai-welcome" v-if="!ai.messages.value.length && !ai.streaming.value">
                <p>AI 库存助手</p>
                <div class="iv__ai-chips">
                  <button v-for="q in quickQuestions" :key="q" class="iv__ai-chip" @click="ai.ask(q)">{{ q }}</button>
                </div>
              </div>

              <!-- Message list -->
              <template v-for="(msg, i) in ai.messages.value" :key="i">
                <div v-if="msg.role === 'user'" class="iv__msg iv__msg--user">
                  <div class="iv__msg-bubble">{{ msg.content }}</div>
                </div>
                <div v-else class="iv__msg iv__msg--assistant">
                  <div class="iv__msg-skill" v-if="msg.skill">
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/></svg>
                    {{ msg.skill }}
                  </div>
                  <CopilotArtifactRenderer
                    v-for="(art, ai2) in msg.artifacts"
                    :key="ai2"
                    :artifact="art"
                  />
                  <CopilotMarkdownRenderer
                    v-if="msg.content"
                    :text="msg.content"
                    :streaming="false"
                  />
                  <CopilotSuggestions
                    v-if="msg.suggestions?.length"
                    :items="msg.suggestions"
                    @select="ai.handleSuggestion"
                  />
                  <!-- Sources -->
                  <div class="iv__msg-sources" v-if="msg.sources?.length">
                    <button class="iv__sources-btn" @click="msg._showSources = !msg._showSources">
                      {{ msg._showSources ? '隐藏' : '查看' }}来源 ({{ msg.sources.length }})
                    </button>
                    <div v-if="msg._showSources" class="iv__sources-list">
                      <span v-for="(s, si) in msg.sources" :key="si" class="iv__source-chip">
                        {{ s.title || s.name || 'Source ' + (si+1) }}
                        <span v-if="s.score" class="iv__source-score">{{ (s.score*100).toFixed(0) }}%</span>
                      </span>
                    </div>
                  </div>
                  <!-- Feedback -->
                  <div class="iv__msg-fb" v-if="msg.content">
                    <button :class="['iv__fb-btn', { 'iv__fb-btn--on': msg.feedback === 1 }]" @click="ai.setFeedback(msg, 1)">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 9V5a3 3 0 00-3-3l-4 9v11h11.28a2 2 0 002-1.7l1.38-9a2 2 0 00-2-2.3H14z"/></svg>
                    </button>
                    <button :class="['iv__fb-btn', { 'iv__fb-btn--on': msg.feedback === -1 }]" @click="ai.setFeedback(msg, -1)">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M10 15V19a3 3 0 003 3l4-9V2H5.72a2 2 0 00-2 1.7l-1.38 9a2 2 0 002 2.3H10z"/></svg>
                    </button>
                  </div>
                </div>
              </template>

              <!-- Live streaming -->
              <div class="iv__msg iv__msg--assistant" v-if="ai.streaming.value">
                <div class="iv__msg-skill" v-if="ai.activeSkill.value?.name">
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/></svg>
                  {{ ai.activeSkill.value.displayName || ai.activeSkill.value.name }}
                  <span class="iv__skill-dot" v-if="ai.activeSkill.value.loading"></span>
                </div>
                <CopilotArtifactRenderer
                  v-for="(art, ai3) in ai.artifacts.value"
                  :key="ai3"
                  :artifact="art"
                />
                <CopilotMarkdownRenderer
                  v-if="ai.text.value"
                  :text="ai.text.value"
                  :streaming="true"
                />
              </div>

              <!-- Error -->
              <div class="iv__ai-error" v-if="ai.error.value">{{ ai.error.value }}</div>
            </div>

            <!-- Composer -->
            <InventoryCommandBar @send="onCommandSend" />
          </div>

          <!-- Tab: Detail -->
          <div class="iv__tab-content" v-show="activeTab === 'detail'">
            <SkuDetailPanel
              :sku="selectedSkuWithMatrix"
              @ask-ai="onAskAiFromDetail"
            />
          </div>

          <!-- Tab: Knowledge Base -->
          <div class="iv__tab-content" v-show="activeTab === 'kb'">
            <KBSearchPanel @doc-click="onKbDocClick" />
          </div>
        </div>
      </template>
    </SplitInspector>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { inventoryApi } from '@/api/business'
import { usePageCopilot } from '@/composables/usePageCopilot'
import { useIntentStore } from '@/stores/useIntentStore'
import {
  PageHeaderV2, StatCardV2, SectionCardV2, EmptyStateV2,
  ErrorStateV2, SkeletonBlockV2, SplitInspector, DegradedBannerV2,
} from '@/components/v2'
import CopilotArtifactRenderer from '@/components/copilot/CopilotArtifactRenderer.vue'
import CopilotMarkdownRenderer from '@/components/copilot/CopilotMarkdownRenderer.vue'
import CopilotSuggestions from '@/components/copilot/CopilotSuggestions.vue'
import {
  StockSparkline, InventoryHeatmap, SkuDetailPanel,
  KBSearchPanel, InventoryCommandBar, InventoryTrendChart,
} from '@/components/inventory'

const router = useRouter()

// ── AI Copilot ──
const ai = usePageCopilot('inventory', ['inventory_skill', 'kb_rag'])
const messagesRef = ref(null)

// ── UI State ──
const rightPanelOpen = ref(true)
const activeTab = ref('ai')
const kpiFilter = ref('')
const selectedSku = ref(null)

const tabs = [
  { id: 'ai', label: 'AI', icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>' },
  { id: 'detail', label: '详情', icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/></svg>' },
  { id: 'kb', label: '知识库', icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/></svg>' },
]

const quickQuestions = [
  '当前库存健康概览',
  '哪些SKU需要紧急补货？',
  '库存周转率分析',
]

// ── Data ──
const status = ref({})
const alertLevel = ref('all')
const alertsLoading = ref(false)
const alertsError = ref('')
const alerts = ref([])
const activeCell = ref('')
const matrixLoading = ref(false)
const matrixError = ref('')
const matrixData = ref([])
const trendData = ref([])

const alertFilters = [
  { value: 'all', label: '全部' },
  { value: 'critical', label: '紧急' },
  { value: 'warning', label: '预警' },
]

// ── Computed ──
const filteredAlerts = computed(() => {
  let data = alerts.value
  if (activeCell.value) {
    data = data.filter(a => {
      const m = matrixData.value.find(m2 => m2.sku_code === a.sku_code)
      return m?.matrix_cell === activeCell.value
    })
  }
  return data
})

const activeCellStrategy = computed(() => {
  const item = matrixData.value.find(i => i.matrix_cell === activeCell.value)
  return item?.strategy || '-'
})

const selectedSkuWithMatrix = computed(() => {
  if (!selectedSku.value) return null
  const mx = matrixData.value.find(m => m.sku_code === selectedSku.value.sku_code)
  return { ...selectedSku.value, ...(mx || {}) }
})

// ── Data Loading ──
async function loadStatus() {
  try {
    const d = await inventoryApi.getStatus()
    status.value = d ?? {}
  } catch { /* silent */ }
}

async function loadAlerts() {
  alertsLoading.value = true
  alertsError.value = ''
  try {
    const d = await inventoryApi.getAlerts({ level: alertLevel.value })
    alerts.value = Array.isArray(d) ? d : (d?.data ?? [])
  } catch (e) {
    alertsError.value = e?.response?.data?.message || '加载预警失败'
  } finally {
    alertsLoading.value = false
  }
}

async function loadMatrix() {
  matrixLoading.value = true
  matrixError.value = ''
  try {
    const d = await inventoryApi.getAbcXyz()
    matrixData.value = Array.isArray(d?.matrix) ? d.matrix : (Array.isArray(d) ? d : [])
  } catch (e) {
    matrixError.value = e?.response?.data?.message || '加载矩阵失败'
  } finally {
    matrixLoading.value = false
  }
}

async function loadTrend() {
  try {
    const d = await inventoryApi.getTrend({ days: 30 })
    trendData.value = Array.isArray(d) ? d : (d?.data ?? [])
  } catch { /* silent */ }
}

// ── Interactions ──
function toggleCell(key) {
  activeCell.value = activeCell.value === key ? '' : key
}

function setAlertFilter(level) {
  alertLevel.value = alertLevel.value === level ? 'all' : level
  loadAlerts()
}

function selectRow(row) {
  selectedSku.value = row
  // Auto-switch to detail tab & inject AI context
  activeTab.value = 'detail'
  ai.setContext({
    selected_sku: row.sku_code,
    sku_name: row.sku_name,
    current_stock: row.current_stock,
    safety_stock: row.safety_stock,
    alert_level: row.alert_level,
  })
}

function onCommandSend({ question, mentions }) {
  ai.ask(question, mentions)
  scrollMessages()
}

function onAskAiFromDetail(question) {
  activeTab.value = 'ai'
  ai.ask(question)
  scrollMessages()
}

function onKbDocClick(doc) {
  // When a KB doc is clicked, ask AI about it
  activeTab.value = 'ai'
  ai.ask(`关于「${doc.title}」，请总结关键内容`, [{ type: 'collection', id: 'kb_rag' }])
}

function onThreadChange(threadId) {
  if (threadId) {
    ai.switchThread(threadId)
  } else {
    ai.startNewThread()
  }
}

function scrollMessages() {
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

// Auto-scroll on streaming
watch(() => ai.text.value, scrollMessages)
watch(() => ai.artifacts.value, scrollMessages, { deep: true })

// ── C-α: Intent Store ──
const intentStore = useIntentStore()
const fromDashboardNotice = ref(null)

function scrollToAlerts() {
  const el = document.querySelector('[data-section="alerts"]')
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    el.classList.add('iv__highlight')
    setTimeout(() => el.classList.remove('iv__highlight'), 1600)
  }
}

// ── Init ──
onMounted(async () => {
  // ── C-α: 先消费 intent 决定预警筛选级别 ──
  const intent = intentStore.consume('replenish_sku')
  if (intent) {
    const sev = intent.payload.severity
    if (sev === 'critical' || sev === 'warning') {
      alertLevel.value = sev
    }
    fromDashboardNotice.value = {
      title: '从经营总览跳转',
      desc: `已按"${sev === 'critical' ? '紧急' : '预警'}"级别筛选${intent.payload.count ? `（${intent.payload.count} 个 SKU）` : ''}，下方自动聚焦补货清单。`,
    }
  }

  loadStatus()
  loadAlerts()
  loadMatrix()
  loadTrend()

  // Init AI — restore last thread or start fresh
  await ai.init()

  if (intent) {
    nextTick(() => setTimeout(scrollToAlerts, 400))
  }
})
</script>

<style scoped>
/* ── Layout ── */
.iv { height: calc(100vh - 64px); display: flex; flex-direction: column; overflow: hidden; }

/* C-α: 被 intent 目标定位的区域临时高亮 */
.iv__highlight { box-shadow: 0 0 0 3px color-mix(in srgb, var(--v2-error, #dc2626) 35%, transparent); transition: box-shadow 0.3s; border-radius: var(--v2-radius-lg); }
.iv :deep(.si__panel--main) { overflow-y: auto; padding: 16px; }
.iv :deep(.si__panel--right) { overflow: hidden; }

.iv__panel-toggle {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 12px; border: 1px solid rgba(0,0,0,0.08); border-radius: 8px;
  background: #fff; font-size: 12px; font-weight: 500; color: #71717a;
  cursor: pointer; transition: all 0.15s; font-family: inherit;
}
.iv__panel-toggle:hover { background: #f4f4f5; color: #18181b; border-color: rgba(0,0,0,0.15); }

/* ── KPI Row ── */
.iv__kpis {
  display: grid;
  grid-template-columns: 1.3fr 1fr 1fr 1fr 1fr;
  gap: 12px;
  margin-bottom: 16px;
  flex-shrink: 0;
}
.iv__kpi-hero { border-left: 3px solid #22c55e; }

/* ── Body: Table + Side ── */
.iv__body {
  display: grid;
  grid-template-columns: 1fr 280px;
  gap: 12px;
  margin-bottom: 12px;
  min-height: 0;
  flex: 1;
}
.iv__side-col { display: flex; flex-direction: column; gap: 12px; }

/* ── Custom Table ── */
.iv__table-wrap { overflow: auto; max-height: 440px; }
.iv__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.iv__table th {
  position: sticky;
  top: 0;
  background: #fafafa;
  padding: 8px 10px;
  font-size: 11px;
  font-weight: 600;
  color: #71717a;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  text-align: left;
  border-bottom: 1px solid rgba(0,0,0,0.06);
  white-space: nowrap;
  z-index: 1;
}
.iv__th-r { text-align: right !important; }
.iv__table td {
  padding: 7px 10px;
  border-bottom: 1px solid rgba(0,0,0,0.03);
  vertical-align: middle;
  white-space: nowrap;
}
.iv__row { cursor: pointer; transition: background 0.1s; }
.iv__row:hover { background: rgba(0,0,0,0.02); }
.iv__row--selected { background: rgba(24,24,27,0.04) !important; }
.iv__td-code { font-weight: 600; font-variant-numeric: tabular-nums; color: #18181b; }
.iv__td-name { color: #52525b; max-width: 140px; overflow: hidden; text-overflow: ellipsis; }
.iv__td-num { text-align: right; font-variant-numeric: tabular-nums; color: #18181b; }
.iv__td-danger { color: #dc2626 !important; font-weight: 600; }
.iv__td-primary { font-weight: 700; }

.iv__badge {
  display: inline-block;
  font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.3px;
  padding: 2px 8px; border-radius: 999px;
}
.iv__badge--critical { background: rgba(239,68,68,0.1); color: #dc2626; }
.iv__badge--warning { background: rgba(245,158,11,0.1); color: #d97706; }

.iv__alert-filters { display: flex; gap: 2px; }
.iv__filter-btn {
  padding: 4px 12px; border: none; border-radius: 6px;
  background: none; font-size: 12px; font-weight: 500; color: #71717a;
  cursor: pointer; transition: all 0.15s; font-family: inherit;
}
.iv__filter-btn:hover { color: #18181b; background: rgba(0,0,0,0.03); }
.iv__filter-btn--active { background: #18181b; color: #fff; }
.iv__filter-btn--active:hover { background: #27272a; }

/* ── Strategy ── */
.iv__strategy {
  padding: 12px;
  background: rgba(0,0,0,0.02);
  border-radius: 8px;
}
.iv__strat-cell { font-size: 22px; font-weight: 700; color: #18181b; margin-bottom: 4px; }
.iv__strat-text { font-size: 13px; color: #52525b; line-height: 1.5; margin: 0; }
.iv__strat-hint { font-size: 12px; color: #a1a1aa; text-align: center; padding: 16px 0; }

/* ── Trend Section ── */
.iv__trend-section { flex-shrink: 0; margin-bottom: 12px; }

/* ═══════ RIGHT PANEL ═══════ */
.iv__right {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fff;
  border-left: 1px solid rgba(0,0,0,0.06);
}

/* Tabs */
.iv__tabs {
  display: flex;
  border-bottom: 1px solid rgba(0,0,0,0.06);
  flex-shrink: 0;
}
.iv__tab {
  flex: 1;
  display: flex; align-items: center; justify-content: center; gap: 5px;
  padding: 10px 8px;
  border: none; background: none;
  font-size: 12px; font-weight: 500; color: #a1a1aa;
  cursor: pointer; transition: all 0.15s; font-family: inherit;
  border-bottom: 2px solid transparent;
}
.iv__tab:hover { color: #18181b; }
.iv__tab--active {
  color: #18181b;
  border-bottom-color: #18181b;
}

.iv__tab-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

/* ── Thread Bar ── */
.iv__thread-bar {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 12px;
  border-bottom: 1px solid rgba(0,0,0,0.04);
  flex-shrink: 0;
}
.iv__thread-select {
  flex: 1;
  border: 1px solid rgba(0,0,0,0.08);
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 11px;
  background: #fff;
  color: #18181b;
  font-family: inherit;
  outline: none;
}
.iv__thread-select:focus { border-color: rgba(0,0,0,0.2); }
.iv__thread-open {
  width: 28px; height: 28px;
  display: flex; align-items: center; justify-content: center;
  border: 1px solid rgba(0,0,0,0.08); border-radius: 6px;
  background: #fff; color: #71717a; cursor: pointer; transition: all 0.15s;
}
.iv__thread-open:hover { color: #18181b; background: #f4f4f5; }

/* ── Messages ── */
.iv__messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.iv__ai-welcome {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; flex: 1; gap: 10px;
}
.iv__ai-welcome p { font-size: 14px; font-weight: 600; color: #18181b; margin: 0; }
.iv__ai-chips { display: flex; flex-wrap: wrap; gap: 6px; justify-content: center; }
.iv__ai-chip {
  padding: 6px 12px; border: 1px solid rgba(0,0,0,0.08); border-radius: 999px;
  background: #fff; font-size: 12px; color: #18181b; cursor: pointer;
  transition: all 0.15s; font-family: inherit;
}
.iv__ai-chip:hover { background: #f4f4f5; border-color: rgba(0,0,0,0.15); }

.iv__msg { max-width: 100%; }
.iv__msg--user { align-self: flex-end; }
.iv__msg-bubble {
  background: #f4f4f5; color: #18181b;
  padding: 8px 14px; border-radius: 16px;
  font-size: 13px; line-height: 1.5; word-break: break-word;
}
.iv__msg--assistant { align-self: flex-start; }
.iv__msg--assistant :deep(code) { font-family: 'Geist Mono', monospace; font-size: 12px; }

.iv__msg-skill {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 11px; color: #71717a;
  padding: 3px 8px; background: rgba(0,0,0,0.03); border-radius: 5px;
  margin-bottom: 6px;
}
.iv__skill-dot {
  width: 5px; height: 5px; border-radius: 50%;
  background: #18181b; animation: pulse 1s infinite;
}
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }

.iv__msg-sources { margin-top: 6px; }
.iv__sources-btn {
  font-size: 11px; color: #71717a; background: none;
  border: 1px solid rgba(0,0,0,0.08); border-radius: 5px;
  padding: 2px 8px; cursor: pointer; font-family: inherit;
}
.iv__sources-btn:hover { color: #18181b; border-color: rgba(0,0,0,0.15); }
.iv__sources-list { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
.iv__source-chip {
  font-size: 10px; padding: 2px 8px;
  background: #fafafa; border: 1px solid rgba(0,0,0,0.06); border-radius: 4px;
  color: #18181b;
}
.iv__source-score { color: #a1a1aa; margin-left: 4px; }

.iv__msg-fb { display: flex; gap: 3px; margin-top: 6px; }
.iv__fb-btn {
  width: 24px; height: 24px;
  display: flex; align-items: center; justify-content: center;
  border: 1px solid rgba(0,0,0,0.06); border-radius: 5px;
  background: #fff; cursor: pointer; color: #a1a1aa; transition: all 0.15s;
}
.iv__fb-btn:hover { color: #18181b; background: #f4f4f5; }
.iv__fb-btn--on { color: #18181b; background: rgba(0,0,0,0.06); }

.iv__ai-error { font-size: 12px; color: #dc2626; padding: 6px 10px; background: rgba(220,38,38,0.04); border-radius: 5px; }

/* ── Responsive ── */
@media (max-width: 1400px) {
  .iv__body { grid-template-columns: 1fr 240px; }
}
@media (max-width: 1100px) {
  .iv__kpis { grid-template-columns: repeat(3, 1fr); }
  .iv__body { grid-template-columns: 1fr; }
  .iv__side-col { flex-direction: row; }
}
</style>
