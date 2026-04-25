<template>
  <div class="ag">
    <v-chart
      v-if="nodes.length"
      :option="chartOption"
      autoresize
      class="ag__chart"
      @click="handleClick"
    />
    <div v-else class="ag__empty">暂无图谱数据</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  nodes:        { type: Array, default: () => [] },
  edges:        { type: Array, default: () => [] },
  selectedId:   { type: String, default: '' },
  highlightIds: { type: Array, default: () => [] },
})

const emit = defineEmits(['node-click', 'node-dblclick', 'edge-hover'])

// ── ECharts heatmap option ──
const chartOption = computed(() => {
  if (!props.nodes.length) return {}

  // Sort by frequency descending → top-left = most frequent
  const sorted = [...props.nodes].sort((a, b) => (b.frequency || 1) - (a.frequency || 1))
  const ids = sorted.map(n => n.id)
  const fullNames = sorted.map(n => n.name || n.id)
  const shortNames = fullNames.map(n => n.length > 5 ? n.slice(0, 4) + '…' : n)
  const idIdx = new Map(ids.map((id, i) => [id, i]))

  // Build symmetric lift lookup (de-duplicated, max lift per pair)
  const liftMap = new Map()
  const confMap = new Map()
  for (const e of props.edges) {
    const si = idIdx.get(e.source)
    const ti = idIdx.get(e.target)
    if (si === undefined || ti === undefined) continue
    const lift = e.lift || 0
    const k1 = `${si},${ti}`, k2 = `${ti},${si}`
    if (!liftMap.has(k1) || lift > liftMap.get(k1)) {
      liftMap.set(k1, lift); liftMap.set(k2, lift)
      confMap.set(k1, e.confidence || 0); confMap.set(k2, e.confidence || 0)
    }
  }

  // Heatmap data: [x, y, lift]
  const heatData = []
  let maxLift = 0
  for (let yi = 0; yi < ids.length; yi++) {
    for (let xi = 0; xi < ids.length; xi++) {
      if (xi === yi) continue
      const k = `${xi},${yi}`
      const lift = liftMap.get(k) || 0
      if (lift > 0) {
        heatData.push([xi, yi, +lift.toFixed(3)])
        if (lift > maxLift) maxLift = lift
      }
    }
  }

  return {
    backgroundColor: 'transparent',
    tooltip: {
      confine: true,
      backgroundColor: 'rgba(24,24,28,0.95)',
      borderColor: 'rgba(255,255,255,0.08)',
      padding: [8, 12],
      textStyle: { color: 'rgba(255,255,255,0.88)', fontSize: 12, fontFamily: '"Geist Sans", system-ui, sans-serif' },
      formatter(p) {
        const [xi, yi, v] = p.value
        if (!v) return ''
        const conf = confMap.get(`${xi},${yi}`)
        return `<b>${fullNames[xi]}</b> × <b>${fullNames[yi]}</b>`
          + `<br/>Lift <b style="color:#FADB14">${v.toFixed(2)}</b>`
          + (conf ? ` · Conf <b>${conf.toFixed(3)}</b>` : '')
      },
    },
    grid: { top: 8, right: 8, bottom: 68, left: 72 },
    xAxis: {
      type: 'category',
      data: shortNames,
      position: 'bottom',
      splitArea: { show: false },
      axisLabel: { color: 'rgba(255,255,255,0.5)', fontSize: 9, rotate: 45, interval: 0 },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
    },
    yAxis: {
      type: 'category',
      data: shortNames,
      inverse: true,
      splitArea: { show: false },
      axisLabel: { color: 'rgba(255,255,255,0.5)', fontSize: 9, interval: 0 },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
    },
    visualMap: {
      min: 0,
      max: Math.max(maxLift, 1),
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      itemWidth: 12,
      itemHeight: 100,
      text: ['高 Lift', '低'],
      textStyle: { color: 'rgba(255,255,255,0.45)', fontSize: 10 },
      inRange: {
        color: ['rgba(64,169,255,0.06)', '#177DDC', '#36CFC9', '#95DE64', '#FADB14', '#FF7A45'],
      },
    },
    series: [{
      type: 'heatmap',
      data: heatData,
      emphasis: {
        itemStyle: {
          borderColor: 'rgba(255,255,255,0.8)',
          borderWidth: 2,
          shadowBlur: 10,
          shadowColor: 'rgba(255,255,255,0.2)',
        },
      },
      itemStyle: {
        borderColor: 'rgba(0,0,0,0.4)',
        borderWidth: 1,
        borderRadius: 2,
      },
      animation: true,
      animationDuration: 600,
    }],
  }
})

// ── Events ──
function handleClick(params) {
  if (params.componentType !== 'series' || !params.value) return
  const sorted = [...props.nodes].sort((a, b) => (b.frequency || 1) - (a.frequency || 1))
  const node = sorted[params.value[0]]
  if (node) emit('node-click', { id: node.id, name: node.name || node.id, frequency: node.frequency || 1 })
}
</script>

<style scoped>
.ag {
  position: relative;
  width: 100%;
  min-height: 280px;
  height: 360px;
  overflow: hidden;
}
.ag__chart {
  width: 100%;
  height: 100%;
}
.ag__empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--v2-text-4);
  font-size: var(--v2-text-sm);
}
</style>
