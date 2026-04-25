<template>
  <div class="cw">
    <div class="cw__toolbar">
      <div class="cw__tb-left">
        <h2 class="cw__title">工作流注册</h2>
        <span class="cw__derived">基于 Traces 数据</span>
      </div>
      <V2Button variant="ghost" size="sm" :loading="loading" @click="load">刷新</V2Button>
    </div>

    <div class="cw__split" v-loading="loading">
      <!-- Left: workflow list -->
      <div class="cw__list">
        <div v-for="wf in workflows" :key="wf.name" class="cw__card" :class="{ 'cw__card--active': sel?.name === wf.name }" @click="sel = wf">
          <div class="cw__card-top">
            <span class="cw__card-name">{{ wf.name }}</span>
            <span class="cw__st" :class="wf.hasRuns ? 'cw__st--active' : 'cw__st--idle'">{{ wf.hasRuns ? '运行中' : '空闲' }}</span>
          </div>
          <div class="cw__card-desc">{{ wf.description }}</div>
          <div class="cw__card-metrics">
            <div class="cw__cm"><span class="cw__cm-v">{{ wf.totalRuns }}</span><span class="cw__cm-k">运行</span></div>
            <div class="cw__cm"><span class="cw__cm-v cw__cm-v--ok">{{ wf.successRuns }}</span><span class="cw__cm-k">成功</span></div>
            <div class="cw__cm"><span class="cw__cm-v cw__cm-v--err">{{ wf.failedRuns }}</span><span class="cw__cm-k">失败</span></div>
            <div class="cw__cm"><span class="cw__cm-v">{{ wf.avgLatency }}<small>ms</small></span><span class="cw__cm-k">均耗</span></div>
          </div>
        </div>
      </div>

      <!-- Right: detail -->
      <div class="cw__detail" v-if="sel">
        <div class="cw__dh">
          <div class="cw__dh-name">{{ sel.name }}</div>
          <span class="cw__st" :class="sel.hasRuns ? 'cw__st--active' : 'cw__st--idle'">{{ sel.hasRuns ? '运行中' : '空闲' }}</span>
        </div>
        <div class="cw__dh-desc">{{ sel.description }}</div>

        <!-- Runtime summary -->
        <div class="cw__sec-label">运行概览</div>
        <div class="cw__runtime">
          <div class="cw__rc"><span class="cw__rc-k">总运行</span><span class="cw__rc-v">{{ sel.totalRuns }}</span></div>
          <div class="cw__rc"><span class="cw__rc-k">成功</span><span class="cw__rc-v cw__rc-v--ok">{{ sel.successRuns }}</span></div>
          <div class="cw__rc"><span class="cw__rc-k">失败</span><span class="cw__rc-v cw__rc-v--err">{{ sel.failedRuns }}</span></div>
          <div class="cw__rc"><span class="cw__rc-k">平均耗时</span><span class="cw__rc-v">{{ sel.avgLatency }}ms</span></div>
          <div class="cw__rc"><span class="cw__rc-k">成功率</span><span class="cw__rc-v">{{ sel.totalRuns > 0 ? Math.round(sel.successRuns / sel.totalRuns * 100) : 0 }}%</span></div>
        </div>

        <!-- Recent runs -->
        <div class="cw__sec-label">最近运行</div>
        <div v-if="sel.recentRuns?.length" class="cw__runs">
          <div v-for="r in sel.recentRuns" :key="r.run_id" class="cw__run" @click="$router.push(`/console/traces/${r.run_id}`)">
            <span class="cw__run-st" :class="'cw__run-st--' + r.status" />
            <span class="cw__mono">{{ r.run_id?.slice(0, 12) }}</span>
            <span class="cw__run-time">{{ fmtTime(r.started_at) }}</span>
          </div>
        </div>
        <div v-else class="cw__muted">暂无运行记录</div>

        <button class="cw__traces-btn" @click="viewTraces(sel.name)">查看全部 Traces →</button>
      </div>
      <div class="cw__detail cw__detail--empty" v-else><span class="cw__muted">← 选择一个工作流</span></div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { adminApi } from '@/api/admin/index'
