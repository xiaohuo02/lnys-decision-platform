<template>
  <div class="itc" ref="containerRef">
    <svg
      v-if="data.length"
      :width="svgW"
      :height="svgH"
      :viewBox="`0 0 ${svgW} ${svgH}`"
      class="itc__svg"
    >
      <!-- Grid lines -->
      <line
        v-for="y in gridY"
        :key="'g'+y"
        :x1="pad.left"
        :y1="y"
        :x2="svgW - pad.right"
        :y2="y"
        stroke="rgba(0,0,0,0.04)"
        stroke-width="1"
      />

      <!-- Area fill -->
      <path :d="areaPath" fill="url(#itc-grad)" />

      <!-- Line -->
      <polyline
        :points="linePts"
        fill="none"
        stroke="#18181b"
        stroke-width="1.5"
        stroke-linecap="round"
        stroke-linejoin="round"
      />

      <!-- Warning bars (subtle) -->
      <rect
        v-for="(pt, i) in warningBars"
        :key="'w'+i"
        :x="pt.x - barW / 2"
        :y="pt.y"
        :width="barW"
        :height="chartH - pt.y + pad.top"
        rx="1"
        fill="rgba(245,158,11,0.15)"
      />

      <!-- Critical bars -->
      <rect
        v-for="(pt, i) in criticalBars"
        :key="'c'+i"
        :x="pt.x + barW / 2"
        :y="pt.y"
        :width="barW"
        :height="chartH - pt.y + pad.top"
        rx="1"
        fill="rgba(239,68,68,0.2)"
      />

      <!-- X-axis labels -->
      <text
        v-for="(lbl, i) in xLabels"
        :key="'xl'+i"
        :x="lbl.x"
        :y="svgH - 4"
        text-anchor="middle"
        class="itc__axis-label"
      >{{ lbl.text }}</text>

      <!-- Y-axis labels -->
      <text
        v-for="(lbl, i) in yLabels"
        :key="'yl'+i"
        :x="pad.left - 6"
        :y="lbl.y + 4"
        text-anchor="end"
        class="itc__axis-label"
      >{{ lbl.text }}</text>

      <!-- Hover dot -->
      <circle
        v-if="hoverIdx >= 0"
        :cx="points[hoverIdx]?.[0]"
        :cy="points[hoverIdx]?.[1]"
        r="3.5"
        fill="#18181b"
        stroke="#fff"
        stroke-width="2"
      />

      <!-- Invisible hover rects -->
      <rect
        v-for="(pt, i) in points"
        :key="'h'+i"
        :x="pt[0] - stepX / 2"
        :y="pad.top"
        :width="stepX"
        :height="chartH"
        fill="transparent"
        @mouseenter="hoverIdx = i"
        @mouseleave="hoverIdx = -1"
      />

      <defs>
        <linearGradient id="itc-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#18181b" stop-opacity="0.06" />
          <stop offset="100%" stop-color="#18181b" stop-opacity="0" />
        </linearGradient>
      </defs>
    </svg>

    <!-- Tooltip -->
    <Transition name="itc-tip">
      <div
        v-if="hoverIdx >= 0 && data[hoverIdx]"
        class="itc__tooltip"
        :style="tooltipStyle"
      >
        <div class="itc__tip-date">{{ data[hoverIdx].date }}</div>
        <div class="itc__tip-row">
          <span>健康度</span>
          <strong>{{ data[hoverIdx].health_pct }}%</strong>
        </div>
        <div class="itc__tip-row">
          <span class="itc__tip-dot itc__tip-dot--warn"></span>
          <span>预警</span>
          <strong>{{ data[hoverIdx].warning_count }}</strong>
        </div>
        <div class="itc__tip-row">
          <span class="itc__tip-dot itc__tip-dot--crit"></span>
          <span>紧急</span>
          <strong>{{ data[hoverIdx].critical_count }}</strong>
        </div>
      </div>
    </Transition>

    <div class="itc__empty" v-if="!data.length">暂无趋势数据</div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  data:   { type: Array, default: () => [] },
  height: { type: Number, default: 180 },
})

const containerRef = ref(null)
const hoverIdx = ref(-1)

const svgW = 560
const svgH = computed(() => props.height)
const pad = { top: 16, right: 16, bottom: 28, left: 40 }
const chartH = computed(() => svgH.value - pad.top - pad.bottom)
const barW = 3

