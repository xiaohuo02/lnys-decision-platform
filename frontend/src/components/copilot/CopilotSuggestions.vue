<template>
  <div class="cop-sug" v-if="items.length">
    <button
      v-for="(item, i) in items"
      :key="i"
      class="cop-sug__btn"
      :class="{ 'cop-sug__btn--action': item.type === 'action' }"
      @click="$emit('select', item)"
    >
      <svg v-if="item.type === 'action'" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
      <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3M12 17h.01"/></svg>
      <span>{{ item.label }}</span>
    </button>
  </div>
</template>

<script setup>
defineProps({ items: { type: Array, default: () => [] } })
defineEmits(['select'])
</script>

<style scoped>
.cop-sug { display: flex; flex-wrap: wrap; gap: 6px; margin: 12px 0; }
.cop-sug__btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 14px; border: 1px solid rgba(0,0,0,0.08); border-radius: 999px;
  background: #fff; font-size: 13px; color: #18181b; cursor: pointer;
  transition: all 0.15s ease;
}
.cop-sug__btn:hover { background: #fafafa; border-color: rgba(0,0,0,0.15); }
.cop-sug__btn--action { border-color: rgba(24,24,27,0.2); font-weight: 500; }
.cop-sug__btn--action:hover { background: #18181b; color: #fff; }
</style>
