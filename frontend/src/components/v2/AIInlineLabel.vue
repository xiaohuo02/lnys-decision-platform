<template>
  <span class="ai-label" :class="[`ai-label--${size}`]">
    <svg class="ai-label__icon" width="12" height="12" viewBox="0 0 16 16" fill="none">
      <path d="M8 1l1.5 3.5L13 6l-3.5 1.5L8 11 6.5 7.5 3 6l3.5-1.5L8 1z" fill="currentColor"/>
      <path d="M12 10l.75 1.75L14.5 12.5l-1.75.75L12 15l-.75-1.75L9.5 12.5l1.75-.75L12 10z" fill="currentColor" opacity=".6"/>
    </svg>
    <span class="ai-label__text"><slot>{{ text }}</slot></span>
  </span>
</template>

<script setup>
defineProps({
  text: { type: String, default: 'AI 生成' },
  size: { type: String, default: 'sm', validator: v => ['xs', 'sm', 'md'].includes(v) },
})
</script>

<style scoped>
.ai-label {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  border-radius: var(--v2-radius-sm);
  font-weight: var(--v2-font-medium);
  color: var(--v2-ai-purple);
  background: var(--v2-ai-purple-bg);
  white-space: nowrap;
  vertical-align: middle;
}
.ai-label--xs { font-size: var(--v2-text-2xs); padding: 0 4px; height: 18px; }
.ai-label--sm { font-size: var(--v2-text-xs);  padding: 1px 6px; height: 20px; }
.ai-label--md { font-size: var(--v2-text-sm);  padding: 2px 8px; height: 24px; }

.ai-label__icon { flex-shrink: 0; }
</style>
