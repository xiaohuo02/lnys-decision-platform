<template>
  <button
    class="v2-btn"
    :class="[
      `v2-btn--${variant}`,
      `v2-btn--${size}`,
      { 'v2-btn--loading': loading, 'v2-btn--block': block, 'v2-btn--icon-only': iconOnly }
    ]"
    :disabled="disabled || loading"
    @click="$emit('click', $event)"
  >
    <span v-if="loading" class="v2-btn__spinner" />
    <slot />
  </button>
</template>

<script setup>
defineProps({
  variant:  { type: String, default: 'secondary', validator: v => ['primary', 'secondary', 'ghost', 'danger'].includes(v) },
  size:     { type: String, default: 'md', validator: v => ['sm', 'md', 'lg'].includes(v) },
  loading:  { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  block:    { type: Boolean, default: false },
  iconOnly: { type: Boolean, default: false },
})
defineEmits(['click'])
</script>

<style scoped>
.v2-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-family: var(--v2-font-sans);
  font-weight: var(--v2-font-medium);
  border-radius: var(--v2-radius-btn);
  cursor: pointer;
  transition: all var(--v2-trans-fast);
  white-space: nowrap;
  user-select: none;
  outline: none;
  line-height: 1;
}
.v2-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.v2-btn--block { width: 100%; }

/* Sizes */
.v2-btn--sm { height: 28px; padding: 0 10px; font-size: var(--v2-text-xs); }
.v2-btn--md { height: 32px; padding: 0 14px; font-size: var(--v2-text-sm); }
.v2-btn--lg { height: 38px; padding: 0 20px; font-size: var(--v2-text-sm); }
.v2-btn--icon-only.v2-btn--sm { width: 28px; padding: 0; }
.v2-btn--icon-only.v2-btn--md { width: 32px; padding: 0; }
.v2-btn--icon-only.v2-btn--lg { width: 38px; padding: 0; }

/* Primary: filled */
.v2-btn--primary {
  background: var(--v2-text-1);
  color: var(--v2-bg-page);
  border: var(--v2-border-width) solid transparent;
}
.v2-btn--primary:hover:not(:disabled) { opacity: 0.85; }
.v2-btn--primary:active:not(:disabled) { opacity: 0.7; transform: scale(0.98); }

/* Secondary: outlined */
.v2-btn--secondary {
  background: transparent;
  color: var(--v2-text-1);
  border: var(--v2-border-width) solid var(--v2-border-2);
}
.v2-btn--secondary:hover:not(:disabled) { border-color: var(--v2-border-3); background: var(--v2-bg-hover); }
.v2-btn--secondary:active:not(:disabled) { background: var(--v2-bg-sunken); }

/* Ghost: no border */
.v2-btn--ghost {
  background: transparent;
  color: var(--v2-text-2);
  border: var(--v2-border-width) solid transparent;
}
.v2-btn--ghost:hover:not(:disabled) { color: var(--v2-text-1); background: var(--v2-bg-hover); }
.v2-btn--ghost:active:not(:disabled) { background: var(--v2-bg-sunken); }

/* Danger: red */
.v2-btn--danger {
  background: transparent;
  color: var(--v2-error);
  border: var(--v2-border-width) solid var(--v2-error);
}
.v2-btn--danger:hover:not(:disabled) { background: var(--v2-error-bg); }
.v2-btn--danger:active:not(:disabled) { opacity: 0.8; }

/* Loading spinner */
.v2-btn__spinner {
  width: 14px;
  height: 14px;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: v2-btn-spin 0.6s linear infinite;
}
.v2-btn--loading { pointer-events: none; }
@keyframes v2-btn-spin { from { transform: rotate(0) } to { transform: rotate(360deg) } }
</style>
