<template>
  <div class="ch">
    <div class="ch__header">
      <h2 class="ch__title">系统健康</h2>
      <div class="ch__header-right">
        <div class="ch__tabs">
          <button class="ch__tab" :class="{ 'ch__tab--active': tab === 'health' }" @click="tab = 'health'">基础设施</button>
          <button class="ch__tab" :class="{ 'ch__tab--active': tab === 'telemetry' }" @click="tab = 'telemetry'">
            遥测仪表盘
            <span class="ch__tab-dot"></span>
          </button>
        </div>
        <V2Badge :variant="overallOk ? 'success' : 'error'" :label="overallOk ? '系统正常' : '系统异常'" />
        <V2Button variant="ghost" size="sm" :loading="loading" @click="refresh">刷新</V2Button>
      </div>
    </div>

    <!-- Telemetry Dashboard Tab -->
    <TelemetryDashboard v-if="tab === 'telemetry'" />

    <!-- Original Health Tab -->
    <template v-if="tab === 'health'">
    <!-- 基础设施状态 -->
    <div class="ch__sec-title">基础设施</div>
    <div class="ch__grid">
      <div v-for="svc in services" :key="svc.name" class="ch__card">
        <div class="ch__card-top">
          <span class="ch__svc-name">{{ svc.name }}</span>
          <V2Badge :variant="svc.ok ? 'success' : 'error'" :label="svc.ok ? '正常' : '异常'" />
        </div>
        <div class="ch__kv">
          <div class="ch__kv-row"><span class="ch__kv-k">响应延迟</span><span class="ch__kv-v">{{ svc.latency }}</span></div>
          <div class="ch__kv-row"><span class="ch__kv-k">检查时间</span><span class="ch__kv-v">{{ svc.checked }}</span></div>
        </div>
      </div>
    </div>

    <!-- Agent 状态 -->
    <div class="ch__sec-title">Agent 状态 <span class="ch__sec-badge">{{ agents.length }}</span></div>
    <div class="ch__grid">
      <div v-for="a in agents" :key="a.name" class="ch__card ch__card--sm">
        <div class="ch__card-top">
          <span class="ch__svc-name">{{ a.label }}</span>
          <V2Badge :variant="a.ok ? 'success' : 'error'" :label="a.ok ? '就绪' : '离线'" />
        </div>
        <div class="ch__kv">
          <div class="ch__kv-row"><span class="ch__kv-k">标识</span><span class="ch__kv-v ch__mono">{{ a.name }}</span></div>
        </div>
      </div>
    </div>

    <!-- 模型状态 -->
    <div class="ch__sec-title">模型状态 <span class="ch__sec-badge">{{ models.length }}</span></div>
    <div class="ch__grid">
      <div v-for="m in models" :key="m.name" class="ch__card ch__card--sm">
        <div class="ch__card-top">
          <span class="ch__svc-name">{{ m.label }}</span>
          <V2Badge :variant="m.ok ? 'success' : 'error'" :label="m.ok ? '已加载' : '缺失'" />
        </div>
        <div class="ch__kv">
          <div class="ch__kv-row"><span class="ch__kv-k">标识</span><span class="ch__kv-v ch__mono">{{ m.name }}</span></div>
        </div>
      </div>
    </div>

    <!-- 环境信息 -->
    <div class="ch__sec-title">运行环境</div>
    <div class="ch__env">
      <div class="ch__env-item"><span class="ch__kv-k">环境</span><span class="ch__kv-v">{{ envLabel(envInfo.env) }}</span></div>
      <div class="ch__env-item"><span class="ch__kv-k">总体状态</span><span class="ch__kv-v">{{ envInfo.status === 'ok' ? '正常运行' : envInfo.status }}</span></div>
      <div class="ch__env-item"><span class="ch__kv-k">模拟数据</span><span class="ch__kv-v">{{ envInfo.mockData ? '已开启' : '已关闭' }}</span></div>
    </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'
import V2Badge from '@/components/v2/V2Badge.vue'
import V2Button from '@/components/v2/V2Button.vue'
import TelemetryDashboard from '@/components/telemetry/TelemetryDashboard.vue'

const tab = ref('health')
const loading = ref(false)

const services = ref([
  { name: 'API 服务',   ok: false, latency: '—', checked: '—' },
  { name: 'MySQL',      ok: false, latency: '—', checked: '—' },
  { name: 'Redis',      ok: false, latency: '—', checked: '—' },
  { name: 'PostgreSQL', ok: false, latency: '—', checked: '—' },
])
const agents = ref([])
const models = ref([])
const envInfo = ref({ env: '', status: '', mockData: false })

const overallOk = computed(() => services.value.every(s => s.ok))

