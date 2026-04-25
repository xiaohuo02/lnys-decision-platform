<template>
  <div v-if="checks.length" class="sb">
    <div
      v-for="(c, i) in checks" :key="i"
      class="sb__item"
      :class="{ 'sb__item--fail': !c.passed }"
    >
      <div class="sb__icon">
        <!-- Shield icon -->
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
        </svg>
      </div>
      <div class="sb__body">
        <span class="sb__type">{{ typeLabel(c.check_type) }}</span>
        <span class="sb__status" :class="c.passed ? 'sb__status--pass' : 'sb__status--fail'">
          {{ c.passed ? 'PASS' : 'BLOCKED' }}
        </span>
      </div>
      <div v-if="c.hits && c.hits.length" class="sb__hits">
        <span v-for="(h, j) in c.hits.slice(0, 3)" :key="j" class="sb__hit">
          {{ h.rule }}: {{ h.message }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  checks: { type: Array, default: () => [] },
})

function typeLabel(t) {
  const map = {
    input_guard: '输入安全',
    output_pii_scan: '输出 PII',
  }
  return map[t] || t
}
</script>

<style scoped>
.sb { display: flex; flex-direction: column; gap: 4px; }

.sb__item {
  display: flex; flex-wrap: wrap; align-items: center; gap: 6px;
  padding: 4px 8px; border-radius: 6px;
  background: color-mix(in srgb, var(--v2-success) 6%, transparent);
  border: 1px solid color-mix(in srgb, var(--v2-success) 20%, transparent);
  transition: all 0.3s;
}
.sb__item--fail {
  background: color-mix(in srgb, var(--v2-error) 6%, transparent);
  border-color: color-mix(in srgb, var(--v2-error) 20%, transparent);
}

.sb__icon { color: var(--v2-success); display: flex; flex-shrink: 0; }
.sb__item--fail .sb__icon { color: var(--v2-error); }

.sb__body { display: flex; align-items: center; gap: 6px; }
.sb__type { font-size: 11px; font-weight: 500; color: var(--v2-text-1); }
.sb__status { font-size: 9px; font-weight: 700; letter-spacing: 0.5px; padding: 1px 5px; border-radius: 3px; }
.sb__status--pass { color: var(--v2-success); background: color-mix(in srgb, var(--v2-success) 12%, transparent); }
.sb__status--fail { color: var(--v2-error); background: color-mix(in srgb, var(--v2-error) 12%, transparent); }

.sb__hits { width: 100%; display: flex; flex-direction: column; gap: 1px; padding-left: 18px; }
.sb__hit { font-size: 10px; color: var(--v2-text-3); }
</style>
