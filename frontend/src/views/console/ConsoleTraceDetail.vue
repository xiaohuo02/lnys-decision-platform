<template>
  <div class="ctd">
    <div class="ctd-hd">
      <div class="ctd-hd__left">
        <button class="v2-btn v2-btn--ghost" @click="$router.back()">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
        </button>
        <div class="ctd-hd__titles">
          <div class="ctd-hd__id v2-mono">追踪-{{ id.substring(0,8) }}</div>
          <h2 class="ctd-hd__name">{{ wfLabel(traceData.workflow) }}</h2>
        </div>
        <span class="v2-badge" :class="statusBadgeClass">{{ statusLabel(traceData.status) }}</span>
      </div>
      <div class="ctd-hd__right">
        <div class="ctd-meta-item">
          <span class="ctd-meta-label">延迟</span>
          <span class="ctd-meta-val v2-mono">{{ traceData.latency ? fmtDuration(traceData.latency) : '-' }}</span>
        </div>
        <div class="ctd-meta-item">
          <span class="ctd-meta-label">令牌数</span>
          <span class="ctd-meta-val v2-mono">{{ fmtTokens(traceData.total_tokens) || '无' }}</span>
        </div>
        <div class="ctd-meta-item">
          <span class="ctd-meta-label">成本</span>
          <span class="ctd-meta-val v2-mono">{{ traceData.total_cost ? '¥' + Number(traceData.total_cost).toFixed(4) : '无' }}</span>
        </div>
      </div>
    </div>

    <!-- ── The Waterfall Viewer ── -->
    <div class="ctd-layout">
      <!-- Left: Step Tree / Flame Graph -->
      <div class="ctd-waterfall v2-hairline-card">
        <div class="ctd-waterfall__hd">
          <h3 class="ctd-panel-title">执行瀑布图</h3>
        </div>
        <div class="ctd-waterfall__bd" v-loading="loading">
          <div class="wf-empty" v-if="!steps.length">暂无执行步骤记录。</div>
          
          <div class="wf-tree" v-else>
            <!-- Timeline Header (Mocked Scale) -->
            <div class="wf-axis">
              <span class="v2-mono-meta">0</span>
              <span class="v2-mono-meta">{{ traceData.latency ? fmtDuration(Math.round(traceData.latency / 2)) : '...' }}</span>
              <span class="v2-mono-meta">{{ traceData.latency ? fmtDuration(traceData.latency) : '...' }}</span>
            </div>

            <!-- Steps -->
            <div 
              v-for="step in steps" :key="step.id"
              class="wf-row"
              :class="{ 'is-selected': selectedStep?.id === step.id, 'is-error': step.status === 'failed' }"
              @click="selectedStep = step"
            >
              <div class="wf-row__info" :style="{ paddingLeft: (step.depth * 20 + 12) + 'px' }">
                <span class="wf-icon" :class="getStepIconColor(step.type)" v-html="getStepIconSvg(step.type)"></span>
                <span class="wf-name v2-truncate" :title="step.name">{{ step.name }}</span>
              </div>
              <div class="wf-row__bar-area">
                <!-- Flame Graph Bar -->
                <div 
                  class="wf-bar"
                  :class="`wf-bar--${step.status}`"
                  :style="{
                    left: getBarLeft(step) + '%',
                    width: getBarWidth(step) + '%'
                  }"
                ></div>
                <!-- Inline Meta -->
                <span class="wf-bar-meta v2-mono" :style="{ left: `calc(${getBarLeft(step) + getBarWidth(step)}% + 8px)` }">
                  {{ step.latency ? fmtDuration(step.latency) : '-' }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Right: Inspector Drawer (FLIP animation concept) -->
      <div class="ctd-inspector v2-hairline-card" v-if="selectedStep">
        <div class="ctd-inspector__hd">
          <h3 class="ctd-panel-title v2-truncate">{{ selectedStep.name }}</h3>
          <button class="v2-btn v2-btn--ghost ctd-close-btn" @click="selectedStep = null">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>
          </button>
        </div>
        
        <div class="ctd-inspector__bd">
          <div class="ctd-prop">
            <label class="v2-mono-meta">类型</label>
            <span class="v2-badge v2-badge--gray">{{ stepTypeLabel(selectedStep.type) }}</span>
          </div>
          
          <div class="ctd-prop" v-if="selectedStep.status === 'failed' && selectedStep.error_message">
            <label class="v2-mono-meta" style="color: var(--v2-error);">错误追踪</label>
            <pre class="ctd-code is-error">{{ selectedStep.error_message }}</pre>
          </div>

          <div class="ctd-prop">
            <label class="v2-mono-meta">输入</label>
            <pre class="ctd-code">{{ formatJson(selectedStep.input_payload) }}</pre>
          </div>

          <div class="ctd-prop">
            <label class="v2-mono-meta">输出</label>
            <pre class="ctd-code">{{ formatJson(selectedStep.output_payload) }}</pre>
          </div>

          <div class="ctd-prop" v-if="selectedStep.agent_name">
            <label class="v2-mono-meta">智能体</label>
            <span class="ctd-val">{{ selectedStep.agent_name }}</span>
          </div>
          <div class="ctd-prop" v-if="selectedStep.tool_name">
            <label class="v2-mono-meta">工具</label>
            <span class="ctd-val">{{ selectedStep.tool_name }}</span>
          </div>
          <div class="ctd-prop" v-if="selectedStep.latency">
            <label class="v2-mono-meta">耗时</label>
            <span class="ctd-val">{{ fmtDuration(selectedStep.latency) }}</span>
          </div>
          <div class="ctd-prop" v-if="selectedStep.tokens">
            <label class="v2-mono-meta">词元数</label>
            <span class="ctd-val">{{ fmtTokens(selectedStep.tokens) || '无' }}</span>
          </div>
          <div class="ctd-prop" v-if="selectedStep.cost">
            <label class="v2-mono-meta">成本</label>
            <span class="ctd-val">¥{{ Number(selectedStep.cost).toFixed(4) }}</span>
          </div>
        </div>
      </div>
      
      <!-- Placeholder when no step selected -->
      <div class="ctd-inspector v2-hairline-card is-empty" v-else>
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" style="color:var(--v2-text-4)"><path d="M9 9l5 12 1.774-5.226L21 14 9 9z"/><path d="M16.071 16.071l4.243 4.243"/></svg>
        <p>点击瀑布图中的步骤查看详细载荷和指标。</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { tracesApi } from '@/api/admin/traces'

const route = useRoute()
const id = ref(route.params.runId || route.params.id || '')
const loading = ref(false)
const traceData = ref({})
const steps = ref([])
const selectedStep = ref(null)

const STATUS_LABELS = { completed: '已完成', failed: '失败', running: '运行中', pending: '等待中', cancelled: '已取消', timeout: '超时', paused: '已暂停' }
function statusLabel(s) { return STATUS_LABELS[s] || s || '未知' }

const WORKFLOW_MAP = {
  business_overview: '经营总览', risk_review: '风控审核', openclaw: '数据抓取',
  patrol_ops: '运维巡检', patrol_biz: '业务巡检', memory_reconciliation: '记忆整理',
  ops_copilot: '运维诊断',
}
function wfLabel(wf) { return WORKFLOW_MAP[wf] || wf || '-' }

const STEP_TYPE_LABELS = { llm_call: 'LLM 调用', tool_call: '工具调用', service_call: '服务调用', agent_call: '智能体调用', guardrail_check: '护栏检查' }
function stepTypeLabel(t) { return STEP_TYPE_LABELS[t] || t }

const statusBadgeClass = computed(() => {
  if (traceData.value.status === 'completed') return 'v2-badge--success'
  if (traceData.value.status === 'failed') return 'v2-badge--error'
  if (traceData.value.status === 'running') return 'v2-badge--purple'
  return 'v2-badge--gray'
})

function getStepIconSvg(type) {
  const a = 'width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"'
  if (type === 'llm_call') return `<svg ${a}><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M9 9h6M9 13h6M9 17h4"/></svg>`
  if (type === 'tool_call') return `<svg ${a}><path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/></svg>`
  if (type === 'service_call') return `<svg ${a}><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>`
  if (type === 'agent_call') return `<svg ${a}><path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/></svg>`
  return `<svg ${a}><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>`
}

function getStepIconColor(type) {
  if (type === 'llm_call') return 'color-purple'
  if (type === 'tool_call') return 'color-blue'
  return 'color-gray'
}

function formatJson(obj) {
  if (!obj) return '{}'
  if (typeof obj === 'string') return obj
  try { return JSON.stringify(obj, null, 2) } catch { return String(obj) }
}

function fmtTokens(n) {
  if (n == null || n === 0) return ''
  if (n >= 10000) return (n / 10000).toFixed(1) + '万'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}

function fmtDuration(ms) {
  if (ms == null) return '-'
  if (ms < 1000) return ms + 'ms'
  return (ms / 1000).toFixed(2) + 's'
}

// Waterfall Logic — uses real timestamps
function getBarLeft(step) {
  const totalMs = traceData.value.latency
  if (!totalMs || step.start_time == null) return 0
  return Math.min(Math.max((step.start_time / totalMs) * 100, 0), 100)
}

function getBarWidth(step) {
  const totalMs = traceData.value.latency
  if (!totalMs || !step.latency) return 2
  return Math.max((step.latency / totalMs) * 100, 0.5)
}

// Fetch real data from backend
onMounted(async () => {
  if (!id.value) return
  loading.value = true
  try {
    const data = await tracesApi.getDetail(id.value)
    if (!data) return

    const run = data.run || {}
    const latMs = run.latency_ms || 0
    traceData.value = {
      id: run.run_id || id.value,
      workflow: run.workflow_name || '-',
      status: run.status || 'unknown',
      latency: latMs,
      total_tokens: run.total_tokens || 0,
      total_cost: run.total_cost || 0,
      input_summary: run.input_summary,
      output_summary: run.output_summary,
      error_message: run.error_message,
      triggered_by: run.triggered_by,
    }

    const rawSteps = data.steps || []
    const runStart = run.started_at ? new Date(run.started_at).getTime() : null

    steps.value = rawSteps.map((s, idx) => {
      const sa = s.started_at ? new Date(s.started_at).getTime() : null
      const ea = s.ended_at ? new Date(s.ended_at).getTime() : null
      const stepLatMs = s.latency_ms || (sa && ea ? ea - sa : 0)
      const startOffset = (runStart && sa) ? Math.max(0, sa - runStart) : 0
      const tu = s.token_usage || {}
      return {
        id: s.step_id || ('step-' + idx),
        depth: 0,
        name: s.step_name || s.agent_name || s.tool_name || ('-'),
        type: s.step_type || 'unknown',
        status: s.status || 'completed',
        latency: stepLatMs,
        start_time: startOffset,
        tokens: tu.total_tokens || 0,
        input_payload: s.input_summary,
        output_payload: s.output_summary,
        error_message: s.error_message,
        cost: s.cost_amount || 0,
        agent_name: s.agent_name,
        tool_name: s.tool_name,
        model_name: s.model_name,
      }
    })
  } catch (e) {
    console.error('[TraceDetail] load failed:', e)
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.ctd {
  display: flex;
  flex-direction: column;
  height: calc(100vh - var(--v2-header-height) - var(--v2-space-6) * 2);
  gap: var(--v2-space-4);
  max-width: var(--v2-layout-max-width);
  margin: 0 auto;
}

/* ── Header ── */
.ctd-hd {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  padding-bottom: var(--v2-space-4);
  border-bottom: var(--v2-border-width) solid var(--v2-border-2);
  flex-shrink: 0;
}
.ctd-hd__left {
  display: flex;
  align-items: center;
  gap: var(--v2-space-4);
}
.ctd-hd__titles {
  display: flex;
  flex-direction: column;
}
.ctd-hd__id {
  font-size: 11px;
  color: var(--v2-text-3);
  margin-bottom: 2px;
}
.ctd-hd__name {
  font-size: 18px;
  font-weight: 600;
  margin: 0;
  color: var(--v2-text-1);
}

.ctd-hd__right {
  display: flex;
  gap: var(--v2-space-6);
}
.ctd-meta-item {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}
.ctd-meta-label {
  font-size: 11px;
  color: var(--v2-text-3);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.ctd-meta-val {
  font-size: 18px;
  font-weight: 500;
  color: var(--v2-text-1);
}

/* ── Layout ── */
.ctd-layout {
  flex: 1;
  display: flex;
  gap: var(--v2-space-4);
  min-height: 0;
}

/* ── Waterfall Graph ── */
.ctd-waterfall {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--v2-bg-card);
  min-width: 0;
}
.ctd-waterfall__hd {
  padding: 12px 16px;
  border-bottom: var(--v2-border-width) solid var(--v2-border-2);
}
.ctd-panel-title {
  font-size: 13px;
  font-weight: 600;
  margin: 0;
  color: var(--v2-text-1);
}
.ctd-waterfall__bd {
  flex: 1;
  overflow-y: auto;
  position: relative;
}
.wf-empty {
  padding: 40px;
  text-align: center;
  color: var(--v2-text-3);
  font-size: 13px;
}
.wf-tree {
  display: flex;
  flex-direction: column;
  min-width: 600px;
}
.wf-axis {
  display: flex;
  justify-content: space-between;
  padding: 4px 16px 4px 240px; /* Offset for the info column */
  border-bottom: var(--v2-border-width) solid var(--v2-border-2);
  background: var(--v2-bg-hover);
  position: sticky;
  top: 0;
  z-index: 10;
}

.wf-row {
  display: flex;
  align-items: center;
  height: 36px;
  border-bottom: var(--v2-border-width) solid var(--v2-border-2);
  cursor: pointer;
  transition: background var(--v2-trans-fast);
}
.wf-row:hover { background: var(--v2-bg-hover); }
.wf-row.is-selected { background: var(--v2-bg-active); }
.wf-row.is-error { background: var(--v2-error-bg); }

.wf-row__info {
  width: 240px; /* Fixed width for names */
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  border-right: var(--v2-border-width) solid var(--v2-border-2);
  height: 100%;
}
.wf-icon { font-size: 14px; }
.color-purple { color: #a855f7; }
.color-blue { color: #3b82f6; }
.color-gray { color: var(--v2-text-3); }

.wf-name {
  font-size: 12px;
  font-family: var(--v2-font-mono);
  color: var(--v2-text-2);
}
.wf-row.is-selected .wf-name { color: var(--v2-text-1); font-weight: 600; }

.wf-row__bar-area {
  flex: 1;
  position: relative;
  height: 100%;
  /* Guide lines could be added as background repeating-linear-gradient */
}
.wf-bar {
  position: absolute;
  top: 10px;
  height: 16px;
  border-radius: 2px;
  background: var(--v2-text-3);
  transition: var(--v2-trans-spring);
}
.wf-bar--completed { background: var(--v2-text-2); }
.wf-bar--failed { background: var(--v2-error); }
.wf-row.is-selected .wf-bar { background: var(--v2-text-1); }
.wf-bar-meta {
  position: absolute;
  top: 10px;
  font-size: 10px;
  color: var(--v2-text-3);
  pointer-events: none;
  white-space: nowrap;
}

/* ── Inspector Drawer ── */
.ctd-inspector {
  width: 380px;
  display: flex;
  flex-direction: column;
  background: var(--v2-bg-card);
  transition: var(--v2-trans-spring);
}
.ctd-inspector.is-empty {
  align-items: center;
  justify-content: center;
  color: var(--v2-text-4);
  gap: 16px;
  text-align: center;
  padding: 32px;
}
.ctd-inspector__hd {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: var(--v2-border-width) solid var(--v2-border-2);
}
.ctd-close-btn { width: 28px; height: 28px; padding: 0; display: flex; align-items: center; justify-content: center; }

.ctd-inspector__bd {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: var(--v2-space-5);
}

.ctd-prop {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ctd-code {
  margin: 0;
  padding: 12px;
  background: var(--v2-bg-sunken, #121212);
  border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-btn);
  font-family: var(--v2-font-mono);
  font-size: 11px;
  color: #e7e9ea;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 240px;
  overflow-y: auto;
}
.ctd-code.is-error {
  background: var(--v2-error-bg);
  border-color: var(--v2-error);
  color: var(--v2-error);
}
.ctd-val {
  font-size: 14px;
  color: var(--v2-text-1);
}
</style>
