<template>
  <div class="sys-kpi-row">
    <div
      v-for="(s, i) in items" :key="s.key"
      class="sys-kpi" :class="`sys-kpi--sev-${s.severity || 'ok'}`"
      :style="{ '--i': i }"
      @click="handleClick(s)"
    >
      <div class="sys-kpi__val">
        <template v-if="s.value != null">
          <Odometer :value="s.value" :decimals="0" />
          <span v-if="s.suffix" class="sys-kpi__suffix">{{ s.suffix }}</span>
        </template>
        <span v-else class="sys-kpi__empty">—</span>
      </div>
      <div class="sys-kpi__meta">
        <span class="sys-kpi__label">{{ s.label }}</span>
        <span v-if="s.sub" class="sys-kpi__sub">{{ s.sub }}</span>
      </div>
      <button
        v-if="s.actionLabel"
        class="sys-kpi__action"
        @click.stop="s.actionLink ? $router.push(s.actionLink) : null"
      >
        {{ s.actionLabel }} <ChevronRight :size="11" />
      </button>
    </div>
  </div>
</template>

<script setup>
import { ChevronRight } from 'lucide-vue-next'
import { Odometer } from '@/components/v2'

const props = defineProps({
  items: { type: Array, required: true },
})
const emit = defineEmits(['ask-ai'])

function handleClick(s) {
  if (s.actionLink) {
    // router.push handled via <button>
  } else if (s.aiQ) {
    emit('ask-ai', { question: s.aiQ })
  }
}
</script>

<style scoped>
.sys-kpi-row {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px;
  background: var(--v2-border-2); border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-card); overflow: hidden;
}
.sys-kpi {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 14px; background: var(--v2-bg-card);
  cursor: pointer; transition: background var(--v2-trans-fast);
}
.sys-kpi:hover { background: var(--v2-bg-hover); }
.sys-kpi__val {
  font-family: var(--v2-font-mono); font-size: 18px; font-weight: var(--v2-font-semibold);
  color: var(--v2-text-2); letter-spacing: -0.01em;
  display: flex; align-items: baseline; min-width: 60px;
}
.sys-kpi__suffix { font-size: 10px; color: var(--v2-text-4); margin-left: 2px; }
.sys-kpi__empty  { color: var(--v2-text-4); font-weight: 400; }
.sys-kpi__meta { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.sys-kpi__label { font-size: 11px; color: var(--v2-text-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sys-kpi__sub { font-size: 10px; color: var(--v2-text-4); font-family: var(--v2-font-mono); white-space: nowrap; }
.sys-kpi__action {
  display: inline-flex; align-items: center; gap: 2px;
  font-family: inherit; font-size: 10px; font-weight: var(--v2-font-medium);
  color: var(--v2-text-1); border: none; background: transparent;
  padding: 2px 4px; border-radius: var(--v2-radius-pill); cursor: pointer;
  flex-shrink: 0;
}
.sys-kpi__action:hover { background: color-mix(in srgb, var(--v2-text-1) 8%, transparent); }

.sys-kpi--sev-warn     { border-left: 2px solid var(--v2-warning, #f59e0b); }
.sys-kpi--sev-critical { border-left: 2px solid var(--v2-error, #dc2626); }
.sys-kpi--sev-critical .sys-kpi__val { color: var(--v2-error, #dc2626); }

@media (max-width: 768px) {
  .sys-kpi-row { grid-template-columns: 1fr; }
}
</style>
