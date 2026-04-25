<template>
  <div class="cd">
    <!-- ── Header ── -->
    <div class="cd__hd">
      <div class="cd__hd-left">
        <h2 class="cd__title">治理总览</h2>
      </div>
      <div class="cd__hd-right">
        <V2Segment v-model="timeRange" :options="TIME_RANGES" size="sm" @change="load" />
        <V2Segment v-model="refreshInterval" :options="REFRESH_OPTS" size="sm" @change="resetAutoRefresh" />
        <V2Button variant="ghost" size="sm" icon-only :loading="loading" @click="load">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.636-6.364"/><path d="M21 3v6h-6"/></svg>
        </V2Button>
      </div>
    </div>

    <!-- ── Degraded banner ── -->
    <div v-if="isDegraded" class="cd__alert cd__alert--degraded">
      <span class="cd__alert-dot" />
      <span>部分数据加载异常，当前为降级模式</span>
    </div>

    <!-- ── KPI Strip: 6 Odometer Cards ── -->
    <div class="cd__kpi">
      <div
        v-for="kpi in kpiCards" :key="kpi.key"
        class="cd__kpi-card"
        :class="{ 'cd__kpi-card--clickable': kpi.link }"
        @click="kpi.link && $router.push(kpi.link)"
      >
        <span class="cd__kpi-label">{{ kpi.label }}</span>
        <div class="cd__kpi-value">
          <Odometer :value="kpi.value" :duration="800" :decimals="kpi.decimals || 0" />
          <span v-if="kpi.unit" class="cd__kpi-unit">{{ kpi.unit }}</span>
        </div>
        <div class="cd__kpi-trend" :class="kpi.trendClass">
          <svg v-if="kpi.trend > 0" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg>
          <svg v-else-if="kpi.trend < 0" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M19 12l-7 7-7-7"/></svg>
          <span v-if="kpi.trend !== 0">{{ Math.abs(kpi.trend) }}%</span>
          <span v-else class="cd__kpi-flat">—</span>
        </div>
      </div>
    </div>

    <!-- ── Middle Row: Timeseries (60%) + Agent Matrix (40%) ── -->
    <div class="cd__mid">
      <!-- Timeseries area chart -->
      <div class="cd__panel cd__panel--ts">
        <div class="cd__ph">
          <span>运行量趋势</span>
          <V2Badge v-if="tsError" variant="error" label="加载失败" dot />
        </div>
        <div v-if="tsLoading" class="cd__panel-loading">
          <span class="cd__spinner" />
        </div>
        <v-chart v-else-if="tsOption" :option="tsOption" autoresize class="cd__chart" />
        <div v-else class="cd__nil">暂无时序数据</div>
      </div>

      <!-- Agent health matrix -->
      <div class="cd__panel cd__panel--matrix">
        <div class="cd__ph">
          <span>Agent 健康矩阵</span>
          <button class="cd__link-btn" @click="$router.push('/console/agent-hub')">详情 →</button>
        </div>
        <div v-if="agentLoading" class="cd__panel-loading"><span class="cd__spinner" /></div>
        <div v-else-if="agentMatrix.length" class="cd__matrix">
          <div
            v-for="a in agentMatrix" :key="a.key"
            class="cd__matrix-cell"
            :class="'cd__matrix-cell--' + a.health"
            :title="`${a.label}: ${a.healthLabel} (${a.error_calls} 失败 / ${a.total_calls} 总调用)`"
            @click="$router.push('/console/agent-hub')"
          >
            <span class="cd__matrix-name">{{ a.shortLabel }}</span>
            <span class="cd__matrix-val">
              <svg v-if="a.health === 'ok'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>
              <span v-else>{{ a.error_calls > 0 ? a.error_calls + '⚠' : '—' }}</span>
            </span>
          </div>
        </div>
        <div v-else class="cd__nil">无 Agent 数据</div>
      </div>
    </div>

    <!-- ── Bottom Row: Failures (60%) + Activity Preview (40%) ── -->
    <div class="cd__bot">
      <!-- Recent failures -->
      <div class="cd__panel cd__panel--fails">
        <div class="cd__ph">
          <span>失败与异常</span>
          <button class="cd__link-btn" @click="$router.push('/console/traces?status=failed')">全部 →</button>
        </div>
        <div v-if="failLoading" class="cd__panel-loading"><span class="cd__spinner" /></div>
        <div v-else-if="recentFails.length" class="cd__fails">
          <div v-for="r in recentFails" :key="r.run_id" class="cd__fail" @click="$router.push(`/console/traces/${r.run_id}`)">
            <div class="cd__fail-top">
              <span class="cd__fail-wf">{{ r.workflow_name }}</span>
              <V2Badge variant="error" :label="STATUS_LABELS[r.status] || r.status" />
            </div>
            <div class="cd__fail-id">{{ r.run_id?.slice(0, 16) }} · {{ r._time }}</div>
            <div v-if="r.error_message" class="cd__fail-msg">{{ r.error_message?.slice(0, 120) }}</div>
          </div>
        </div>
        <div v-else class="cd__nil cd__nil--ok">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="M22 4L12 14.01l-3-3"/></svg>
          <span>所有运行正常</span>
        </div>
      </div>

      <!-- Activity feed preview -->
      <div class="cd__panel cd__panel--feed">
        <div class="cd__ph">
          <span>最近活动</span>
          <button class="cd__link-btn" @click="$router.push('/console/activity')">查看全部 →</button>
        </div>
        <div v-if="feedLoading" class="cd__panel-loading"><span class="cd__spinner" /></div>
        <div v-else-if="recentActivity.length" class="cd__feed">
          <div v-for="evt in recentActivity" :key="evt.id" class="cd__feed-item">
            <span class="cd__feed-dot" :class="'cd__feed-dot--' + evt._severity" />
            <div class="cd__feed-body">
              <span class="cd__feed-action">{{ evt._actionLabel }}</span>
              <span class="cd__feed-time">{{ evt._timeLabel }}</span>
            </div>
          </div>
        </div>
        <div v-else class="cd__nil">暂无活动</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { adminApi } from '@/api/admin/index'
