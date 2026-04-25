<template>
  <span class="sd" :class="[`sd--${status}`, `sd--${size}`]">
    <span class="sd__dot" />
    <span v-if="showText" class="sd__text">{{ label }}</span>
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: {
    type: String,
    default: 'pending',
    validator: v => ['completed', 'running', 'pending', 'failed', 'review', 'warning'].includes(v),
  },
  showText: { type: Boolean, default: true },
  size:     { type: String, default: 'md', validator: v => ['sm', 'md'].includes(v) },
})

const LABELS = {
  completed: '已完成',
  running:   '运行中',
  pending:   '等待中',
  failed:    '失败',
  review:    '审核中',
  warning:   '预警',
}

const label = computed(() => LABELS[props.status] || props.status)
</script>

<style scoped>
.sd {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}

/* Dot */
.sd__dot {
  width: 7px; height: 7px;
  border-radius: var(--v2-radius-full);
  flex-shrink: 0;
}
.sd--sm .sd__dot { width: 6px; height: 6px; }

/* Text */
.sd__text {
  font-size: var(--v2-text-sm);
  color: var(--v2-text-2);
  line-height: 1;
}
.sd--sm .sd__text { font-size: var(--v2-text-xs); }

/* ── Status colors ─────────────────────────────────────────── */
.sd--completed .sd__dot { background: var(--v2-success); }
.sd--completed .sd__text { color: var(--v2-success-text); }

.sd--running .sd__dot {
  background: var(--v2-brand-primary);
  animation: sd-pulse 1.5s ease-in-out infinite;
}
.sd--running .sd__text { color: var(--v2-brand-primary); }

.sd--pending .sd__dot { background: var(--v2-gray-400); }
.sd--pending .sd__text { color: var(--v2-text-3); }

.sd--failed .sd__dot { background: var(--v2-error); }
.sd--failed .sd__text { color: var(--v2-error-text); }

.sd--review .sd__dot { background: var(--v2-ai-purple); }
.sd--review .sd__text { color: var(--v2-ai-purple); }

.sd--warning .sd__dot { background: var(--v2-warning); }
.sd--warning .sd__text { color: var(--v2-warning-text); }

@keyframes sd-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50%      { opacity: .5; transform: scale(1.3); }
}
</style>
