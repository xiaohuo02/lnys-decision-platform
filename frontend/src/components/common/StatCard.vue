<template>
  <div class="stat-card" :style="{ borderLeftColor: color }">
    <div class="stat-card__header">
      <span class="stat-card__label">{{ label }}</span>
      <el-icon v-if="icon" class="stat-card__icon" :size="16"><component :is="icon" /></el-icon>
    </div>
    <div class="stat-card__value">{{ displayValue }}</div>
    <div v-if="trend !== null" class="stat-card__trend" :class="trendClass">
      <span class="stat-card__trend-arrow">{{ trend >= 0 ? '↑' : '↓' }}</span>
      <span>{{ Math.abs(trend) }}%</span>
      <span v-if="trendLabel" class="stat-card__trend-label">{{ trendLabel }}</span>
    </div>
    <slot />
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  label:      { type: String, required: true },
  value:      { type: [String, Number], default: '-' },
  color:      { type: String, default: 'var(--color-accent)' },
  icon:       { type: String, default: '' },
  trend:      { type: Number, default: null },
  trendLabel: { type: String, default: '' },
  prefix:     { type: String, default: '' },
  suffix:     { type: String, default: '' },
})

const displayValue = computed(() => {
  if (props.value === '-' || props.value === null || props.value === undefined) return '-'
  return `${props.prefix}${props.value}${props.suffix}`
})

const trendClass = computed(() => ({
  'stat-card__trend--up':   props.trend > 0,
  'stat-card__trend--down': props.trend < 0,
}))
</script>

<style scoped>
.stat-card {
  background: var(--color-bg-card);
  border-radius: var(--radius-md);
  padding: var(--spacing-md) var(--spacing-lg);
  border-left: 3px solid var(--color-accent);
  box-shadow: var(--shadow-xs);
  min-width: 0;
}
.stat-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--spacing-sm);
}
.stat-card__label {
  font-size: var(--font-size-body);
  color: var(--color-text-tertiary);
  font-weight: var(--font-weight-medium);
}
.stat-card__icon { color: var(--color-text-disabled); }
.stat-card__value {
  font-size: var(--font-size-xxl);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-primary);
  line-height: 1;
  margin-bottom: var(--spacing-xs);
  font-variant-numeric: tabular-nums;
}
.stat-card__trend {
  font-size: var(--font-size-xs);
  display: flex;
  align-items: center;
  gap: 2px;
}
.stat-card__trend--up   { color: var(--color-success); }
.stat-card__trend--down { color: var(--color-error); }
.stat-card__trend-label {
  color: var(--color-text-disabled);
  margin-left: 4px;
}
</style>
