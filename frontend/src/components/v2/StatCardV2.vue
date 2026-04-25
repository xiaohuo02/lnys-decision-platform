<template>
  <div class="sc" :class="{ 'sc--clickable': clickable }" @click="clickable && $emit('click')">
    <div class="sc__header">
      <span class="sc__label">{{ label }}</span>
      <span v-if="trend" class="sc__trend" :class="`sc__trend--${trendDir}`">
        {{ trend }}
      </span>
    </div>
    <div class="sc__value"><slot name="value">{{ displayValue }}</slot></div>
    <div v-if="sub" class="sc__sub">{{ sub }}</div>
    <div v-if="$slots.footer" class="sc__footer"><slot name="footer" /></div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  label:     { type: String, required: true },
  value:     { type: [String, Number], default: '--' },
  trend:     { type: String, default: '' },
  trendDir:  { type: String, default: 'neutral', validator: v => ['up', 'down', 'neutral'].includes(v) },
  sub:       { type: String, default: '' },
  clickable: { type: Boolean, default: false },
})

defineEmits(['click'])

const displayValue = computed(() => {
  if (typeof props.value === 'number') {
    return props.value >= 10000
      ? (props.value / 10000).toFixed(1) + '万'
      : props.value.toLocaleString()
  }
  return props.value
})
</script>

<style scoped>
.sc {
  background: var(--v2-bg-card);
  border: 1px solid var(--v2-border-2);
  border-radius: var(--v2-radius-lg);
  padding: var(--v2-space-5);
  transition: all var(--v2-trans-fast);
  min-width: 0;
}
.sc--clickable { cursor: pointer; }
.sc--clickable:hover {
  border-color: var(--v2-border-3);
  box-shadow: var(--v2-shadow-sm);
}

.sc__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--v2-space-2);
}
.sc__label {
  font-size: var(--v2-text-sm);
  color: var(--v2-text-3);
  font-weight: var(--v2-font-medium);
  letter-spacing: .2px;
}
.sc__trend {
  font-size: var(--v2-text-xs);
  font-weight: var(--v2-font-medium);
  padding: 1px 6px;
  border-radius: var(--v2-radius-sm);
}
.sc__trend--up   { color: var(--v2-success-text); background: var(--v2-success-bg); }
.sc__trend--down { color: var(--v2-error-text);   background: var(--v2-error-bg); }
.sc__trend--neutral { color: var(--v2-text-3); background: var(--v2-gray-100); }

.sc__value {
  font-size: var(--v2-text-3xl);
  font-weight: var(--v2-font-bold);
  color: var(--v2-text-1);
  line-height: var(--v2-leading-tight);
  font-variant-numeric: tabular-nums;
}

.sc__sub {
  font-size: var(--v2-text-xs);
  color: var(--v2-text-4);
  margin-top: var(--v2-space-1);
}

.sc__footer {
  margin-top: var(--v2-space-3);
  padding-top: var(--v2-space-3);
  border-top: 1px solid var(--v2-border-2);
}
</style>
