<template>
  <div class="sk" :style="{ minHeight: height }">
    <div v-for="r in rows" :key="r" class="sk__row">
      <div
        v-for="c in columns"
        :key="c"
        class="sk__cell"
        :style="{ width: cellWidth(c), height: cellHeight(r) }"
      />
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  rows:    { type: Number, default: 4 },
  columns: { type: Number, default: 1 },
  height:  { type: String, default: 'auto' },
})

function cellWidth(c) {
  if (props.columns === 1) return c === 1 ? '75%' : '100%'
  return '100%'
}
function cellHeight(r) {
  return r === 1 ? '16px' : '12px'
}
</script>

<style scoped>
.sk { padding: var(--v2-space-5); }

.sk__row {
  display: flex;
  gap: var(--v2-space-3);
  margin-bottom: var(--v2-space-3);
}
.sk__row:last-child { margin-bottom: 0; }

.sk__cell {
  background: var(--v2-gray-100);
  border-radius: var(--v2-radius-sm);
  animation: sk-pulse 1.5s ease-in-out infinite;
}

@keyframes sk-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: .4; }
}
</style>
