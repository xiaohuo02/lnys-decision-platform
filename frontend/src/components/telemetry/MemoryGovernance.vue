<template>
  <div class="mg">
    <!-- ── Row 1: Layer Architecture ── -->
    <div class="mg__layers">
      <div class="mg__layer" v-for="layer in layerCards" :key="layer.key">
        <div class="mg__layer-num">{{ layer.num }}</div>
        <div class="mg__layer-body">
          <div class="mg__layer-name">{{ layer.name }}</div>
          <div class="mg__layer-desc">{{ layer.desc }}</div>
          <div class="mg__layer-stat">{{ layer.stat }}</div>
        </div>
      </div>
    </div>

    <!-- ── Row 2: Freshness Distribution + Health Stats ── -->
    <div class="mg__row2">
      <!-- Freshness Donut -->
      <div class="mg__panel">
        <div class="mg__panel-hd">
          <span class="mg__panel-title">新鲜度分布</span>
          <span class="mg__panel-badge">{{ health.total_memories }} 条</span>
        </div>
        <div class="mg__donut-wrap">
          <svg class="mg__donut" viewBox="0 0 120 120">
            <circle
              v-for="(seg, i) in donutSegments" :key="i"
              cx="60" cy="60" r="45"
              fill="none"
              :stroke="seg.color"
              stroke-width="18"
              :stroke-dasharray="seg.dashArray"
              :stroke-dashoffset="seg.offset"
              class="mg__donut-seg"
            />
            <text x="60" y="56" text-anchor="middle" class="mg__donut-pct">
              {{ health.avg_freshness ? (health.avg_freshness * 100).toFixed(0) : '—' }}
            </text>
            <text x="60" y="72" text-anchor="middle" class="mg__donut-label">平均新鲜度</text>
          </svg>
          <div class="mg__donut-legend">
            <div class="mg__legend-item" v-for="seg in legendItems" :key="seg.label">
              <span class="mg__legend-dot" :style="{ background: seg.color }"></span>
              <span class="mg__legend-label">{{ seg.label }}</span>
              <span class="mg__legend-count">{{ seg.count }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Health KPIs -->
      <div class="mg__panel">
        <div class="mg__panel-hd">
          <span class="mg__panel-title">治理指标</span>
        </div>
        <div class="mg__kpis">
          <div class="mg__kpi" v-for="kpi in kpiCards" :key="kpi.label">
            <div class="mg__kpi-value" :class="kpi.cls">{{ kpi.value }}</div>
            <div class="mg__kpi-label">{{ kpi.label }}</div>
          </div>
        </div>
        <div class="mg__config">
          <div class="mg__config-title">衰减配置</div>
          <div class="mg__config-row" v-for="(v, k) in freshnessConfig" :key="k">
            <span>{{ configLabels[k] || k }}</span>
            <span class="mg__mono">{{ v }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Row 3: Domain Distribution ── -->
    <div class="mg__panel mg__panel--full" v-if="Object.keys(health.domain_stats || {}).length">
      <div class="mg__panel-hd">
        <span class="mg__panel-title">领域分布</span>
      </div>
      <div class="mg__domains">
        <div class="mg__domain" v-for="(count, domain) in health.domain_stats" :key="domain">
          <div class="mg__domain-name">{{ domain }}</div>
          <div class="mg__domain-bar">
            <div class="mg__domain-fill" :style="{ width: domainPct(count) + '%' }"></div>
          </div>
          <div class="mg__domain-count">{{ count }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { fetchMemoryHealth } from '@/api/admin/memoryGovernance'

const health = ref({
  total_memories: 0, active_memories: 0,
  fresh_count: 0, warm_count: 0, stale_count: 0, expired_count: 0,
  avg_freshness: 0, avg_importance: 0,
  domain_stats: {},
})
const copilotStats = ref({ total: 0, active: 0 })
const freshnessConfig = ref({})

const layerCards = computed(() => [
  {
    key: 'L1', num: 'L1', name: '对话历史',
    desc: 'Redis 缓存 · TTL 7天 · 自动回填',
    stat: 'Redis TTL 7d',
  },
  {
    key: 'L2', num: 'L2', name: 'Copilot 记忆',
    desc: '用户偏好 · 领域知识 · 重要度排序',
    stat: `${copilotStats.value.active}/${copilotStats.value.total} 条`,
  },
  {
    key: 'L3', num: 'L3', name: '系统规则',
    desc: '静态配置 · 角色定义 · 行为约束',
    stat: '静态',
  },
])

const COLORS = { fresh: '#22c55e', warm: '#f59e0b', stale: '#94a3b8', expired: '#ef4444' }
const LABELS = { fresh: '新鲜', warm: '温热', stale: '陈旧', expired: '过期' }

const legendItems = computed(() => [
  { label: LABELS.fresh, count: health.value.fresh_count, color: COLORS.fresh },
  { label: LABELS.warm, count: health.value.warm_count, color: COLORS.warm },
  { label: LABELS.stale, count: health.value.stale_count, color: COLORS.stale },
  { label: LABELS.expired, count: health.value.expired_count, color: COLORS.expired },
])

const donutSegments = computed(() => {
  const total = health.value.total_memories || 1
  const circumference = 2 * Math.PI * 45
  const counts = [
    { count: health.value.fresh_count, color: COLORS.fresh },
    { count: health.value.warm_count, color: COLORS.warm },
    { count: health.value.stale_count, color: COLORS.stale },
    { count: health.value.expired_count, color: COLORS.expired },
  ]
  let cumOffset = 0
  return counts.map(c => {
    const pct = c.count / total
    const len = pct * circumference
    const seg = {
      color: c.color,
      dashArray: `${len} ${circumference - len}`,
      offset: -cumOffset,
    }
    cumOffset += len
    return seg
  })
})

const kpiCards = computed(() => {
  const h = health.value
  return [
    { label: '总记忆', value: h.total_memories, cls: '' },
    { label: '平均重要度', value: h.avg_importance ? h.avg_importance.toFixed(2) : '—', cls: '' },
    { label: '过期率', value: h.total_memories ? ((h.expired_count / h.total_memories) * 100).toFixed(1) + '%' : '—', cls: h.expired_count > h.total_memories * 0.3 ? 'mg__kpi-value--warn' : '' },
    { label: 'Copilot 记忆', value: copilotStats.value.active, cls: '' },
  ]
})

const configLabels = {
  recency_weight: '时效权重',
  importance_weight: '重要度权重',
  frequency_weight: '频率权重',
  half_life_days: '半衰期(天)',
  max_access_boost: '最大访问增益',
}

function domainPct(count) {
  const max = Math.max(...Object.values(health.value.domain_stats || { _: 1 }))
  return (count / max) * 100
}

async function load() {
  try {
    const res = await fetchMemoryHealth()
    if (res.ok) {
      health.value = res.data.memory_records || health.value
      copilotStats.value = res.data.copilot_memory || copilotStats.value
      freshnessConfig.value = res.data.freshness_config || {}
    }
  } catch { /* ignore */ }
}

onMounted(load)
</script>

<style scoped>
.mg { display: flex; flex-direction: column; gap: 16px; }

/* ── Layers ── */
.mg__layers { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.mg__layer {
  display: flex; gap: 12px; padding: 16px;
  background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-lg);
}
.mg__layer-num {
  width: 32px; height: 32px; border-radius: 50%;
  background: var(--v2-text-1); color: var(--v2-bg-card);
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700; font-family: var(--v2-font-mono); flex-shrink: 0;
}
.mg__layer-body { display: flex; flex-direction: column; gap: 2px; }
.mg__layer-name { font-size: 14px; font-weight: 600; color: var(--v2-text-1); }
.mg__layer-desc { font-size: 11px; color: var(--v2-text-3); }
.mg__layer-stat { font-size: 11px; color: var(--v2-text-2); font-family: var(--v2-font-mono); margin-top: 4px; }

/* ── Panels ── */
.mg__row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@media (max-width: 900px) { .mg__row2 { grid-template-columns: 1fr; } }
.mg__panel {
  background: var(--v2-bg-card); border: 1px solid var(--v2-border-2);
  border-radius: var(--v2-radius-lg); padding: 16px 18px;
}
.mg__panel--full { grid-column: 1 / -1; }
.mg__panel-hd { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; }
.mg__panel-title { font-size: var(--v2-text-md); font-weight: var(--v2-font-semibold); color: var(--v2-text-1); }
.mg__panel-badge {
  font-size: 11px; padding: 1px 7px; border-radius: var(--v2-radius-sm);
  background: var(--v2-bg-sunken); color: var(--v2-text-3); font-family: var(--v2-font-mono);
}

/* ── Donut ── */
.mg__donut-wrap { display: flex; gap: 20px; align-items: center; }
.mg__donut { width: 120px; height: 120px; flex-shrink: 0; transform: rotate(-90deg); }
.mg__donut-seg { transition: stroke-dasharray 0.6s, stroke-dashoffset 0.6s; }
.mg__donut-pct { font-size: 22px; font-weight: 700; fill: var(--v2-text-1); font-family: var(--v2-font-mono); transform: rotate(90deg); transform-origin: 60px 60px; }
.mg__donut-label { font-size: 9px; fill: var(--v2-text-3); transform: rotate(90deg); transform-origin: 60px 60px; }
.mg__donut-legend { display: flex; flex-direction: column; gap: 8px; }
.mg__legend-item { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.mg__legend-dot { width: 8px; height: 8px; border-radius: 2px; flex-shrink: 0; }
.mg__legend-label { color: var(--v2-text-2); }
.mg__legend-count { color: var(--v2-text-1); font-family: var(--v2-font-mono); margin-left: auto; }

/* ── KPIs ── */
.mg__kpis { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 16px; }
.mg__kpi { text-align: center; }
.mg__kpi-value { font-size: 24px; font-weight: 700; color: var(--v2-text-1); font-family: var(--v2-font-mono); }
.mg__kpi-value--warn { color: #f59e0b; }
.mg__kpi-label { font-size: 11px; color: var(--v2-text-3); margin-top: 2px; }

/* ── Config ── */
.mg__config { border-top: 1px solid var(--v2-border-2); padding-top: 12px; }
.mg__config-title { font-size: 11px; color: var(--v2-text-3); margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.05em; }
.mg__config-row { display: flex; justify-content: space-between; font-size: 12px; padding: 2px 0; }
.mg__config-row span:first-child { color: var(--v2-text-3); }
.mg__mono { color: var(--v2-text-1); font-family: var(--v2-font-mono); }

/* ── Domains ── */
.mg__domains { display: flex; flex-direction: column; gap: 8px; }
.mg__domain { display: grid; grid-template-columns: 100px 1fr 40px; gap: 10px; align-items: center; }
.mg__domain-name { font-size: 12px; color: var(--v2-text-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mg__domain-bar { height: 6px; background: var(--v2-bg-sunken); border-radius: 3px; overflow: hidden; }
.mg__domain-fill { height: 100%; background: var(--v2-text-1); border-radius: 3px; transition: width 0.4s; }
.mg__domain-count { font-size: 11px; color: var(--v2-text-1); font-family: var(--v2-font-mono); text-align: right; }
</style>