import { fmtShort as fmtTime } from '@/utils/time'
import V2Button from '@/components/v2/V2Button.vue'

const router = useRouter(), loading = ref(false), sel = ref(null)

const KNOWN_WORKFLOWS = [
  { name: 'business_overview', description: '经营总览分析 Workflow' },
  { name: 'risk_review',       description: '高风险交易审核 Workflow（含 HITL）' },
  { name: 'openclaw',          description: 'OpenClaw 客服会话 Workflow' },
  { name: 'ops_diagnosis',     description: '运维诊断问答 Workflow' },
]
const KNOWN_NAMES = new Set(KNOWN_WORKFLOWS.map(w => w.name))

const workflows = ref([])
function viewTraces(name) { router.push({ path: '/console/traces', query: { workflow_name: name } }) }

// fmtTime imported from @/utils/time (UTC-safe)

async function load() {
  loading.value = true
  try {
    const items = (await adminApi.getTraces({ limit: 500, offset: 0 }))?.items ?? []
    const m = {}
    for (const t of items) { const w = t.workflow_name || 'unknown'; if (!m[w]) m[w] = { total: 0, success: 0, failed: 0, latSum: 0, recent: [] }; m[w].total++; if (t.status === 'completed') m[w].success++; if (t.status === 'failed') m[w].failed++; m[w].latSum += (t.latency_ms || 0); if (m[w].recent.length < 5) m[w].recent.push(t) }
    const known = KNOWN_WORKFLOWS.map(wf => { const s = m[wf.name] || { total: 0, success: 0, failed: 0, latSum: 0, recent: [] }; return { ...wf, hasRuns: s.total > 0, totalRuns: s.total, successRuns: s.success, failedRuns: s.failed, avgLatency: s.total > 0 ? Math.round(s.latSum / s.total) : 0, recentRuns: s.recent } })
    const extra = Object.keys(m).filter(k => k !== 'unknown' && !KNOWN_NAMES.has(k)).map(k => { const s = m[k]; return { name: k, description: '动态发现的 Workflow', hasRuns: true, totalRuns: s.total, successRuns: s.success, failedRuns: s.failed, avgLatency: s.total > 0 ? Math.round(s.latSum / s.total) : 0, recentRuns: s.recent } })
    workflows.value = [...known, ...extra]
  } catch (e) {
    console.warn('[Workflows]', e)
    console.warn('[Workflows] load fallback')
    workflows.value = KNOWN_WORKFLOWS.map(wf => ({ ...wf, hasRuns: false, totalRuns: 0, successRuns: 0, failedRuns: 0, avgLatency: 0, recentRuns: [] }))
  }
  finally { loading.value = false }
}

onMounted(load)
</script>

<style scoped>
.cw__toolbar { display: flex; align-items: center; gap: var(--v2-space-3); padding: var(--v2-space-2) var(--v2-space-3); margin-bottom: var(--v2-space-3); background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-lg); }
.cw__tb-left { display: flex; align-items: center; gap: var(--v2-space-2); flex: 1; }
.cw__title { font-size: var(--v2-text-md); font-weight: var(--v2-font-semibold); color: var(--v2-text-1); margin: 0; }
.cw__derived { font-size: 9px; padding: 1px 6px; background: var(--v2-ai-purple-bg); color: var(--v2-ai-purple); border-radius: 3px; font-weight: var(--v2-font-semibold); letter-spacing: .5px; }

.cw__split { display: grid; grid-template-columns: 1fr 1fr; gap: var(--v2-space-3); min-height: calc(100vh - 180px); }

