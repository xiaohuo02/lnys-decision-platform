<template>
  <div class="es" :style="{ minHeight: height }">
    <div class="es__icon">
      <slot name="icon">
        <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
          <rect x="4" y="8" width="40" height="32" rx="4" stroke="currentColor" stroke-width="2" fill="none"/>
          <path d="M4 16h40M16 8v8" stroke="currentColor" stroke-width="2"/>
          <circle cx="24" cy="30" r="4" stroke="currentColor" stroke-width="2"/>
          <path d="M20 34l-3 3M28 34l3 3" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
      </slot>
    </div>
    <p class="es__title">{{ title }}</p>
    <p v-if="desc" class="es__desc">{{ desc }}</p>
    <div v-if="$slots.default" class="es__action"><slot /></div>
  </div>
</template>

<script setup>
defineProps({
  title:  { type: String, default: '暂无数据' },
  desc:   { type: String, default: '' },
  height: { type: String, default: '240px' },
})
</script>

<style scoped>
.es {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: var(--v2-space-8);
}
.es__icon { color: var(--v2-gray-300); margin-bottom: var(--v2-space-4); }
.es__title {
  font-size: var(--v2-text-md);
  color: var(--v2-text-2);
  font-weight: var(--v2-font-medium);
  margin: 0;
}
.es__desc {
  font-size: var(--v2-text-sm);
  color: var(--v2-text-3);
  margin: var(--v2-space-1) 0 0;
  max-width: 320px;
}
.es__action { margin-top: var(--v2-space-4); }
</style>