const healthMax = computed(() => Math.max(100, ...props.data.map(d => d.health_pct)))
const healthMin = computed(() => Math.max(0, Math.min(...props.data.map(d => d.health_pct)) - 5))
const countMax = computed(() => Math.max(1, ...props.data.map(d => d.warning_count + d.critical_count)))

const stepX = computed(() => {
  const n = props.data.length
  return n > 1 ? (svgW - pad.left - pad.right) / (n - 1) : 0
})

const points = computed(() =>
  props.data.map((d, i) => {
    const x = pad.left + i * stepX.value
    const range = healthMax.value - healthMin.value || 1
    const y = pad.top + chartH.value - ((d.health_pct - healthMin.value) / range) * chartH.value
    return [x, y]
  })
)

const linePts = computed(() =>
  points.value.map(p => p.join(',')).join(' ')
)

const areaPath = computed(() => {
  const pts = points.value
  if (pts.length < 2) return ''
  const bottom = pad.top + chartH.value
  let d = `M ${pts[0][0]},${pts[0][1]}`
  for (let i = 1; i < pts.length; i++) {
    d += ` L ${pts[i][0]},${pts[i][1]}`
  }
  d += ` L ${pts[pts.length - 1][0]},${bottom} L ${pts[0][0]},${bottom} Z`
  return d
})

const warningBars = computed(() =>
  props.data.map((d, i) => {
    const x = pad.left + i * stepX.value
    const h = (d.warning_count / countMax.value) * (chartH.value * 0.3)
    return { x, y: pad.top + chartH.value - h }
  })
)

const criticalBars = computed(() =>
  props.data.map((d, i) => {
    const x = pad.left + i * stepX.value
    const h = (d.critical_count / countMax.value) * (chartH.value * 0.3)
    return { x, y: pad.top + chartH.value - h }
  })
)

const gridY = computed(() => {
  const steps = 4
  return Array.from({ length: steps + 1 }, (_, i) =>
    pad.top + (chartH.value / steps) * i
  )
})

const xLabels = computed(() => {
  const d = props.data
  if (d.length <= 7) return d.map((item, i) => ({
    x: pad.left + i * stepX.value,
    text: item.date.slice(5),
  }))
  const step = Math.ceil(d.length / 6)
  return d.filter((_, i) => i % step === 0 || i === d.length - 1).map(item => ({
    x: pad.left + d.indexOf(item) * stepX.value,
    text: item.date.slice(5),
  }))
})

const yLabels = computed(() => {
  const steps = 4
  const range = healthMax.value - healthMin.value
  return Array.from({ length: steps + 1 }, (_, i) => ({
    y: pad.top + (chartH.value / steps) * i,
    text: Math.round(healthMax.value - (range / steps) * i) + '%',
  }))
})

const tooltipStyle = computed(() => {
  if (hoverIdx.value < 0 || !points.value[hoverIdx.value]) return {}
  const [x, y] = points.value[hoverIdx.value]
  const left = Math.min(Math.max(x, 80), svgW - 80)
  return {
    left: left + 'px',
    top: (y - 8) + 'px',
  }
})
</script>

<style scoped>
.itc {
  position: relative;
  width: 100%;
  overflow: hidden;
}

.itc__svg {
  display: block;
  width: 100%;
  height: auto;
}

.itc__axis-label {
  font-size: 10px;
  fill: #a1a1aa;
  font-family: 'Geist Mono', monospace;
  font-variant-numeric: tabular-nums;
}

.itc__tooltip {
  position: absolute;
  transform: translate(-50%, -100%);
  padding: 8px 12px;
  background: #18181b;
  color: #fff;
  border-radius: 8px;
  font-size: 11px;
  white-space: nowrap;
  z-index: 10;
  pointer-events: none;
}
.itc__tip-date {
  font-weight: 600;
  margin-bottom: 4px;
  font-variant-numeric: tabular-nums;
}
.itc__tip-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-variant-numeric: tabular-nums;
}
.itc__tip-row strong { margin-left: auto; }
.itc__tip-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}
.itc__tip-dot--warn { background: #f59e0b; }
.itc__tip-dot--crit { background: #ef4444; }

.itc-tip-enter-active { transition: opacity 0.1s; }
.itc-tip-leave-active { transition: opacity 0.08s; }
.itc-tip-enter-from, .itc-tip-leave-to { opacity: 0; }

.itc__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 120px;
  font-size: 13px;
  color: #a1a1aa;
}
</style>
