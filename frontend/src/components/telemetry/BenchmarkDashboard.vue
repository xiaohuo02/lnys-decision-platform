<template>
  <div class="bm">
    <!-- ── Row 1: Overview KPIs ── -->
    <div class="bm__kpis">
      <div class="bm__kpi" v-for="kpi in overviewCards" :key="kpi.label">
        <div class="bm__kpi-value" :class="kpi.cls">{{ kpi.value }}</div>
        <div class="bm__kpi-label">{{ kpi.label }}</div>
      </div>
    </div>

    <!-- ── Row 2: Agent Leaderboard + Pass Rate Gauge ── -->
    <div class="bm__row2">
      <div class="bm__panel">
        <div class="bm__panel-hd">
          <span class="bm__panel-title">Agent 排行榜</span>
          <span class="bm__panel-badge">pass_rate 降序</span>
        </div>
        <div class="bm__table-wrap" v-if="agents.length">
          <table class="bm__table">
            <thead>
              <tr>
                <th>#</th>
                <th>Agent</th>
                <th>实验数</th>
                <th>用例数</th>
                <th>平均通过率</th>
                <th>最佳通过率</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(a, i) in agents" :key="a.agent">
                <td class="bm__rank">{{ i + 1 }}</td>
                <td class="bm__mono">{{ a.agent || '—' }}</td>
                <td>{{ a.experiments }}</td>
                <td>{{ a.total_cases }}</td>
                <td>
                  <span class="bm__rate" :class="rateClass(a.avg_pass_rate)">
                    {{ fmtRate(a.avg_pass_rate) }}
                  </span>
                </td>
                <td>
                  <span class="bm__rate" :class="rateClass(a.best_pass_rate)">
                    {{ fmtRate(a.best_pass_rate) }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="bm__empty">暂无已完成的评测实验</div>
      </div>

      <!-- Pass Rate Gauge -->
      <div class="bm__panel">
        <div class="bm__panel-hd">
          <span class="bm__panel-title">综合通过率</span>
        </div>
        <div class="bm__gauge-wrap">
          <svg class="bm__gauge" viewBox="0 0 200 120">
            <path d="M20,100 A80,80 0 0,1 180,100" fill="none" stroke="var(--v2-border-2)" stroke-width="14" stroke-linecap="round" />
            <path d="M20,100 A80,80 0 0,1 180,100" fill="none" :stroke="gaugeColor" stroke-width="14" stroke-linecap="round"
              :stroke-dasharray="gaugeDash" class="bm__gauge-fill" />
            <text x="100" y="88" text-anchor="middle" class="bm__gauge-pct">
              {{ overview.avg_pass_rate != null ? (overview.avg_pass_rate * 100).toFixed(1) : '—' }}%
            </text>
            <text x="100" y="108" text-anchor="middle" class="bm__gauge-label">平均通过率</text>
          </svg>
        </div>

        <!-- Mini Telemetry -->
        <div class="bm__mini-stats" v-if="telemetry.total_model_calls">
          <div class="bm__mini-stat">
            <span class="bm__mini-label">模型调用</span>
            <span class="bm__mono">{{ telemetry.total_model_calls }}</span>
          </div>
          <div class="bm__mini-stat">
            <span class="bm__mini-label">Skill 执行</span>
            <span class="bm__mono">{{ telemetry.total_skill_executions }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Row 3: Recent Trend ── -->
    <div class="bm__panel bm__panel--full">
      <div class="bm__panel-hd">
        <span class="bm__panel-title">最近实验趋势</span>
        <span class="bm__panel-badge">{{ trend.length }} 条</span>
      </div>
      <div class="bm__trend" v-if="trend.length">
        <div class="bm__trend-row" v-for="t in trend" :key="t.experiment_id">
          <span class="bm__trend-name">{{ t.name }}</span>
          <span class="bm__trend-agent bm__mono">{{ t.agent || '—' }}</span>
          <span class="bm__trend-cases">{{ t.total_cases }}例</span>
          <span class="bm__rate" :class="rateClass(t.pass_rate)">{{ fmtRate(t.pass_rate) }}</span>
          <span :class="['bm__trend-status', 'bm__trend-status--' + t.status]">{{ t.status }}</span>
        </div>
      </div>
      <div v-else class="bm__empty">暂无实验数据</div>
    </div>

    <!-- ── Row 4: Evaluators + Datasets ── -->
    <div class="bm__row2">
      <div class="bm__panel">
        <div class="bm__panel-hd">
          <span class="bm__panel-title">评测器</span>
        </div>
        <div class="bm__list" v-if="evaluators.length">
          <div class="bm__list-row" v-for="e in evaluators" :key="e.name">
            <span class="bm__list-name">{{ e.name }}</span>
            <span class="bm__list-type">{{ e.task_type }}</span>
            <span class="bm__mono">{{ e.usage_count }}次</span>
          </div>
        </div>
        <div v-else class="bm__empty">暂无评测器</div>
      </div>
      <div class="bm__panel">
        <div class="bm__panel-hd">
          <span class="bm__panel-title">数据集</span>
        </div>
        <div class="bm__list" v-if="datasets.length">
          <div class="bm__list-row" v-for="d in datasets" :key="d.name">
            <span class="bm__list-name">{{ d.name }}</span>
            <span class="bm__list-type">{{ d.task_type }} · {{ d.item_count }}条</span>
            <span class="bm__mono">{{ d.experiment_count }}次</span>
          </div>
        </div>
        <div v-else class="bm__empty">暂无数据集</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { fetchBenchmarkSummary } from '@/api/admin/benchmark'

const overview = ref({ total: 0, running: 0, completed: 0, failed: 0, avg_pass_rate: null, total_cases: 0 })
const agents = ref([])
const trend = ref([])
const evaluators = ref([])
const datasets = ref([])
const telemetry = ref({})

const overviewCards = computed(() => {
  const o = overview.value
  return [
    { label: '总实验', value: o.total || 0, cls: '' },
    { label: '已完成', value: o.completed || 0, cls: '' },
    { label: '运行中', value: o.running || 0, cls: o.running ? 'bm__kpi-value--active' : '' },
    { label: '失败', value: o.failed || 0, cls: o.failed ? 'bm__kpi-value--error' : '' },
    { label: '总用例', value: o.total_cases || 0, cls: '' },
    { label: '平均通过率', value: fmtRate(o.avg_pass_rate), cls: rateClass(o.avg_pass_rate) },
  ]
})

const gaugeColor = computed(() => {
  const r = overview.value.avg_pass_rate
  if (r == null) return 'var(--v2-border-2)'
  if (r >= 0.8) return '#22c55e'
  if (r >= 0.6) return '#f59e0b'
  return '#ef4444'
})

const gaugeDash = computed(() => {
  const arcLen = Math.PI * 80  // half circle r=80
  const r = overview.value.avg_pass_rate || 0
  const fill = r * arcLen
  return `${fill} ${arcLen - fill}`
})

function fmtRate(v) {
  if (v == null) return '—'
  return (v * 100).toFixed(1) + '%'
}

function rateClass(v) {
  if (v == null) return ''
  if (v >= 0.8) return 'bm__rate--good'
  if (v >= 0.6) return 'bm__rate--mid'
  return 'bm__rate--bad'
}

async function load() {
  try {
    const res = await fetchBenchmarkSummary()
    if (res.ok && res.data) {
      overview.value = res.data.overview || overview.value
      agents.value = res.data.agents || []
      trend.value = res.data.trend || []
      evaluators.value = res.data.evaluators || []
      datasets.value = res.data.datasets || []
      telemetry.value = res.data.telemetry || {}
    }
  } catch { /* ignore */ }
}

onMounted(load)
</script>

<style scoped>
.bm { display: flex; flex-direction: column; gap: 16px; }

/* ── KPIs ── */
.bm__kpis { display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; }
@media (max-width: 900px) { .bm__kpis { grid-template-columns: repeat(3, 1fr); } }
.bm__kpi {
  text-align: center; padding: 14px 8px;
  background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-lg);
}
.bm__kpi-value { font-size: 22px; font-weight: 700; color: var(--v2-text-1); font-family: var(--v2-font-mono); }
.bm__kpi-value--active { color: var(--v2-text-1); }
.bm__kpi-value--error { color: #ef4444; }
.bm__kpi-label { font-size: 11px; color: var(--v2-text-3); margin-top: 2px; }

/* ── Panels ── */
.bm__row2 { display: grid; grid-template-columns: 1.5fr 1fr; gap: 12px; }
@media (max-width: 900px) { .bm__row2 { grid-template-columns: 1fr; } }
.bm__panel {
  background: var(--v2-bg-card); border: 1px solid var(--v2-border-2);
  border-radius: var(--v2-radius-lg); padding: 16px 18px;
}
.bm__panel--full { grid-column: 1 / -1; }
.bm__panel-hd { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; }
.bm__panel-title { font-size: var(--v2-text-md); font-weight: var(--v2-font-semibold); color: var(--v2-text-1); }
.bm__panel-badge {
  font-size: 11px; padding: 1px 7px; border-radius: var(--v2-radius-sm);
  background: var(--v2-bg-sunken); color: var(--v2-text-3); font-family: var(--v2-font-mono);
}

/* ── Table ── */
.bm__table-wrap { overflow-x: auto; }
.bm__table { width: 100%; border-collapse: collapse; font-size: 12px; }
.bm__table th { text-align: left; padding: 6px 10px; color: var(--v2-text-3); font-weight: 600; font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 1px solid var(--v2-border-2); }
.bm__table td { padding: 8px 10px; color: var(--v2-text-2); border-bottom: 1px solid var(--v2-border-2); }
.bm__table tr:hover td { background: var(--v2-bg-hover); }
.bm__rank { color: var(--v2-text-3); font-family: var(--v2-font-mono); }
.bm__mono { font-family: var(--v2-font-mono); color: var(--v2-text-1); }

/* ── Rate badges ── */
.bm__rate { font-family: var(--v2-font-mono); font-weight: 600; font-size: 12px; }
.bm__rate--good { color: #22c55e; }
.bm__rate--mid { color: #f59e0b; }
.bm__rate--bad { color: #ef4444; }

/* ── Gauge ── */
.bm__gauge-wrap { display: flex; justify-content: center; padding: 8px 0 16px; }
.bm__gauge { width: 180px; height: 110px; }
.bm__gauge-fill { transition: stroke-dasharray 0.8s ease-out; }
.bm__gauge-pct { font-size: 28px; font-weight: 700; fill: var(--v2-text-1); font-family: var(--v2-font-mono); }
.bm__gauge-label { font-size: 10px; fill: var(--v2-text-3); }

/* ── Mini Stats ── */
.bm__mini-stats { display: flex; gap: 16px; justify-content: center; border-top: 1px solid var(--v2-border-2); padding-top: 12px; }
.bm__mini-stat { display: flex; gap: 6px; align-items: center; font-size: 12px; }
.bm__mini-label { color: var(--v2-text-3); }

/* ── Trend ── */
.bm__trend { display: flex; flex-direction: column; gap: 0; }
.bm__trend-row {
  display: grid; grid-template-columns: 2fr 1fr 60px 70px 70px;
  gap: 8px; align-items: center; padding: 8px 0;
  border-bottom: 1px solid var(--v2-border-2); font-size: 12px;
}
.bm__trend-row:last-child { border-bottom: none; }
.bm__trend-name { color: var(--v2-text-1); font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bm__trend-agent { font-size: 11px; color: var(--v2-text-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bm__trend-cases { font-size: 11px; color: var(--v2-text-3); font-family: var(--v2-font-mono); }
.bm__trend-status { font-size: 10px; font-weight: 600; padding: 1px 6px; border-radius: 3px; text-align: center; }
.bm__trend-status--completed { background: rgba(34,197,94,0.1); color: #22c55e; }
.bm__trend-status--failed { background: rgba(239,68,68,0.1); color: #ef4444; }

/* ── List ── */
.bm__list { display: flex; flex-direction: column; gap: 0; }
.bm__list-row {
  display: flex; align-items: center; gap: 8px; padding: 8px 0;
  border-bottom: 1px solid var(--v2-border-2); font-size: 12px;
}
.bm__list-row:last-child { border-bottom: none; }
.bm__list-name { flex: 1; color: var(--v2-text-1); font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bm__list-type { color: var(--v2-text-3); font-size: 11px; }

.bm__empty { text-align: center; color: var(--v2-text-4); font-size: 12px; padding: 24px 0; }
</style>