import { auditApi } from '@/api/admin/audit'
import { agentsApi } from '@/api/admin/agents'
import { fmtRelative as fmtRelTime, fmtShort as fmtTime } from '@/utils/time'
import Odometer from '@/components/v2/Odometer.vue'
import V2Segment from '@/components/v2/V2Segment.vue'
import V2Button from '@/components/v2/V2Button.vue'
import V2Badge from '@/components/v2/V2Badge.vue'

const route = useRoute()
const router = useRouter()

// ── Time range & auto-refresh ──
const TIME_RANGES = [
  { label: '1h', value: '1h' },
  { label: '6h', value: '6h' },
  { label: '24h', value: '24h' },
  { label: '7d', value: '7d' },
]
const REFRESH_OPTS = [
  { label: '⟳ 15s', value: 15 },
  { label: '30s', value: 30 },
  { label: '1m', value: 60 },
  { label: '关', value: 0 },
]

const timeRange = ref(route.query.range || '24h')
const refreshInterval = ref(Number(route.query.refresh) || 30)
let refreshTimer = null

function resetAutoRefresh() {
  if (refreshTimer) clearInterval(refreshTimer)
  refreshTimer = null
  if (refreshInterval.value > 0) {
    refreshTimer = setInterval(load, refreshInterval.value * 1000)
  }
  router.replace({ query: { ...route.query, range: timeRange.value, refresh: refreshInterval.value || undefined } })
}

// ── State ──
const loading = ref(false)
const summary = ref({})
const isDegraded = ref(false)

