<template>
  <svg
    class="spark"
    :width="width"
    :height="height"
    :viewBox="`0 0 ${width} ${height}`"
    preserveAspectRatio="none"
  >
    <defs>
      <linearGradient :id="gradId" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" :stop-color="color" stop-opacity="0.15" />
        <stop offset="100%" :stop-color="color" stop-opacity="0" />
      </linearGradient>
    </defs>
    <path v-if="areaPath" :d="areaPath" :fill="`url(#${gradId})`" />
    <polyline
      v-if="linePath"
      :points="linePath"
      fill="none"
      :stroke="color"
      :stroke-width="strokeWidth"
      stroke-linecap="round"
      stroke-linejoin="round"
    />
    <circle
      v-if="lastPoint"
      :cx="lastPoint[0]"
      :cy="lastPoint[1]"
      :r="strokeWidth + 0.5"
      :fill="color"
    />
  </svg>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  data:        { type: Array, default: () => [] },
  width:       { type: Number, default: 80 },
  height:      { type: Number, default: 24 },
  color:       { type: String, default: '#18181b' },
  strokeWidth: { type: Number, default: 1.5 },
})

let _uid = 0
const gradId = `spark-grad-${++_uid}`

const points = computed(() => {
  const d = props.data
  if (!d || d.length < 2) return []
  const max = Math.max(...d)
  const min = Math.min(...d)
  const range = max - min || 1
  const pad = 2
  const w = props.width - pad * 2
  const h = props.height - pad * 2
  return d.map((v, i) => [
    pad + (i / (d.length - 1)) * w,
    pad + h - ((v - min) / range) * h,
  ])
})

const linePath = computed(() =>
  points.value.map(p => p.join(',')).join(' ') || null
)

const areaPath = computed(() => {
  const pts = points.value
  if (pts.length < 2) return null
  const first = pts[0]
  const last = pts[pts.length - 1]
  let d = `M ${first[0]},${first[1]}`
  for (let i = 1; i < pts.length; i++) {
    d += ` L ${pts[i][0]},${pts[i][1]}`
  }
  d += ` L ${last[0]},${props.height} L ${first[0]},${props.height} Z`
  return d
})

const lastPoint = computed(() =>
  points.value.length ? points.value[points.value.length - 1] : null
)
</script>

<style scoped>
.spark {
  display: block;
  flex-shrink: 0;
}
</style>