const AGENT_LABELS = {
  customer_agent: '客户分析 Agent', forecast_agent: '销售预测 Agent',
  fraud_agent: '欺诈风控 Agent', sentiment_agent: '舆情分析 Agent',
  inventory_agent: '库存优化 Agent', openclaw_agent: 'OpenClaw 客服 Agent',
  association_agent: '关联分析 Agent', data_agent: '数据感知 Agent',
}
const MODEL_LABELS = {
  churn_xgb: '流失预测 XGBoost', fraud_lgb: '欺诈检测 LightGBM',
  iso_forest: '异常检测 IsoForest', bert: '情感分析 BERT',
  lda: '主题模型 LDA', sarima: '时序预测 SARIMA', stacking: '融合预测 Stacking',
}
const ENV_LABELS = { development: '开发环境', production: '生产环境', staging: '预发布环境' }
function envLabel(v) { return ENV_LABELS[v] || v || '—' }

function fmtTime() {
  const d = new Date()
  return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}:${String(d.getSeconds()).padStart(2,'0')}`
}

async function refresh() {
  loading.value = true
  const now = fmtTime()
  try {
    const start = Date.now()
    const res = await axios.get('/api/health', { timeout: 5000 })
    const ms = Date.now() - start
    const d = (res.data || {}).data || {}

    const lat = d.latency_ms || {}
    services.value = [
      { name: 'API 服务',   ok: d.status === 'ok' || d.status === 'degraded', latency: `${ms}ms`, checked: now },
      { name: 'MySQL',      ok: d.db === 'ok',    latency: lat.db != null ? `${lat.db}ms` : '—', checked: now },
      { name: 'Redis',      ok: d.redis === 'ok', latency: lat.redis != null ? `${lat.redis}ms` : '—', checked: now },
      { name: 'PostgreSQL', ok: d.pg === 'ok',    latency: lat.pg != null ? `${lat.pg}ms` : '—', checked: now },
    ]

    if (d.agents) {
      agents.value = Object.entries(d.agents).map(([k, v]) => ({
        name: k, label: AGENT_LABELS[k] || k, ok: v === 'ready',
      }))
    }
    if (d.models) {
      models.value = Object.entries(d.models).map(([k, v]) => ({
        name: k, label: MODEL_LABELS[k] || k, ok: v === 'ok',
      }))
    }
    envInfo.value = { env: d.env || '', status: d.status || '', mockData: false }

    // 获取 deps 信息中的 mock_data_enabled
    try {
      const depsRes = await axios.get('/api/health/deps', { timeout: 3000 })
      const dd = (depsRes.data || {}).data || {}
      if (dd.mock_data_enabled != null) envInfo.value.mockData = dd.mock_data_enabled
    } catch { /* ignore */ }
  } catch {
    services.value = services.value.map(s => ({ ...s, ok: false, checked: now }))
  } finally { loading.value = false }
}

onMounted(refresh)
</script>

<style scoped>
.ch__header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.ch__header-right { display: flex; align-items: center; gap: 10px; }
.ch__title { font-size: var(--v2-text-lg); font-weight: var(--v2-font-semibold); color: var(--v2-text-1); margin: 0; }
.ch__sec-title {
  font-size: var(--v2-text-md); font-weight: var(--v2-font-semibold); color: var(--v2-text-1);
  margin: 18px 0 10px; display: flex; align-items: center; gap: 6px;
}
.ch__sec-badge {
  font-size: 11px; padding: 0 6px; background: var(--v2-bg-sunken); color: var(--v2-text-3);
  border-radius: var(--v2-radius-sm);
}
.ch__grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }
.ch__card { background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-lg); padding: 16px; }
.ch__card--sm { padding: 12px; }
.ch__card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.ch__svc-name { font-size: var(--v2-text-md); font-weight: var(--v2-font-semibold); color: var(--v2-text-1); }
.ch__kv { display: flex; flex-direction: column; gap: 5px; }
.ch__kv-row { display: flex; justify-content: space-between; font-size: 12px; }
.ch__kv-k { color: var(--v2-text-3); }
.ch__kv-v { color: var(--v2-text-1); }
.ch__mono { font-family: var(--v2-font-mono); font-size: 11px; }
.ch__env {
  display: flex; gap: 24px; padding: 14px 18px;
  background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-lg);
}
.ch__env-item { display: flex; gap: 8px; font-size: 13px; }
/* Tab switcher */
.ch__tabs { display: flex; gap: 2px; background: var(--v2-bg-sunken); border-radius: var(--v2-radius-md); padding: 2px; }
.ch__tab {
  font-size: 12px; padding: 4px 12px; border-radius: var(--v2-radius-sm); border: none;
  background: transparent; color: var(--v2-text-3); cursor: pointer; position: relative;
  display: flex; align-items: center; gap: 4px; transition: all 0.15s;
}
.ch__tab:hover { color: var(--v2-text-1); }
.ch__tab--active { background: var(--v2-bg-card); color: var(--v2-text-1); font-weight: var(--v2-font-semibold); box-shadow: 0 1px 2px rgba(0,0,0,.06); }
.ch__tab-dot { width: 5px; height: 5px; border-radius: 50%; background: #22c55e; animation: ch-pulse 2s infinite; }
@keyframes ch-pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }
</style>