// KPI
const kpiCards = computed(() => {
  const s = summary.value
  const total = s.total_runs ?? 0
  const failed = s.failed_runs ?? 0
  const successRate = s.success_rate != null ? Math.round(s.success_rate * 100) : 0
  const latency = s.avg_latency_ms ?? 0
  const tokens = s.total_tokens ?? 0
  const pending = s.pending_reviews ?? 0

  return [
    { key: 'runs',    label: '运行次数', value: total,       trend: 0, trendClass: '', link: '/console/traces' },
    { key: 'success', label: '成功率',   value: successRate, unit: '%', trend: 0, trendClass: '', decimals: 0 },
    { key: 'latency', label: '平均延迟', value: latency,     unit: 'ms', trend: 0, trendClass: '', decimals: 0 },
    { key: 'tokens',  label: 'Token 消耗', value: tokens,    trend: 0, trendClass: '' },
    { key: 'failed',  label: '失败',     value: failed,      trend: 0, trendClass: failed > 0 ? 'cd__kpi-trend--err' : '', link: '/console/traces?status=failed' },
    { key: 'pending', label: '待审核',   value: pending,     trend: 0, trendClass: pending > 0 ? 'cd__kpi-trend--warn' : '' },
  ]
})

// ── Timeseries ──
const tsLoading = ref(false)
const tsError = ref(false)
const tsOption = ref(null)

