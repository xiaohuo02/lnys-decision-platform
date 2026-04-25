<template>
  <div
    class="v2-select"
    :class="[`v2-select--${size}`, { 'v2-select--open': open, 'v2-select--disabled': disabled }]"
    ref="selectEl"
  >
    <div class="v2-select__trigger" @click="toggle">
      <span v-if="selectedLabel" class="v2-select__value">{{ selectedLabel }}</span>
      <span v-else class="v2-select__placeholder">{{ placeholder }}</span>
      <svg class="v2-select__arrow" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M6 9l6 6 6-6"/></svg>
    </div>
    <Transition name="v2-select-pop">
      <div v-if="open" class="v2-select__dropdown">
        <div
          v-if="clearable && modelValue != null && modelValue !== ''"
          class="v2-select__option v2-select__option--clear"
          @click="select(null)"
        >清除</div>
        <div
          v-for="opt in normalizedOptions" :key="opt.value"
          class="v2-select__option"
          :class="{ 'v2-select__option--active': opt.value === modelValue }"
          @click="select(opt.value)"
        >{{ opt.label }}</div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  modelValue:  { default: null },
  options:     { type: Array, default: () => [] },
  placeholder: { type: String, default: '请选择' },
  size:        { type: String, default: 'md', validator: v => ['sm', 'md', 'lg'].includes(v) },
  disabled:    { type: Boolean, default: false },
  clearable:   { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'change'])

const open = ref(false)
const selectEl = ref(null)

const normalizedOptions = computed(() =>
  props.options.map(o => typeof o === 'object' ? o : { label: String(o), value: o })
)

const selectedLabel = computed(() => {
  const found = normalizedOptions.value.find(o => o.value === props.modelValue)
  return found?.label || ''
})

function toggle() {
  if (props.disabled) return
  open.value = !open.value
}

function select(val) {
  emit('update:modelValue', val)
  emit('change', val)
  open.value = false
}

function onClickOutside(e) {
  if (selectEl.value && !selectEl.value.contains(e.target)) {
    open.value = false
  }
}

onMounted(() => document.addEventListener('click', onClickOutside))
onUnmounted(() => document.removeEventListener('click', onClickOutside))
</script>

<style scoped>
.v2-select {
  position: relative;
  display: inline-flex;
  min-width: 120px;
}
.v2-select--disabled { opacity: 0.5; pointer-events: none; }

.v2-select__trigger {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  background: var(--v2-bg-card);
  border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-btn);
  cursor: pointer;
  transition: border-color var(--v2-trans-fast);
}
.v2-select--open .v2-select__trigger { border-color: var(--v2-text-3); }
.v2-select__trigger:hover { border-color: var(--v2-border-3); }

.v2-select--sm .v2-select__trigger { height: 28px; padding: 0 8px; font-size: var(--v2-text-xs); }
.v2-select--md .v2-select__trigger { height: 32px; padding: 0 10px; font-size: var(--v2-text-sm); }
.v2-select--lg .v2-select__trigger { height: 38px; padding: 0 14px; font-size: var(--v2-text-sm); }

.v2-select__value {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--v2-text-1);
}
.v2-select__placeholder {
  flex: 1;
  color: var(--v2-text-4);
}

.v2-select__arrow {
  flex-shrink: 0;
  color: var(--v2-text-4);
  transition: transform var(--v2-trans-fast);
}
.v2-select--open .v2-select__arrow { transform: rotate(180deg); }

.v2-select__dropdown {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  z-index: var(--v2-z-dropdown);
  background: var(--v2-bg-elevated);
  border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-md);
  padding: 4px;
  max-height: 240px;
  overflow-y: auto;
}

.v2-select__option {
  padding: 6px 10px;
  font-size: var(--v2-text-sm);
  color: var(--v2-text-2);
  border-radius: calc(var(--v2-radius-md) - 2px);
  cursor: pointer;
  transition: var(--v2-trans-fast);
}
.v2-select__option:hover { background: var(--v2-bg-hover); color: var(--v2-text-1); }
.v2-select__option--active { color: var(--v2-text-1); font-weight: var(--v2-font-semibold); }
.v2-select__option--clear { color: var(--v2-text-4); font-size: var(--v2-text-xs); }

/* Pop transition */
.v2-select-pop-enter-active { transition: opacity .15s ease, transform .15s cubic-bezier(0.16,1,0.3,1); }
.v2-select-pop-leave-active { transition: opacity .1s ease, transform .1s ease; }
.v2-select-pop-enter-from,
.v2-select-pop-leave-to { opacity: 0; transform: translateY(-4px); }
</style>
