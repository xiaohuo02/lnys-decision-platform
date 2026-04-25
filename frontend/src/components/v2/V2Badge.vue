<template>
  <span class="v2-badge" :class="[`v2-badge--${variant}`, `v2-badge--${size}`]">
    <span v-if="dot" class="v2-badge__dot" />
    <slot>{{ label }}</slot>
  </span>
</template>

<script setup>
defineProps({
  variant: { type: String, default: 'neutral', validator: v => ['neutral', 'success', 'warning', 'error', 'info'].includes(v) },
  size:    { type: String, default: 'sm', validator: v => ['sm', 'md'].includes(v) },
  label:   { type: String, default: '' },
  dot:     { type: Boolean, default: false },
})
</script>

<style scoped>
.v2-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-weight: var(--v2-font-medium);
  border-radius: var(--v2-radius-full);
  white-space: nowrap;
}

.v2-badge--sm { padding: 1px 6px; font-size: 10px; }
.v2-badge--md { padding: 2px 8px; font-size: var(--v2-text-xs); }

.v2-badge__dot { width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0; background: currentColor; }

.v2-badge--neutral { background: var(--v2-bg-sunken); color: var(--v2-text-3); }
.v2-badge--success { background: var(--v2-success-bg); color: var(--v2-success-text); }
.v2-badge--warning { background: var(--v2-warning-bg); color: var(--v2-warning-text); }
.v2-badge--error   { background: var(--v2-error-bg); color: var(--v2-error-text); }
.v2-badge--info    { background: var(--v2-ai-purple-bg); color: var(--v2-ai-purple); }
</style>
