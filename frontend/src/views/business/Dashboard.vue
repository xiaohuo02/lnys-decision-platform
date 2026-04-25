<template>
  <div class="db page-enter-active" :class="{ 'db--present': isPresenting }">
    <SplitInspector :hide-right="!showRight">
      <template #main>
        <div class="db__scroll">
          <!-- ① Hero -->
          <HeroBanner
            :user-name="userName"
            :current-time="currentTime"
            :now="now"
            :narrative="narrative"
            :todo-count="todoCount"
            :loading="data.loading.value"
            :is-presenting="isPresenting"
            :show-right="showRight"
            :delegating="heroDelegating"
            @refresh="data.refreshAll"
            @toggle-present="togglePresent"
            @toggle-right="showRight = !showRight"
            @cta-click="focusRef?.flash()"
            @delegate-ai="handleHeroDelegate"
          />

          <!-- ② 业务主 KPI -->
          <KpiGrid :items="kpiItems" @ask-ai="onAskAI" />

          <!-- ③ 系统辅助 KPI -->
          <SystemKpiRow :items="systemKpiItems" @ask-ai="onAskAI" />

          <!-- ④ 趋势 + 焦点 -->
          <div class="db__body">
            <SalesTrendChart :data="data.trendData.value" />
            <FocusList
              ref="focusRef"
              :items="focusItems"
              :todo-count="todoCount"
              :insight-text="insightText"
              @ask-ai="onAskAI"
            />
          </div>

          <!-- ⑤ 快捷入口 -->
          <QuickNav :cards="moduleCards" />
        </div>
      </template>

      <template #right>
        <PageAICopilotPanel
          ref="aiPanel"
          :ai="ai"
          welcome-title="AI 业务总览助手"
          welcome-desc="汇总经营数据、识别异常、提供决策建议"
          collection="general"
          command-bar-placeholder="询问业务相关问题...  @ 选择智能体"
          :quick-questions="quickQuestions"
          :mention-catalog="mentionCatalog"
        />
      </template>
    </SplitInspector>
  </div>
</template>

<script>
export default { name: 'Dashboard' }
</script>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { usePageCopilot } from '@/composables/usePageCopilot'
import { useAuthStore } from '@/stores/useAuthStore'
import { useDashboardData } from '@/composables/useDashboardData'
import { useRunStore } from '@/stores/useRunStore'
import { workflowApi } from '@/api/workflow'
import { SplitInspector, PageAICopilotPanel } from '@/components/v2'
import HeroBanner from '@/components/dashboard/HeroBanner.vue'
import KpiGrid from '@/components/dashboard/KpiGrid.vue'
import SystemKpiRow from '@/components/dashboard/SystemKpiRow.vue'
import SalesTrendChart from '@/components/dashboard/SalesTrendChart.vue'
import FocusList from '@/components/dashboard/FocusList.vue'
import QuickNav from '@/components/dashboard/QuickNav.vue'

const auth = useAuthStore()
const data = useDashboardData()
const runStore = useRunStore()

// ── C-γ.1: Hero 委托按钮 ──
const heroDelegating = ref(false)
async function handleHeroDelegate() {
  if (heroDelegating.value) return
  heroDelegating.value = true
  try {
    const request_text = `基于当前 Dashboard 数据（GMV=${data.kpiGmv.value ?? '未知'}、订单=${data.kpiOrders.value ?? '未知'}、活跃客户=${data.kpiCustomers.value ?? '未知'}、待审交易=${data.pendingReviews.value}、流失风险=${data.churnRiskCount.value}、库存预警=${data.kpiStockAlert.value ?? 0}）生成完整经营诊断：客户、预测、风控、舆情、库存、关联推荐全维度分析。`
    const res = await workflowApi.run({
      request_text,
      request_type: 'business_overview',
      use_mock: false,
    })
    const runId = res?.run_id || res?.data?.run_id
    if (!runId) throw new Error('未获取到 run_id')
    runStore.track({
      runId,
      streamUrl: `/api/v1/workflows/${runId}/stream`,
      route: 'business_overview',
      query: request_text,
      origin: 'dashboard_hero',
    })
    ElMessage.success('已交给 AI 生成今日经营诊断，完成后可在右上角任务栏查看')
  } catch (e) {
    console.error('[Dashboard] hero delegate failed:', e)
    ElMessage.error(e?.message || '委托失败，请稍后重试')
  } finally {
    heroDelegating.value = false
  }
}

