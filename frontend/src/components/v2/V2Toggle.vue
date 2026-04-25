<template>
  <button
    class="v2-toggle"
    :class="{ 'v2-toggle--on': modelValue, 'v2-toggle--disabled': disabled }"
    role="switch"
    :aria-checked="modelValue"
    @click="toggle"
  >
    <span class="v2-toggle__track">
      <span class="v2-toggle__thumb" />
    </span>
    <span v-if="label" class="v2-toggle__label">{{ label }}</span>
  </button>
</template>

<script setup>
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  disabled:   { type: Boolean, default: false },
  label:      { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'change'])

function toggle() {
  if (props.disabled) return
  const next = !props.modelValue
  emit('update:modelValue', next)
  emit('change', next)
}
</script>

<style scoped>
.v2-toggle {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 0;
}
.v2-toggle--disabled { opacity: 0.4; cursor: not-allowed; }

.v2-toggle__track {
  width: 36px;
  height: 20px;
  border-radius: 10px;
  background: var(--v2-border-2);
  position: relative;
  transition: background var(--v2-trans-fast);
  flex-shrink: 0;
}
.v2-toggle--on .v2-toggle__track { background: var(--v2-text-1); }

.v2-toggle__thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--v2-bg-card);
  transition: transform var(--v2-trans-fast);
}
.v2-toggle--on .v2-toggle__thumb { transform: translateX(16px); }

.v2-toggle__label {
  font-size: var(--v2-text-sm);
  color: var(--v2-text-2);
  user-select: none;
}
</style>