function buildTsOption(traces) {
  if (!traces?.length) return null
  const buckets = new Map()
  const errBuckets = new Map()
  const interval = timeRange.value === '1h' ? 300000 : timeRange.value === '6h' ? 900000 : timeRange.value === '24h' ? 3600000 : 86400000

  for (const t of traces) {
    const ts = new Date(t.started_at).getTime()
    if (isNaN(ts)) continue
    const bucket = Math.floor(ts / interval) * interval
    buckets.set(bucket, (buckets.get(bucket) || 0) + 1)
    if (t.status === 'failed') errBuckets.set(bucket, (errBuckets.get(bucket) || 0) + 1)
  }

  const sorted = [...buckets.keys()].sort()
  const data = sorted.map(k => [k, buckets.get(k)])
  const errData = sorted.map(k => [k, errBuckets.get(k) || 0])

  return {
    grid: { left: 40, right: 16, top: 12, bottom: 28 },
    tooltip: { trigger: 'axis', backgroundColor: 'var(--v2-bg-elevated)', borderColor: 'var(--v2-border-2)', textStyle: { color: 'var(--v2-text-1)', fontSize: 11 } },
    xAxis: { type: 'time', axisLine: { show: false }, axisTick: { show: false }, axisLabel: { fontSize: 10, color: 'var(--v2-text-4)' }, splitLine: { show: false } },
    yAxis: { type: 'value', axisLine: { show: false }, axisTick: { show: false }, axisLabel: { fontSize: 10, color: 'var(--v2-text-4)' }, splitLine: { lineStyle: { color: 'var(--v2-border-1)', type: 'dashed' } } },
    series: [
      { name: '运行量', type: 'line', data, smooth: true, symbol: 'none', lineStyle: { width: 1.5, color: 'var(--v2-text-3)' }, areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(113,113,122,0.15)' }, { offset: 1, color: 'rgba(113,113,122,0.02)' }] } } },
      { name: '失败', type: 'line', data: errData, smooth: true, symbol: 'none', lineStyle: { width: 1.5, color: 'var(--v2-error)', type: 'dashed' }, areaStyle: { color: 'rgba(239,68,68,0.06)' } },
    ],
  }
}

// ── Agent matrix ──
const agentLoading = ref(false)
const agentMatrix = ref([])

const AGENT_SHORT = {
  customer_agent: '客户', forecast_agent: '预测', fraud_agent: '风控',
  sentiment_agent: '舆情', inventory_agent: '库存', openclaw_agent: '客服',
  association_agent: '关联',
}

// ── Failures ──
const failLoading = ref(false)
const recentFails = ref([])

// ── Activity feed preview ──
const feedLoading = ref(false)
const recentActivity = ref([])

const ACTION_LABELS = {
  'user.login': '用户登录', 'user.logout': '用户登出', 'user.created': '用户创建',
  'prompt.created': '提示词创建', 'prompt.updated': '提示词更新',
  'policy.created': '策略创建', 'policy.activated': '策略激活',
  'release.created': '发布创建', 'release.rolled_back': '发布回滚',
  'faq.created': 'FAQ 创建', 'memory.disabled': '记忆禁用',
  'create_review': '创建审核', 'create_release': '创建发布',
  'activate_policy': '激活策略', 'create_policy': '创建策略',
  'release_prompt': '发布提示词', 'update_prompt': '更新提示词',
  'delete_policy': '删除策略', 'rollback_release': '回滚发布',
  'create_faq': '创建 FAQ', 'disable_memory': '禁用记忆',
  'enable_memory': '启用记忆', 'create_agent': '创建智能体',
  'update_agent': '更新智能体', 'run_workflow': '运行工作流',
  'complete_review': '完成审核', 'reject_review': '驳回审核',
}

const STATUS_LABELS = {
  failed: '失败', completed: '已完成', running: '运行中',
  pending: '等待中', cancelled: '已取消', timeout: '超时',
}

function getSeverity(action) {
  const a = (action || '').toLowerCase()
  if (a.includes('fail') || a.includes('error') || a.includes('rollback')) return 'error'
  if (a.includes('alert') || a.includes('review')) return 'warning'
  if (a.includes('create') || a.includes('complete') || a.includes('login')) return 'success'
  return 'neutral'
}

// fmtRelTime & fmtTime imported from @/utils/time (UTC-safe)

// ── Parallel data loading ──
async function load() {
  loading.value = true

  const [summaryRes, tracesRes, failRes, agentsRes, auditRes] = await Promise.allSettled([
    adminApi.getDashboardSummary(),
    adminApi.getTraces({ limit: 200, offset: 0 }),
    adminApi.getTraces({ status: 'failed', limit: 5, offset: 0 }),
    agentsApi.getOverview(),
    auditApi.getLogs({ limit: 5, offset: 0 }),
  ])

  // Summary
  if (summaryRes.status === 'fulfilled') {
    summary.value = summaryRes.value ?? {}
    isDegraded.value = !!summary.value._meta?.degraded || !!summary.value._degraded
  } else {
    isDegraded.value = true
  }

  // Timeseries
  tsLoading.value = false
  if (tracesRes.status === 'fulfilled') {
    tsOption.value = buildTsOption(tracesRes.value?.items || [])
    tsError.value = false
  } else {
    tsError.value = true
  }

  // Failures
  failLoading.value = false
  if (failRes.status === 'fulfilled') {
    recentFails.value = (failRes.value?.items ?? []).map(r => ({ ...r, _time: fmtTime(r.started_at) }))
  }

  // Agent matrix
  agentLoading.value = false
  if (agentsRes.status === 'fulfilled') {
    const serverAgents = agentsRes.value?.agents ?? []
    const byName = {}
    for (const a of serverAgents) byName[a.name] = a
    agentMatrix.value = Object.entries(AGENT_SHORT).map(([key, shortLabel]) => {
      const s = byName[key] || {}
      const errorRate = s.total_calls > 0 ? s.error_calls / s.total_calls : 0
      let health = 'ok'
      if (s.status === 'unknown' || !s.status) health = 'unknown'
      else if (errorRate > 0.1) health = 'critical'
      else if (errorRate > 0.02) health = 'warning'
      return {
        key, shortLabel,
        label: key.replace(/_/g, ' '),
        health,
        healthLabel: health === 'ok' ? '健康' : health === 'warning' ? '告警' : health === 'critical' ? '异常' : '未知',
        total_calls: s.total_calls || 0,
        error_calls: s.error_calls || 0,
      }
    })
  }

  // Activity feed
  feedLoading.value = false
  if (auditRes.status === 'fulfilled') {
    const items = auditRes.value?.items || auditRes.value || []
    recentActivity.value = (Array.isArray(items) ? items : []).slice(0, 5).map(e => ({
      ...e,
      id: e.id || e.audit_id || Math.random(),
      _actionLabel: ACTION_LABELS[e.action] || e.action || '操作',
      _severity: getSeverity(e.action),
      _timeLabel: fmtRelTime(new Date(e.timestamp || e.created_at || Date.now())),
    }))
  }

  loading.value = false
}

// ── Lifecycle ──
onMounted(() => {
  tsLoading.value = true
  agentLoading.value = true
  failLoading.value = true
  feedLoading.value = true
  load()
  resetAutoRefresh()
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})
</script>

<style scoped>
/* ── Header ── */
.cd__hd { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--v2-space-4); }
.cd__hd-left { display: flex; align-items: center; gap: var(--v2-space-2); }
.cd__title { font-size: var(--v2-text-lg); font-weight: var(--v2-font-semibold); color: var(--v2-text-1); margin: 0; }
.cd__hd-right { display: flex; align-items: center; gap: var(--v2-space-2); }

