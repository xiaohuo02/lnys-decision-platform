<template>
  <div class="v2-seg" :class="[`v2-seg--${size}`]">
    <button
      v-for="opt in normalizedOptions" :key="opt.value"
      class="v2-seg__btn"
      :class="{ 'v2-seg__btn--active': opt.value === modelValue }"
      @click="select(opt.value)"
    >{{ opt.label }}</button>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: { default: null },
  options:    { type: Array, default: () => [] },
  size:       { type: String, default: 'sm', validator: v => ['sm', 'md'].includes(v) },
})
const emit = defineEmits(['update:modelValue', 'change'])

const normalizedOptions = computed(() =>
  props.options.map(o => typeof o === 'object' ? o : { label: String(o), value: o })
)

function select(val) {
  emit('update:modelValue', val)
  emit('change', val)
}
</script>

<style scoped>
.v2-seg {
  display: inline-flex;
  gap: 2px;
  background: var(--v2-bg-sunken);
  border-radius: var(--v2-radius-btn);
  padding: 2px;
}

.v2-seg__btn {
  font-family: var(--v2-font-mono);
  font-weight: var(--v2-font-medium);
  color: var(--v2-text-3);
  background: transparent;
  border: none;
  border-radius: calc(var(--v2-radius-btn) - 2px);
  cursor: pointer;
  transition: var(--v2-trans-fast);
  white-space: nowrap;
}
.v2-seg--sm .v2-seg__btn { padding: 3px 10px; font-size: var(--v2-text-xs); }
.v2-seg--md .v2-seg__btn { padding: 5px 14px; font-size: var(--v2-text-sm); }

.v2-seg__btn:hover { color: var(--v2-text-1); }
.v2-seg__btn--active {
  color: var(--v2-text-1);
  background: var(--v2-bg-card);
  font-weight: var(--v2-font-semibold);
}
</style>
