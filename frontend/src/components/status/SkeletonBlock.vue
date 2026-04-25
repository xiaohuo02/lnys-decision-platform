<template>
  <div class="sk" :style="{ minHeight: height }">
    <div class="sk__bar sk__bar--title" />
    <div class="sk__row" v-for="n in rows" :key="n">
      <div class="sk__bar sk__bar--cell" v-for="c in cols" :key="c" :style="{ width: cellWidth(c) }" />
    </div>
  </div>
</template>

<script setup>
defineProps({
  rows:   { type: Number, default: 5 },
  cols:   { type: Number, default: 4 },
  height: { type: String, default: '200px' },
})

function cellWidth(col) {
  const widths = ['60%', '80%', '45%', '70%', '55%']
  return widths[(col - 1) % widths.length]
}
</script>

<style scoped>
.sk { padding: 16px; }
.sk__row { display: flex; gap: 12px; margin-bottom: 12px; }
.sk__bar {
  height: 14px;
  border-radius: var(--radius-sm, 4px);
  background: linear-gradient(90deg, var(--color-bg-hover, #f5f5f5) 25%, var(--color-border-light, #f0f0f0) 50%, var(--color-bg-hover, #f5f5f5) 75%);
  background-size: 200% 100%;
  animation: sk-shimmer 1.5s infinite ease-in-out;
}
.sk__bar--title { width: 30%; height: 18px; margin-bottom: 16px; }
.sk__bar--cell { flex: 1; }

@keyframes sk-shimmer {
  0%   { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
</style>