/* ── Alert ── */
.cd__alert { display: flex; align-items: center; gap: var(--v2-space-3); padding: var(--v2-space-2) var(--v2-space-4); margin-bottom: var(--v2-space-3); background: var(--v2-warning-bg); border: var(--v2-border-width) solid rgba(245,158,11,.2); border-radius: var(--v2-radius-md); font-size: var(--v2-text-sm); color: var(--v2-warning-text); }
.cd__alert-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--v2-warning); flex-shrink: 0; animation: cd-pulse 1.5s infinite; }
@keyframes cd-pulse { 0%,100%{opacity:1} 50%{opacity:.3} }
.cd__alert--degraded { background: var(--v2-error-bg); border-color: rgba(239,68,68,.2); color: var(--v2-error-text); }
.cd__alert--degraded .cd__alert-dot { background: var(--v2-error); }

/* ── KPI Strip ── */
.cd__kpi {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: var(--v2-space-3);
  margin-bottom: var(--v2-space-4);
}
.cd__kpi-card {
  background: var(--v2-bg-card);
  border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-lg);
  padding: var(--v2-space-3) var(--v2-space-4);
  display: flex;
  flex-direction: column;
  gap: 4px;
  transition: border-color var(--v2-trans-fast);
}
.cd__kpi-card--clickable { cursor: pointer; }
.cd__kpi-card--clickable:hover { border-color: var(--v2-text-3); }
.cd__kpi-label {
  font-size: 10px;
  font-weight: var(--v2-font-semibold);
  color: var(--v2-text-4);
  text-transform: uppercase;
  letter-spacing: .05em;
}
.cd__kpi-value {
  display: flex;
  align-items: baseline;
  gap: 3px;
}
.cd__kpi-value :deep(.v2-odometer) {
  font-size: var(--v2-text-xl);
  font-weight: var(--v2-font-bold);
  color: var(--v2-text-1);
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
}
.cd__kpi-unit {
  font-size: var(--v2-text-xs);
  color: var(--v2-text-4);
  font-weight: 400;
}
.cd__kpi-trend {
  display: flex;
  align-items: center;
  gap: 2px;
  font-size: 10px;
  color: var(--v2-text-4);
  font-variant-numeric: tabular-nums;
}
.cd__kpi-trend--err { color: var(--v2-error); }
.cd__kpi-trend--warn { color: var(--v2-warning); }
.cd__kpi-flat { color: var(--v2-text-4); }

/* ── Middle row ── */
.cd__mid {
  display: grid;
  grid-template-columns: 3fr 2fr;
  gap: var(--v2-space-3);
  margin-bottom: var(--v2-space-3);
}

/* ── Bottom row ── */
.cd__bot {
  display: grid;
  grid-template-columns: 3fr 2fr;
  gap: var(--v2-space-3);
}

