<template>
  <svg class="lift-bar" :width="width" :height="height" viewBox="0 0 40 12">
    <rect x="0" y="2" :width="40" height="8" rx="2" fill="var(--v2-bg-sunken)" />
    <rect x="0" y="2" :width="barWidth" height="8" rx="2" :fill="barColor" />
  </svg>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  value: { type: Number, default: 0 },
  max:   { type: Number, default: 6 },
  width: { type: Number, default: 40 },
  height:{ type: Number, default: 12 },
})

const ratio = computed(() => Math.min(props.value / (props.max || 1), 1))
const barWidth = computed(() => Math.max(ratio.value * 40, 2))
const barColor = computed(() => {
  if (props.value > 3) return 'var(--v2-text-1)'
  if (props.value > 1.5) return 'var(--v2-text-3)'
  return 'var(--v2-text-4)'
})
</script>

<style scoped>
.lift-bar {
  display: block;
  flex-shrink: 0;
}
</style>
