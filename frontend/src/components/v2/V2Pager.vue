<template>
  <div class="v2-pager" v-if="totalPages > 1">
    <button class="v2-pager__btn" :disabled="modelValue <= 1" @click="go(modelValue - 1)">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M15 18l-6-6 6-6"/></svg>
    </button>

    <template v-for="p in visiblePages" :key="p">
      <span v-if="p === '...'" class="v2-pager__dots">…</span>
      <button v-else class="v2-pager__btn v2-pager__btn--page" :class="{ 'v2-pager__btn--active': p === modelValue }" @click="go(p)">{{ p }}</button>
    </template>

    <button class="v2-pager__btn" :disabled="modelValue >= totalPages" @click="go(modelValue + 1)">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M9 18l6-6-6-6"/></svg>
    </button>

    <span class="v2-pager__info">{{ total }} 条</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: { type: Number, default: 1 },
  total:      { type: Number, default: 0 },
  pageSize:   { type: Number, default: 20 },
})
const emit = defineEmits(['update:modelValue', 'change'])

const totalPages = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)))

const visiblePages = computed(() => {
  const total = totalPages.value
  const current = props.modelValue
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1)

  const pages = []
  pages.push(1)
  if (current > 3) pages.push('...')
  for (let i = Math.max(2, current - 1); i <= Math.min(total - 1, current + 1); i++) {
    pages.push(i)
  }
  if (current < total - 2) pages.push('...')
  pages.push(total)
  return pages
})

function go(page) {
  if (page < 1 || page > totalPages.value) return
  emit('update:modelValue', page)
  emit('change', page)
}
</script>

<style scoped>
.v2-pager {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: var(--v2-text-xs);
}

.v2-pager__btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: var(--v2-border-width) solid transparent;
  border-radius: var(--v2-radius-btn);
  color: var(--v2-text-3);
  cursor: pointer;
  font-family: var(--v2-font-mono);
  font-size: var(--v2-text-xs);
  transition: var(--v2-trans-fast);
}
.v2-pager__btn:hover:not(:disabled) { color: var(--v2-text-1); background: var(--v2-bg-hover); }
.v2-pager__btn:disabled { opacity: 0.3; cursor: default; }
.v2-pager__btn--active {
  color: var(--v2-text-1);
  font-weight: var(--v2-font-semibold);
  border-color: var(--v2-border-2);
}

.v2-pager__dots {
  width: 28px;
  text-align: center;
  color: var(--v2-text-4);
  user-select: none;
}

.v2-pager__info {
  margin-left: 8px;
  color: var(--v2-text-4);
  font-variant-numeric: tabular-nums;
}
</style>
