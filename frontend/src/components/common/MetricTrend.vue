<template>
  <div class="metric-trend">
    <div class="metric-trend__header">
      <span class="metric-trend__label">{{ label }}</span>
      <span class="metric-trend__value">{{ displayValue }}</span>
    </div>
    <div class="metric-trend__chart">
      <v-chart v-if="chartOption" :option="chartOption" autoresize style="height:48px" />
    </div>
    <div v-if="change !== null" class="metric-trend__footer">
      <span class="metric-trend__change" :class="changeClass">
        {{ change >= 0 ? '+' : '' }}{{ change }}%
      </span>
      <span class="metric-trend__period">{{ period }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  label:  { type: String, required: true },
  value:  { type: [String, Number], default: '-' },
  data:   { type: Array, default: () => [] },
  change: { type: Number, default: null },
  period: { type: String, default: '较上周' },
  color:  { type: String, default: 'var(--color-accent)' },
})

const displayValue = computed(() =>
  props.value === null || props.value === undefined ? '-' : String(props.value)
)

const changeClass = computed(() => ({
  'metric-trend__change--up':   props.change > 0,
  'metric-trend__change--down': props.change < 0,
}))

const chartOption = computed(() => {
  if (!props.data.length) return null
  return {
    grid: { left: 0, right: 0, top: 2, bottom: 2 },
    xAxis: { type: 'category', show: false, data: props.data.map((_, i) => i) },
    yAxis: { type: 'value', show: false },
    series: [{
      type: 'line',
      data: props.data,
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 2, color: props.color.startsWith('var') ? '#4361ee' : props.color },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [
        { offset: 0, color: 'rgba(67,97,238,.15)' },
        { offset: 1, color: 'rgba(67,97,238,.02)' },
      ]}},
    }],
    tooltip: { show: false },
  }
})
</script>

<style scoped>
.metric-trend {
  background: var(--color-bg-card);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  box-shadow: var(--shadow-xs);
}
.metric-trend__header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: var(--spacing-xs);
}
.metric-trend__label {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
}
.metric-trend__value {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-primary);
  font-variant-numeric: tabular-nums;
}
.metric-trend__chart { margin: var(--spacing-xs) 0; }
.metric-trend__footer {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: var(--font-size-xs);
}
.metric-trend__change--up   { color: var(--color-success); }
.metric-trend__change--down { color: var(--color-error); }
.metric-trend__period { color: var(--color-text-disabled); }
</style>
