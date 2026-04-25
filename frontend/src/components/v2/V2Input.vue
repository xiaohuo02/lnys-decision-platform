<template>
  <div class="v2-input" :class="[`v2-input--${size}`, { 'v2-input--focus': focused, 'v2-input--disabled': disabled }]">
    <span v-if="$slots.prefix" class="v2-input__prefix"><slot name="prefix" /></span>
    <input
      ref="inputEl"
      class="v2-input__inner"
      :type="type"
      :value="modelValue"
      :placeholder="placeholder"
      :disabled="disabled"
      :readonly="readonly"
      @input="$emit('update:modelValue', $event.target.value)"
      @focus="focused = true"
      @blur="focused = false; $emit('blur', $event)"
      @keydown.enter="$emit('enter', $event)"
    />
    <span v-if="clearable && modelValue" class="v2-input__clear" @click="$emit('update:modelValue', ''); $emit('clear')">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>
    </span>
    <span v-if="$slots.suffix" class="v2-input__suffix"><slot name="suffix" /></span>
  </div>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  modelValue:  { type: [String, Number], default: '' },
  placeholder: { type: String, default: '' },
  type:        { type: String, default: 'text' },
  size:        { type: String, default: 'md', validator: v => ['sm', 'md', 'lg'].includes(v) },
  disabled:    { type: Boolean, default: false },
  readonly:    { type: Boolean, default: false },
  clearable:   { type: Boolean, default: false },
})
defineEmits(['update:modelValue', 'blur', 'enter', 'clear'])

const focused = ref(false)
const inputEl = ref(null)

defineExpose({ focus: () => inputEl.value?.focus() })
</script>

<style scoped>
.v2-input {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: var(--v2-bg-card);
  border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-btn);
  transition: border-color var(--v2-trans-fast);
  width: 100%;
}
.v2-input--focus { border-color: var(--v2-text-3); }
.v2-input--disabled { opacity: 0.5; pointer-events: none; }

.v2-input--sm { height: 28px; padding: 0 8px; }
.v2-input--md { height: 32px; padding: 0 10px; }
.v2-input--lg { height: 38px; padding: 0 14px; }

.v2-input__inner {
  flex: 1;
  min-width: 0;
  border: none;
  outline: none;
  background: transparent;
  color: var(--v2-text-1);
  font-family: var(--v2-font-sans);
  font-size: var(--v2-text-sm);
}
.v2-input--sm .v2-input__inner { font-size: var(--v2-text-xs); }

.v2-input__inner::placeholder { color: var(--v2-text-4); }

.v2-input__prefix,
.v2-input__suffix {
  display: flex;
  align-items: center;
  color: var(--v2-text-4);
  flex-shrink: 0;
}

.v2-input__clear {
  display: flex;
  align-items: center;
  color: var(--v2-text-4);
  cursor: pointer;
  flex-shrink: 0;
  padding: 2px;
  border-radius: 50%;
  transition: var(--v2-trans-fast);
}
.v2-input__clear:hover { color: var(--v2-text-2); background: var(--v2-bg-hover); }
</style>
