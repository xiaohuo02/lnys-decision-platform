<template>
  <div class="td">
    <!-- ── Row 1: Metric Cards ── -->
    <div class="td__metrics">
      <div class="td__card" v-for="m in metricCards" :key="m.key">
        <div class="td__card-label">{{ m.label }}</div>
        <div class="td__card-value" :class="m.cls">
          <span class="td__odometer" :data-v="m.value">{{ m.display }}</span>
        </div>
        <div class="td__card-sub" v-if="m.sub">{{ m.sub }}</div>
      </div>
    </div>

    <!-- ── Row 2: Model Routing + Context Monitor ── -->
    <div class="td__row2">
      <!-- Model Routing Map -->
      <div class="td__panel">
        <div class="td__panel-hd">
          <span class="td__panel-title">多模型路由</span>
          <span class="td__panel-badge">{{ Object.keys(modelInfo).length }} roles</span>
        </div>
        <div class="td__routes">
          <div
            v-for="(info, role) in modelInfo" :key="role"
            class="td__route"
            :class="{ 'td__route--active': modelBreakdown[info.model_name] }"
          >
            <div class="td__route-role">{{ roleLabels[role] || role }}</div>
            <div class="td__route-model">{{ shortModel(info.model_name) }}</div>
            <div class="td__route-stats" v-if="modelBreakdown[info.model_name]">
              <span>{{ modelBreakdown[info.model_name].calls }}x</span>
              <span>{{ formatTokens(modelBreakdown[info.model_name].tokens_in + modelBreakdown[info.model_name].tokens_out) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Context Budget Gauge -->
      <div class="td__panel">
        <div class="td__panel-hd">
          <span class="td__panel-title">上下文治理</span>
          <span class="td__panel-badge" :class="'td__panel-badge--' + ctxStatus">{{ ctxStatusLabel }}</span>
        </div>
        <div class="td__gauge-wrap">
          <svg class="td__gauge" viewBox="0 0 200 120">
            <!-- Track -->
            <path d="M 20 100 A 80 80 0 0 1 180 100" fill="none" stroke="var(--v2-border-2)" stroke-width="10" stroke-linecap="round"/>
            <!-- Value -->
            <path
              :d="gaugeArc"
              fill="none"
              :stroke="gaugeColor"
              stroke-width="10"
              stroke-linecap="round"
              class="td__gauge-bar"
            />
            <!-- Label -->
            <text x="100" y="85" text-anchor="middle" class="td__gauge-pct">{{ ctxPercent }}%</text>
            <text x="100" y="105" text-anchor="middle" class="td__gauge-label">Token 使用率</text>
          </svg>
          <div class="td__gauge-details">
            <div class="td__gauge-kv"><span>压缩次数</span><span>{{ summary.compactions }}</span></div>
            <div class="td__gauge-kv"><span>熔断计数</span><span>{{ ctxDiag.thrash_count || 0 }}/{{ ctxDiag.max_thrash || 3 }}</span></div>
            <div class="td__gauge-kv"><span>最大容量</span><span>{{ formatTokens(ctxDiag.max_tokens || 32000) }}</span></div>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Row 2.5: Component Breakdown ── -->
    <div class="td__panel td__panel--full" v-if="Object.keys(summary.component_breakdown).length">
      <div class="td__panel-hd">
        <span class="td__panel-title">组件事件分布</span>
        <span class="td__panel-badge">{{ Object.keys(summary.component_breakdown).length }} 组件</span>
      </div>
      <div class="td__comp-grid">
        <div v-for="(count, comp) in summary.component_breakdown" :key="comp" class="td__comp-item">
          <div class="td__comp-bar-wrap">
            <div class="td__comp-bar" :style="{ width: compPct(count) + '%' }"></div>
          </div>
          <span class="td__comp-name">{{ comp }}</span>
          <span class="td__comp-count">{{ count }}</span>
        </div>
      </div>
    </div>

    <!-- ── Row 2.7: Security Audit + Memory Activity ── -->
    <div class="td__row2">
      <!-- Security Audit Panel -->
      <div class="td__panel">
        <div class="td__panel-hd">
          <span class="td__panel-title">安全审计</span>
          <span class="td__panel-badge" :class="summary.security_blocks > 0 ? 'td__panel-badge--circuit_break' : 'td__panel-badge--healthy'">
            {{ summary.security_blocks > 0 ? '有拦截' : '全部通过' }}
          </span>
        </div>
        <div class="td__sec-grid">
          <div class="td__sec-stat">
            <span class="td__sec-num">{{ summary.security_checks || 0 }}</span>
            <span class="td__sec-label">安全检查</span>
          </div>
          <div class="td__sec-stat">
            <span class="td__sec-num td__sec-num--warn">{{ summary.security_blocks || 0 }}</span>
            <span class="td__sec-label">拦截次数</span>
          </div>
          <div class="td__sec-stat">
            <span class="td__sec-num td__sec-num--pii">{{ summary.pii_detections || 0 }}</span>
            <span class="td__sec-label">PII 检测</span>
          </div>
        </div>
        <div class="td__sec-hits" v-if="summary.security_hits?.length">
          <div v-for="(h, i) in summary.security_hits.slice(0, 5)" :key="i" class="td__sec-hit">
            <span class="td__sec-hit-rule">{{ h.rule || h.direction || '—' }}</span>
            <span class="td__sec-hit-count">{{ h.count || 1 }}x</span>
          </div>
        </div>
      </div>

      <!-- Memory Activity Panel -->
      <div class="td__panel">
        <div class="td__panel-hd">
          <span class="td__panel-title">记忆活动</span>
          <span class="td__panel-badge">{{ summary.memory_recalls + summary.memory_writes }} 操作</span>
        </div>
        <div class="td__mem-grid">
          <div class="td__mem-stat">
            <span class="td__mem-num">{{ summary.memory_recalls || 0 }}</span>
            <span class="td__mem-label">召回</span>
          </div>
          <div class="td__mem-stat">
            <span class="td__mem-num">{{ summary.memory_writes || 0 }}</span>
            <span class="td__mem-label">写入</span>
          </div>
        </div>
        <div class="td__mem-layers" v-if="Object.keys(summary.memory_layers || {}).length">
          <div v-for="(count, layer) in summary.memory_layers" :key="layer" class="td__mem-layer">
            <span class="td__mem-layer-name">{{ layerLabel(layer) }}</span>
            <div class="td__mem-layer-bar-wrap">
              <div class="td__mem-layer-bar" :style="{ width: memLayerPct(count) + '%' }"></div>
            </div>
            <span class="td__mem-layer-count">{{ count }}</span>
          </div>
        </div>
        <div v-else class="td__mem-empty">暂无记忆活动</div>
      </div>
    </div>

    <!-- ── Row 3: Event Stream ── -->
    <div class="td__panel td__panel--full">
      <div class="td__panel-hd">
        <span class="td__panel-title">遥测事件流</span>
        <div class="td__event-filters">
          <button
            v-for="f in eventFilters" :key="f.value"
            class="td__filter-btn"
            :class="{ 'td__filter-btn--active': activeFilter === f.value }"
            @click="activeFilter = f.value"
          >{{ f.label }}</button>
        </div>
        <span class="td__panel-badge">{{ summary.total_events }} total</span>
      </div>
      <div class="td__events" ref="eventsEl">
        <div
          v-for="(ev, idx) in filteredEvents" :key="idx"
          class="td__event"
          :class="'td__event--' + eventCategory(ev.type)"
        >
          <span class="td__event-time">{{ fmtTs(ev.timestamp) }}</span>
          <span class="td__event-type">{{ ev.type }}</span>
          <span class="td__event-comp">{{ ev.component }}</span>
          <span class="td__event-data">{{ eventSummary(ev) }}</span>
        </div>
        <div v-if="!filteredEvents.length" class="td__events-empty">暂无遥测事件</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import {
  fetchTelemetrySummary,
  fetchTelemetryEvents,
  fetchContextDiagnostics,
  fetchModelRouting,
} from '@/api/admin/telemetry'

// ── State ──
const summary = ref({
  total_events: 0, model_calls: 0, model_tokens_in: 0, model_tokens_out: 0,
  model_latency_ms: 0, skill_calls: 0, compactions: 0, errors: 0,
  hook_fires: 0, workflow_nodes: 0, duration_ms: 0,
  model_breakdown: {}, component_breakdown: {},
  security_checks: 0, security_blocks: 0, pii_detections: 0, security_hits: [],
  memory_recalls: 0, memory_writes: 0, memory_layers: {},
})
const events = ref([])
const modelInfo = ref({})
const ctxDiag = ref({ usage_percent: 0, status: 'healthy', thrash_count: 0, max_thrash: 3, max_tokens: 32000 })
const activeFilter = ref('all')

// ── Computed ──
const metricCards = computed(() => {
  const s = summary.value
  return [
    { key: 'model', label: 'LLM 调用', value: s.model_calls, display: s.model_calls, cls: '' },
    { key: 'tokens', label: 'Token 消耗', value: s.model_tokens_in + s.model_tokens_out, display: formatTokens(s.model_tokens_in + s.model_tokens_out), sub: `↑${formatTokens(s.model_tokens_in)} ↓${formatTokens(s.model_tokens_out)}` },
    { key: 'skills', label: 'Skill 执行', value: s.skill_calls, display: s.skill_calls, cls: '' },
    { key: 'latency', label: '模型延迟', value: s.model_latency_ms, display: s.model_calls ? `${Math.round(s.model_latency_ms / s.model_calls)}ms` : '—', sub: s.model_calls ? `共 ${s.model_calls} 次` : '' },
    { key: 'errors', label: '错误', value: s.errors, display: s.errors, cls: s.errors > 0 ? 'td__card-value--error' : '' },
    { key: 'compact', label: '压缩', value: s.compactions, display: s.compactions, cls: '' },
  ]
})

const modelBreakdown = computed(() => summary.value.model_breakdown || {})

const ctxPercent = computed(() => Math.round(ctxDiag.value.usage_percent || 0))
const ctxStatus = computed(() => ctxDiag.value.status || 'healthy')
const ctxStatusLabel = computed(() => {
  const m = { healthy: '健康', needs_compact: '需压缩', circuit_break: '已熔断' }
  return m[ctxStatus.value] || ctxStatus.value
})

const gaugeColor = computed(() => {
  const p = ctxPercent.value
  if (p >= 90) return '#ef4444'
  if (p >= 70) return '#f59e0b'
  return 'var(--v2-text-1)'
})

const gaugeArc = computed(() => {
  const pct = Math.min(ctxPercent.value, 100) / 100
  const startAngle = Math.PI
  const endAngle = startAngle + pct * Math.PI
  const cx = 100, cy = 100, r = 80
  const x1 = cx + r * Math.cos(startAngle)
  const y1 = cy + r * Math.sin(startAngle)
  const x2 = cx + r * Math.cos(endAngle)
  const y2 = cy + r * Math.sin(endAngle)
  const large = pct > 0.5 ? 1 : 0
  return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`
})

const eventFilters = [
  { label: '全部', value: 'all' },
  { label: '模型', value: 'model' },
  { label: 'Skill', value: 'skill' },
  { label: '安全', value: 'security' },
  { label: '记忆', value: 'memory' },
  { label: '错误', value: 'error' },
  { label: '压缩', value: 'compact' },
]

const filteredEvents = computed(() => {
  if (activeFilter.value === 'all') return events.value
  return events.value.filter(e => {
    if (activeFilter.value === 'model') return e.type.includes('model')
    if (activeFilter.value === 'skill') return e.type.includes('skill')
    if (activeFilter.value === 'security') return e.type.includes('security') || e.type.includes('pii')
    if (activeFilter.value === 'memory') return e.type.includes('memory')
    if (activeFilter.value === 'error') return e.type.includes('failed') || e.type.includes('error')
    if (activeFilter.value === 'compact') return e.type.includes('compact')
    return true
  })
})

// ── Labels ──
const roleLabels = { primary: '主模型', routing: '路由', compact: '压缩', review: '审查', exploration: '探索', embedding: '向量' }

// ── Helpers ──
function formatTokens(n) {
  if (!n) return '0'
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return String(n)
}

function shortModel(name) {
  if (!name) return '—'
  // Remove path prefixes and version suffixes for display
  const parts = name.split('/')
  let short = parts[parts.length - 1]
  if (short.length > 24) short = short.slice(0, 22) + '…'
  return short
}

function fmtTs(ts) {
  if (!ts) return '—'
  const d = new Date(ts * 1000)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
}

function eventCategory(type) {
  if (type.includes('failed') || type.includes('error')) return 'error'
  if (type.includes('security') || type.includes('pii')) return 'security'
  if (type.includes('memory')) return 'memory'
  if (type.includes('model')) return 'model'
  if (type.includes('skill')) return 'skill'
  if (type.includes('compact')) return 'compact'
  if (type.includes('workflow')) return 'workflow'
  return 'default'
}

function eventSummary(ev) {
  const d = ev.data || {}
  if (d.model) return `${d.model} ${d.role || ''} ${d.tokens_in ? `↑${d.tokens_in}` : ''} ${d.tokens_out ? `↓${d.tokens_out}` : ''} ${d.latency_ms ? `${d.latency_ms}ms` : ''}`.trim()
  if (d.skill) return d.skill
  if (d.status) return d.status
  const keys = Object.keys(d)
  return keys.length ? keys.slice(0, 3).map(k => `${k}=${JSON.stringify(d[k]).slice(0, 20)}`).join(' ') : ''
}

function compPct(count) {
  const max = Math.max(...Object.values(summary.value.component_breakdown || { _: 1 }))
  return Math.round((count / max) * 100)
}

const LAYER_LABELS = { L1_redis: 'L1 Redis 会话', L2_memory: 'L2 长期记忆', L3_rules: 'L3 静态规则' }
function layerLabel(l) { return LAYER_LABELS[l] || l }

function memLayerPct(count) {
  const vals = Object.values(summary.value.memory_layers || { _: 1 })
  const max = Math.max(...vals, 1)
  return Math.round((count / max) * 100)
}

// ── Data loading ──
let timer = null

async function load() {
  try {
    const [sumRes, evRes, modelRes, ctxRes] = await Promise.all([
      fetchTelemetrySummary(),
      fetchTelemetryEvents(100),
      fetchModelRouting(),
      fetchContextDiagnostics(),
    ])
    if (sumRes.ok) summary.value = sumRes.data
    if (evRes.ok) events.value = evRes.data.reverse()
    if (modelRes.ok) modelInfo.value = modelRes.data
    if (ctxRes.ok) ctxDiag.value = ctxRes.data
  } catch { /* ignore */ }
}

onMounted(() => {
  load()
  timer = setInterval(load, 5000) // Auto-refresh every 5s
})
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.td { display: flex; flex-direction: column; gap: 16px; }

/* ── Metric Cards ── */
.td__metrics { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; }
@media (max-width: 1200px) { .td__metrics { grid-template-columns: repeat(3, 1fr); } }
.td__card {
  background: var(--v2-bg-card); border: 1px solid var(--v2-border-2);
  border-radius: var(--v2-radius-lg); padding: 16px 18px;
  display: flex; flex-direction: column; gap: 4px;
}
.td__card-label { font-size: 11px; color: var(--v2-text-3); text-transform: uppercase; letter-spacing: 0.05em; }
.td__card-value { font-size: 28px; font-weight: 700; color: var(--v2-text-1); font-variant-numeric: tabular-nums; font-family: var(--v2-font-mono); }
.td__card-value--error { color: #ef4444; }
.td__card-sub { font-size: 11px; color: var(--v2-text-3); font-family: var(--v2-font-mono); }

/* ── Panels ── */
.td__row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@media (max-width: 900px) { .td__row2 { grid-template-columns: 1fr; } }
.td__panel {
  background: var(--v2-bg-card); border: 1px solid var(--v2-border-2);
  border-radius: var(--v2-radius-lg); padding: 16px 18px;
}
.td__panel--full { grid-column: 1 / -1; }
.td__panel-hd { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; }
.td__panel-title { font-size: var(--v2-text-md); font-weight: var(--v2-font-semibold); color: var(--v2-text-1); }
.td__panel-badge {
  font-size: 11px; padding: 1px 7px; border-radius: var(--v2-radius-sm);
  background: var(--v2-bg-sunken); color: var(--v2-text-3); font-family: var(--v2-font-mono);
}
.td__panel-badge--healthy { background: rgba(34,197,94,.1); color: #22c55e; }
.td__panel-badge--needs_compact { background: rgba(245,158,11,.1); color: #f59e0b; }
.td__panel-badge--circuit_break { background: rgba(239,68,68,.1); color: #ef4444; }

/* ── Model Routes ── */
.td__routes { display: flex; flex-direction: column; gap: 8px; }
.td__route {
  display: grid; grid-template-columns: 80px 1fr auto; gap: 8px; align-items: center;
  padding: 8px 12px; border-radius: var(--v2-radius-md);
  border: 1px solid var(--v2-border-2); transition: border-color 0.15s;
}
.td__route--active { border-color: var(--v2-text-1); }
.td__route-role { font-size: 11px; color: var(--v2-text-3); text-transform: uppercase; letter-spacing: 0.04em; }
.td__route-model { font-size: 13px; color: var(--v2-text-1); font-family: var(--v2-font-mono); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.td__route-stats { display: flex; gap: 8px; font-size: 11px; color: var(--v2-text-3); font-family: var(--v2-font-mono); }

/* ── Gauge ── */
.td__gauge-wrap { display: flex; gap: 20px; align-items: center; }
.td__gauge { width: 180px; height: 110px; flex-shrink: 0; }
.td__gauge-bar { transition: d 0.6s cubic-bezier(.4,0,.2,1), stroke 0.3s; }
.td__gauge-pct { font-size: 28px; font-weight: 700; fill: var(--v2-text-1); font-family: var(--v2-font-mono); }
.td__gauge-label { font-size: 11px; fill: var(--v2-text-3); }
.td__gauge-details { display: flex; flex-direction: column; gap: 8px; flex: 1; }
.td__gauge-kv { display: flex; justify-content: space-between; font-size: 12px; }
.td__gauge-kv span:first-child { color: var(--v2-text-3); }
.td__gauge-kv span:last-child { color: var(--v2-text-1); font-family: var(--v2-font-mono); }

/* ── Event Filters ── */
.td__event-filters { display: flex; gap: 4px; margin-left: auto; }
.td__filter-btn {
  font-size: 11px; padding: 2px 8px; border-radius: var(--v2-radius-sm);
  border: 1px solid var(--v2-border-2); background: transparent; color: var(--v2-text-3);
  cursor: pointer; transition: all 0.1s;
}
.td__filter-btn:hover { color: var(--v2-text-1); border-color: var(--v2-text-3); }
.td__filter-btn--active { background: var(--v2-text-1); color: var(--v2-bg-card); border-color: var(--v2-text-1); }

/* ── Event Stream ── */
.td__events { max-height: 320px; overflow-y: auto; display: flex; flex-direction: column; gap: 2px; }
.td__event {
  display: grid; grid-template-columns: 60px 180px 120px 1fr; gap: 8px;
  padding: 5px 8px; font-size: 12px; border-radius: var(--v2-radius-sm);
  font-family: var(--v2-font-mono); transition: background 0.1s;
}
.td__event:hover { background: var(--v2-bg-sunken); }
.td__event-time { color: var(--v2-text-3); }
.td__event-type { color: var(--v2-text-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.td__event-comp { color: var(--v2-text-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.td__event-data { color: var(--v2-text-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.td__event--error .td__event-type { color: #ef4444; }
.td__event--model .td__event-type { color: var(--v2-text-1); }
.td__event--compact .td__event-type { color: #f59e0b; }
.td__events-empty { padding: 24px; text-align: center; color: var(--v2-text-3); font-size: 13px; }

/* ── Component Breakdown ── */
.td__comp-grid { display: flex; flex-direction: column; gap: 6px; }
.td__comp-item { display: grid; grid-template-columns: 1fr 140px 50px; gap: 8px; align-items: center; font-size: 12px; }
.td__comp-bar-wrap { height: 6px; background: var(--v2-bg-sunken); border-radius: 3px; overflow: hidden; }
.td__comp-bar { height: 100%; background: var(--v2-text-1); border-radius: 3px; transition: width 0.4s cubic-bezier(.4,0,.2,1); }
.td__comp-name { color: var(--v2-text-2); font-family: var(--v2-font-mono); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.td__comp-count { color: var(--v2-text-1); font-family: var(--v2-font-mono); text-align: right; }

/* ── Security Audit Panel ── */
.td__sec-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 12px; }
.td__sec-stat { display: flex; flex-direction: column; align-items: center; gap: 2px; }
.td__sec-num { font-size: 24px; font-weight: 700; color: var(--v2-text-1); font-family: var(--v2-font-mono); }
.td__sec-num--warn { color: #f59e0b; }
.td__sec-num--pii { color: #8b5cf6; }
.td__sec-label { font-size: 11px; color: var(--v2-text-3); }
.td__sec-hits { display: flex; flex-direction: column; gap: 4px; }
.td__sec-hit {
  display: flex; justify-content: space-between; align-items: center;
  padding: 4px 8px; border-radius: var(--v2-radius-sm);
  background: var(--v2-bg-sunken); font-size: 12px;
}
.td__sec-hit-rule { color: var(--v2-text-2); font-family: var(--v2-font-mono); }
.td__sec-hit-count { color: var(--v2-text-3); font-family: var(--v2-font-mono); }

/* ── Memory Activity Panel ── */
.td__mem-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 12px; }
.td__mem-stat { display: flex; flex-direction: column; align-items: center; gap: 2px; }
.td__mem-num { font-size: 24px; font-weight: 700; color: var(--v2-text-1); font-family: var(--v2-font-mono); }
.td__mem-label { font-size: 11px; color: var(--v2-text-3); }
.td__mem-layers { display: flex; flex-direction: column; gap: 6px; }
.td__mem-layer { display: grid; grid-template-columns: 110px 1fr 40px; gap: 8px; align-items: center; font-size: 12px; }
.td__mem-layer-name { color: var(--v2-text-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.td__mem-layer-bar-wrap { height: 6px; background: var(--v2-bg-sunken); border-radius: 3px; overflow: hidden; }
.td__mem-layer-bar { height: 100%; background: #8b5cf6; border-radius: 3px; transition: width 0.4s cubic-bezier(.4,0,.2,1); }
.td__mem-layer-count { color: var(--v2-text-1); font-family: var(--v2-font-mono); text-align: right; }
.td__mem-empty { padding: 16px; text-align: center; color: var(--v2-text-3); font-size: 12px; }

/* ── Event Stream extras ── */
.td__event--security .td__event-type { color: #8b5cf6; }
.td__event--memory .td__event-type { color: #8b5cf6; }
</style>