.cw__list { display: flex; flex-direction: column; gap: var(--v2-space-2); overflow-y: auto; }
.cw__card { background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-lg); padding: var(--v2-space-3); cursor: pointer; transition: all var(--v2-trans-fast); }
.cw__card:hover { border-color: var(--v2-brand-primary); }
.cw__card--active { border-color: var(--v2-brand-primary); background: var(--v2-brand-bg); }
.cw__card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 3px; }
.cw__card-name { font-size: 13px; font-weight: var(--v2-font-semibold); color: var(--v2-text-1); font-family: var(--v2-font-mono); }
.cw__card-desc { font-size: 11px; color: var(--v2-text-3); margin-bottom: 8px; }
.cw__card-metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 4px; padding-top: 8px; border-top: 1px solid var(--v2-border-1); }
.cw__cm { text-align: center; }
.cw__cm-v { display: block; font-size: var(--v2-text-md); font-weight: var(--v2-font-bold); color: var(--v2-text-1); font-variant-numeric: tabular-nums; line-height: 1.2; }
.cw__cm-v small { font-size: 9px; font-weight: 400; color: var(--v2-text-4); }
.cw__cm-v--ok { color: var(--v2-success); } .cw__cm-v--err { color: var(--v2-error); }
.cw__cm-k { font-size: 9px; color: var(--v2-text-4); text-transform: uppercase; }

.cw__st { font-size: 10px; font-weight: var(--v2-font-medium); padding: 1px 5px; border-radius: 3px; }
.cw__st--active { background: var(--v2-success-bg); color: var(--v2-success-text); }
.cw__st--idle { background: var(--v2-bg-sunken); color: var(--v2-text-4); }

.cw__detail { background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-lg); padding: var(--v2-space-4); overflow-y: auto; display: flex; flex-direction: column; gap: var(--v2-space-3); }
.cw__detail--empty { align-items: center; justify-content: center; }

.cw__dh { display: flex; justify-content: space-between; align-items: center; }
.cw__dh-name { font-size: var(--v2-text-lg); font-weight: var(--v2-font-semibold); color: var(--v2-text-1); font-family: var(--v2-font-mono); }
.cw__dh-desc { font-size: 12px; color: var(--v2-text-3); }

.cw__sec-label { font-size: 10px; font-weight: var(--v2-font-semibold); color: var(--v2-text-4); text-transform: uppercase; letter-spacing: .5px; }

.cw__runtime { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
.cw__rc { padding: 6px 8px; background: var(--v2-bg-sunken); border-radius: var(--v2-radius-md); }
.cw__rc-k { display: block; font-size: 9px; color: var(--v2-text-4); text-transform: uppercase; }
.cw__rc-v { font-size: 14px; font-weight: var(--v2-font-bold); color: var(--v2-text-1); font-variant-numeric: tabular-nums; }
.cw__rc-v--ok { color: var(--v2-success); } .cw__rc-v--err { color: var(--v2-error); }

.cw__runs { display: flex; flex-direction: column; gap: 3px; }
.cw__run { display: flex; align-items: center; gap: 8px; padding: 5px 8px; background: var(--v2-bg-sunken); border-radius: var(--v2-radius-md); cursor: pointer; font-size: 11px; transition: background var(--v2-trans-fast); }
.cw__run:hover { background: var(--v2-border-1); }
.cw__run-st { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; background: var(--v2-gray-300); }
.cw__run-st--completed { background: var(--v2-success); } .cw__run-st--failed { background: var(--v2-error); }
.cw__run-time { margin-left: auto; font-size: 10px; color: var(--v2-text-4); }

.cw__traces-btn { width: 100%; padding: 8px 0; background: var(--v2-brand-bg); color: var(--v2-brand-primary); border: 1px solid rgba(67,97,238,.15); border-radius: var(--v2-radius-md); font-size: 12px; font-weight: var(--v2-font-semibold); cursor: pointer; margin-top: auto; } .cw__traces-btn:hover { background: var(--v2-brand-primary); color: #fff; }

.cw__mono { font-family: var(--v2-font-mono); font-size: 10px; color: var(--v2-text-3); }
.cw__muted { font-size: 11px; color: var(--v2-text-4); }

@media (max-width: 1200px) { .cw__split { grid-template-columns: 1fr; } }
</style>