/* ── Panels ── */
.cd__panel {
  background: var(--v2-bg-card);
  border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-lg);
  padding: var(--v2-space-4);
  display: flex;
  flex-direction: column;
  min-height: 200px;
}
.cd__ph {
  font-size: 10px;
  font-weight: var(--v2-font-semibold);
  color: var(--v2-text-4);
  text-transform: uppercase;
  letter-spacing: .05em;
  margin-bottom: var(--v2-space-3);
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.cd__link-btn {
  font-size: var(--v2-text-xs);
  color: var(--v2-text-3);
  background: transparent;
  border: none;
  cursor: pointer;
  font-weight: var(--v2-font-medium);
  transition: color var(--v2-trans-fast);
}
.cd__link-btn:hover { color: var(--v2-text-1); }

.cd__panel-loading {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}
.cd__spinner {
  width: 20px; height: 20px;
  border: 2px solid var(--v2-border-2);
  border-top-color: var(--v2-text-3);
  border-radius: 50%;
  animation: cd-spin .6s linear infinite;
}
@keyframes cd-spin { from{transform:rotate(0)} to{transform:rotate(360deg)} }

/* Chart */
.cd__chart { flex: 1; min-height: 180px; }

/* ── Agent matrix ── */
.cd__matrix {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 6px;
  flex: 1;
}
.cd__matrix-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--v2-space-3) var(--v2-space-2);
  border-radius: var(--v2-radius-md);
  cursor: pointer;
  transition: var(--v2-trans-fast);
  gap: 4px;
}
.cd__matrix-cell--ok { background: rgba(34,197,94,0.06); }
.cd__matrix-cell--warning { background: rgba(245,158,11,0.08); }
.cd__matrix-cell--critical { background: rgba(239,68,68,0.08); }
.cd__matrix-cell--unknown { background: var(--v2-bg-sunken); opacity: 0.6; }
.cd__matrix-cell:hover { opacity: 0.7; }
.cd__matrix-name {
  font-size: 11px;
  font-weight: var(--v2-font-medium);
  color: var(--v2-text-2);
}
.cd__matrix-val {
  font-size: 10px;
  color: var(--v2-text-4);
  font-variant-numeric: tabular-nums;
}
.cd__matrix-cell--ok .cd__matrix-val { color: #16a34a; }
.cd__matrix-cell--ok .cd__matrix-val svg { stroke: #16a34a; }
.cd__matrix-cell--critical .cd__matrix-val { color: var(--v2-error); }
.cd__matrix-cell--warning .cd__matrix-val { color: var(--v2-warning); }

/* ── Failures ── */
.cd__fails { display: flex; flex-direction: column; gap: 6px; flex: 1; overflow-y: auto; }
.cd__fail { padding: 8px 10px; background: var(--v2-bg-sunken); border-radius: var(--v2-radius-md); cursor: pointer; transition: background var(--v2-trans-fast); }
.cd__fail:hover { background: var(--v2-border-1); }
.cd__fail-top { display: flex; align-items: center; gap: 6px; }
.cd__fail-wf { font-size: 12px; font-weight: var(--v2-font-medium); color: var(--v2-text-1); }
.cd__fail-id { font-size: 10px; color: var(--v2-text-4); font-family: var(--v2-font-mono); margin-top: 2px; }
.cd__fail-msg { font-size: 11px; color: var(--v2-error); margin-top: 3px; line-height: 1.35; }

/* ── Activity feed preview ── */
.cd__feed { display: flex; flex-direction: column; gap: 2px; flex: 1; }
.cd__feed-item {
  display: flex;
  align-items: center;
  gap: var(--v2-space-2);
  padding: 6px 8px;
  border-radius: var(--v2-radius-sm);
  transition: background var(--v2-trans-fast);
}
.cd__feed-item:hover { background: var(--v2-bg-hover); }
.cd__feed-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
  background: var(--v2-gray-400);
}
.cd__feed-dot--error { background: var(--v2-error); }
.cd__feed-dot--warning { background: var(--v2-warning); }
.cd__feed-dot--success { background: var(--v2-success); }
.cd__feed-body {
  flex: 1;
  display: flex;
  justify-content: space-between;
  align-items: center;
  min-width: 0;
}
.cd__feed-action {
  font-size: var(--v2-text-sm);
  color: var(--v2-text-2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cd__feed-time {
  font-size: var(--v2-text-xs);
  color: var(--v2-text-4);
  white-space: nowrap;
  margin-left: var(--v2-space-2);
  font-variant-numeric: tabular-nums;
}

/* ── Empty state ── */
.cd__nil {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: var(--v2-text-sm);
  color: var(--v2-text-4);
  padding: var(--v2-space-4);
}
.cd__nil--ok { color: var(--v2-success); }

/* ── Responsive ── */
@media (max-width: 1200px) {
  .cd__kpi { grid-template-columns: repeat(3, 1fr); }
  .cd__mid, .cd__bot { grid-template-columns: 1fr; }
}
@media (max-width: 768px) {
  .cd__kpi { grid-template-columns: repeat(2, 1fr); }
  .cd__hd { flex-direction: column; align-items: flex-start; gap: var(--v2-space-2); }
}
</style>