// ── AI Copilot ──
const ai = usePageCopilot('dashboard', ['kb_rag'])
const aiPanel = ref(null)
const showRight = ref(false)
const isPresenting = ref(false)
const focusRef = ref(null)

const quickQuestions = [
  '今日业务整体运营状况如何？',
  '当前最需要关注的风险有哪些？',
  '给出今日经营优化建议',
]

const mentionCatalog = [
  { id: 'customer_intel', label: '客群洞察', type: 'skill', icon: '👥' },
  { id: 'forecast',       label: '销售预测', type: 'skill', icon: '📈' },
  { id: 'fraud',          label: '风控中心', type: 'skill', icon: '🛡️' },
  { id: 'inventory_skill',label: '库存管理', type: 'skill', icon: '📦' },
  { id: 'kb_rag',         label: '知识库',   type: 'collection', icon: '📚' },
]

function onAskAI({ question }) {
  showRight.value = true
  aiPanel.value?.askAndSwitch(question)
}

// ── Time ──
const currentTime = ref('')
const now = ref(new Date())
let timer = null
function updateTime() {
  const d = new Date()
  now.value = d
  const pad = (n) => String(n).padStart(2, '0')
  currentTime.value = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// ── Display helpers ──
const userName = computed(() => auth.displayName || auth.username || '')

function fmtK(n) {
  if (n == null) return '—'
  if (n >= 10000) return (n / 10000).toFixed(1) + 'w'
  if (n >= 1000)  return (n / 1000).toFixed(1) + 'K'
  return String(n)
}

function severityFromPct(pct, { warn = -3, critical = -10 } = {}) {
  if (pct == null) return 'ok'
  if (pct <= critical) return 'critical'
  if (pct <= warn)     return 'warn'
  return 'ok'
}

// ── Business narrative ──
const narrative = computed(() => {
  const parts = []
  const gmv = data.gmvPct.value
  if (data.kpiGmv.value == null && data.kpiOrders.value == null) {
    return '关键数据正在加载，稍候即可查看今日经营摘要。'
  }
  if (gmv < -10) parts.push(`今日 GMV 环比下降 ${Math.abs(gmv).toFixed(1)}%`)
  else if (gmv > 10) parts.push(`今日 GMV 环比上升 ${gmv.toFixed(1)}%`)
  if (data.pendingReviews.value > 0) parts.push(`${data.pendingReviews.value} 笔高风险交易待审`)
  if (data.lowStockSkus.value > 0)   parts.push(`${data.lowStockSkus.value} 个 SKU 库存告警`)
  if (data.churnRiskCount.value > 0) parts.push(`${data.churnRiskCount.value} 个客户流失风险`)
  if (!parts.length) return '今日业务平稳，建议关注预测趋势与客户画像变化。'
  return `关键信号：${parts.slice(0, 3).join('、')}。`
})

// ── KPI items ──
const kpiItems = computed(() => {
  const gmvSev   = severityFromPct(data.gmvPct.value,   { warn: -3,  critical: -10 })
  const orderSev = severityFromPct(data.orderPct.value, { warn: -3,  critical: -10 })
  const aovSev   = severityFromPct(data.aovPct.value,   { warn: -5,  critical: -15 })
  const gmvPct = data.gmvPct.value
  const orderPct = data.orderPct.value
  const aovPct = data.aovPct.value
  return [
    {
      key: 'gmv', label: '今日 GMV', prefix: '¥', hero: true,
      value: data.kpiGmv.value,
      sub: data.kpiGmv.value != null ? `${gmvPct > 0 ? '↑' : '↓'}${Math.abs(gmvPct).toFixed(1)}% 较昨日` : '数据加载中',
      severity: gmvSev,
      actionLabel: gmvSev !== 'ok' ? '查看归因' : null,
      aiQ: '今日 GMV 表现如何？环比趋势和主要驱动因素分析',
    },
    {
      key: 'orders', label: '今日订单',
      value: data.kpiOrders.value,
      sub: data.kpiOrders.value != null ? `${orderPct > 0 ? '↑' : '↓'}${Math.abs(orderPct).toFixed(1)}% 较昨日` : '数据加载中',
      severity: orderSev,
      actionLabel: orderSev !== 'ok' ? '查看归因' : null,
      aiQ: '今日订单量变化原因分析和预期',
    },
    {
      key: 'aov', label: '今日客单价', prefix: '¥',
      value: data.kpiAov.value, decimals: 1,
      sub: data.kpiAov.value != null ? `${aovPct > 0 ? '↑' : '↓'}${Math.abs(aovPct).toFixed(1)}% 较上周` : '数据加载中',
      severity: aovSev,
      actionLabel: aovSev !== 'ok' ? '查看归因' : null,
      aiQ: '客单价变化的原因和提升策略',
    },
    {
      key: 'fraud', label: '今日拦截',
      value: data.kpiFraud.value, suffix: ' 笔',
      sub: data.pendingReviews.value > 0
        ? `${data.pendingReviews.value} 待审`
        : (data.kpiFraud.value != null ? `拦截率 ${data.fraudRate.value.toFixed(1)}%` : '数据加载中'),
      severity: data.pendingReviews.value > 0 ? 'warn' : 'ok',
      actionLabel: data.pendingReviews.value > 0 ? '去审核' : null,
      actionLink: '/fraud',
      aiQ: '今日欺诈拦截情况和风险趋势',
    },
  ]
})

const systemKpiItems = computed(() => [
  {
    key: 'customers', label: '近30天活跃客户',
    value: data.kpiCustomers.value,
    severity: 'ok',
    aiQ: '活跃客户的画像特征和留存率分析',
  },
  {
    key: 'ai', label: 'AI 处理量',
    value: data.kpiAiRuns.value,
    sub: data.aiSuccessRate.value ? `成功率 ${data.aiSuccessRate.value.toFixed(1)}%` : '',
    severity: data.aiSuccessRate.value && data.aiSuccessRate.value < 95 ? 'warn' : 'ok',
    aiQ: 'AI 智能体今日处理效率和健康状况',
  },
  {
    key: 'stock', label: '库存预警',
    value: data.kpiStockAlert.value, suffix: ' SKU',
    sub: data.kpiStockAlert.value == null
      ? '数据加载中'
      : (data.kpiStockAlert.value > 0 ? '需补货' : '库存健康'),
    severity: data.kpiStockAlert.value == null
      ? 'ok'
      : (data.kpiStockAlert.value > 20 ? 'critical' : (data.kpiStockAlert.value > 0 ? 'warn' : 'ok')),
    actionLabel: data.kpiStockAlert.value > 0 ? '去查看' : null,
    actionLink: '/inventory',
    aiQ: '当前库存预警详情和补货优先级建议',
  },
])

// ── Focus ──
const PRIORITY_RANK = { P0: 0, P1: 1, P2: 2, ok: 99 }

const focusItems = computed(() => {
  const items = []
  if (data.pendingReviews.value > 0) {
    items.push({
      level: 'critical', priority: 'P0',
      title: `${data.pendingReviews.value} 笔高风险交易待审`,
      impact: '每笔平均标的约 ¥5,000+，延迟审核可能造成损失扩大',
      // C-α: 指向业务前台 fraud 页的待审 Tab（而非治理后台审计日志），目标页自动聚焦
      link: '/fraud?tab=reviews',
      action: '去审核',
      aiQ: `${data.pendingReviews.value} 笔高风险交易的处置建议和审核优先级`,
      intent: 'review_high_risk',
      intentPayload: { pending: data.pendingReviews.value },
    })
  }
  if (data.kpiStockAlert.value != null && data.kpiStockAlert.value > 20) {
    items.push({
      level: 'critical', priority: 'P0',
      title: `${data.kpiStockAlert.value} 个 SKU 严重缺货`,
      impact: `预计影响 ¥${fmtK(data.kpiStockAlert.value * 3200)} 销售额`,
      link: '/inventory',
      action: '生成补货单',
      aiQ: `${data.kpiStockAlert.value} 个缺货 SKU 的补货优先级和供应商建议`,
      intent: 'replenish_sku',
      intentPayload: { severity: 'critical', count: data.kpiStockAlert.value },
    })
  } else if (data.lowStockSkus.value > 0) {
    items.push({
      level: 'warning', priority: 'P1',
      title: `${data.lowStockSkus.value} 个 SKU 库存低于安全线`,
      impact: '若不补货，预计 3-5 天内出现缺货',
      link: '/inventory',
      action: '查看详情',
      aiQ: `${data.lowStockSkus.value} 个 SKU 的库存状态和补货建议`,
      intent: 'replenish_sku',
      intentPayload: { severity: 'warning', count: data.lowStockSkus.value },
    })
  }
  if (data.churnRiskCount.value > 0) {
    items.push({
      level: 'warning', priority: 'P1',
      title: `${data.churnRiskCount.value} 个客户存在流失风险`,
      impact: `合计 CLV 约 ¥${fmtK(data.churnRiskCount.value * 8500)}`,
      link: '/customer',
      action: '查看画像',
      aiQ: `${data.churnRiskCount.value} 个流失风险客户的挽留策略`,
      intent: 'view_churn_customers',
      intentPayload: { threshold: 0.7, count: data.churnRiskCount.value },
    })
  }
  if (data.negativeRate.value > 5) {
    items.push({
      level: 'info', priority: 'P2',
      title: `舆情负面率 ${data.negativeRate.value}%`,
      impact: `高于基线 ${(data.negativeRate.value - 5).toFixed(1)} 个百分点`,
      link: '/sentiment/analyze',
      action: '去分析',
      aiQ: '当前负面舆情的主要话题和应对建议',
      intent: 'analyze_negative',
      intentPayload: { rate: data.negativeRate.value },
    })
  }
  if (!items.length) {
    items.push({
      level: 'ok', priority: 'ok',
      title: '今日一切正常',
      impact: '暂无需要紧急处理的事项',
      link: '', action: '', aiQ: '',
    })
  }
  items.sort((a, b) => (PRIORITY_RANK[a.priority] ?? 99) - (PRIORITY_RANK[b.priority] ?? 99))
  return items
})

const todoCount = computed(() => focusItems.value.filter((i) => i.level !== 'ok').length)

const insightText = computed(() => {
  const parts = []
  if (data.kpiGmv.value != null) {
    parts.push(`今日 GMV ¥${fmtK(data.kpiGmv.value)}，${data.gmvPct.value >= 0 ? '环比增长' : '环比下降'} ${Math.abs(data.gmvPct.value).toFixed(1)}%。`)
  }
  if (data.kpiFraud.value != null && data.kpiFraud.value > 0) parts.push(`欺诈检测智能体拦截 ${data.kpiFraud.value} 笔高风险交易。`)
  if (data.churnRiskCount.value > 0) parts.push(`${data.churnRiskCount.value} 个客户流失风险需干预。`)
  if (data.lowStockSkus.value > 0)   parts.push(`${data.lowStockSkus.value} 个 SKU 库存低于安全线。`)

  if (!parts.length) return '综合研判：数据正在汇总，请稍候。'

  const riskCount =
    (data.pendingReviews.value > 0 ? 1 : 0) +
    (data.churnRiskCount.value > 0 ? 1 : 0) +
    (data.lowStockSkus.value > 0 ? 1 : 0)
  if (riskCount >= 2) parts.push('综合研判：多维度风险信号叠加，建议优先处理 P0 事项。')
  else if (data.gmvPct.value < -5) parts.push('综合研判：营收承压，建议进入分析工作台查看归因。')
  else parts.push('综合研判：整体可控，持续监测即可。')
  return parts.join('')
})

// ── Quick nav cards ──
const moduleCards = computed(() => {
  const cards = []
  if (data.gmvPct.value < 0) {
    cards.push({
      emoji: '📉', title: '分析 GMV 下滑原因',
      desc: `今日 GMV 环比下降 ${Math.abs(data.gmvPct.value).toFixed(1)}%，AI 可协助归因`,
      path: '/analyze', primary: true,
    })
  } else {
    cards.push({
      emoji: '🤖', title: '生成今日经营诊断',
      desc: 'AI 多智能体协同分析，一键输出经营洞察',
      path: '/analyze', primary: true,
    })
  }
  if (data.churnRiskCount.value > 0) {
    cards.push({
      emoji: '👥', title: `跟进 ${data.churnRiskCount.value} 个流失风险客户`,
      desc: `合计 CLV ¥${fmtK(data.churnRiskCount.value * 8500)}，建议查看画像并干预`,
      path: '/customer', primary: false,
    })
  } else {
    cards.push({
      emoji: '👥', title: '查看客户画像与分群',
      desc: 'RFM 分群 · CLV 排行 · 留存分析',
      path: '/customer', primary: false,
    })
  }
  cards.push({
    emoji: '📄', title: '生成本日经营简报',
    desc: '汇总 KPI、风险、库存状态，一键导出',
    path: '/report', primary: false,
  })
  return cards
})

// ── Presentation Mode ──
function togglePresent() {
  isPresenting.value = !isPresenting.value
  if (isPresenting.value) {
    showRight.value = false
    const el = document.documentElement
    if (el.requestFullscreen) {
      el.requestFullscreen().catch(() => { /* silent */ })
    }
  } else if (document.fullscreenElement && document.exitFullscreen) {
    document.exitFullscreen().catch(() => { /* silent */ })
  }
}

function onFsChange() {
  if (!document.fullscreenElement && isPresenting.value) isPresenting.value = false
}

function onKeydown(e) {
  if (e.key === 'Escape' && isPresenting.value) {
    isPresenting.value = false
    if (document.fullscreenElement && document.exitFullscreen) document.exitFullscreen().catch(() => { /* silent */ })
  }
}

// ── Lifecycle ──
onMounted(async () => {
  updateTime()
  timer = setInterval(updateTime, 60000)
  data.refreshAll()
  document.addEventListener('fullscreenchange', onFsChange)
  document.addEventListener('keydown', onKeydown)
  await ai.init()
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
  document.removeEventListener('fullscreenchange', onFsChange)
  document.removeEventListener('keydown', onKeydown)
  if (document.fullscreenElement && document.exitFullscreen) document.exitFullscreen().catch(() => { /* silent */ })
})
</script>

<style scoped>
.db { display: flex; flex-direction: column; gap: 0; height: 100%; }
.db__scroll { display: flex; flex-direction: column; gap: 10px; padding: 10px 14px; overflow-y: auto; }

.db__body { display: grid; grid-template-columns: 5fr 3fr; gap: 10px; min-height: 280px; }

@media (max-width: 1024px) {
  .db__body { grid-template-columns: 1fr; }
}

/* 演示模式 */
.db--present {
  position: fixed; inset: 0; z-index: 9999;
  background: var(--v2-bg-page);
  padding: var(--v2-space-5);
  gap: var(--v2-space-4);
  isolation: isolate;
}
.db--present::before {
  content: ''; position: absolute; inset: 0;
  background: radial-gradient(ellipse at center, transparent 55%, rgba(0,0,0,0.10) 100%);
  pointer-events: none; z-index: 0;
}
.db--present > * { position: relative; z-index: 1; }
.db--present .db__scroll { padding: 0; gap: var(--v2-space-4); }
.db--present .db__body { min-height: 46vh; gap: var(--v2-space-4); }
</style>
