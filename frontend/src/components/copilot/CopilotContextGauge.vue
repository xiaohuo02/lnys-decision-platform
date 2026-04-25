<template>
  <div v-if="ctx" class="cg" :class="'cg--' + ctx.status">
    <div class="cg__ring-wrap">
      <svg class="cg__ring" viewBox="0 0 36 36">
        <path class="cg__ring-bg"
          d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
          fill="none" stroke-width="3" />
        <path class="cg__ring-fg"
          d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
          fill="none" stroke-width="3"
          :stroke-dasharray="`${pct}, 100`" />
      </svg>
      <span class="cg__pct">{{ Math.round(pct) }}%</span>
    </div>
    <div class="cg__info">
      <span class="cg__label">{{ statusLabel }}</span>
      <span class="cg__tokens">{{ formatK(ctx.tokens) }} / {{ formatK(ctx.max_tokens) }}</span>
      <span v-if="ctx.compacted" class="cg__compact-badge">
        已压缩 {{ formatK(ctx.tokens_before) }} → {{ formatK(ctx.tokens_after) }}
      </span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  ctx: { type: Object, default: null },
})

const pct = computed(() => props.ctx?.usage_pct || 0)
const statusLabel = computed(() => {
  const s = props.ctx?.status
  if (s === 'healthy') return '上下文健康'
  if (s === 'compacted') return '已自动压缩'
  if (s === 'needs_compact') return '需要压缩'
  if (s === 'circuit_break') return '已熔断'
  return s || ''
})

function formatK(n) {
  if (!n) return '0'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}
</script>

<style scoped>
.cg { display: flex; align-items: center; gap: 8px; padding: 6px 10px; border-radius: 8px; background: var(--v2-bg-2); border: 1px solid var(--v2-border-1); transition: all 0.3s; }
.cg--healthy { border-color: var(--v2-success); }
.cg--compacted { border-color: var(--v2-info, #3b82f6); }
.cg--needs_compact { border-color: var(--v2-warning, #f59e0b); }
.cg--circuit_break { border-color: var(--v2-error); }

.cg__ring-wrap { position: relative; width: 36px; height: 36px; flex-shrink: 0; }
.cg__ring { width: 36px; height: 36px; transform: rotate(-90deg); }
.cg__ring-bg { stroke: var(--v2-border-2); }
.cg__ring-fg { stroke: var(--v2-success); stroke-linecap: round; transition: stroke-dasharray 0.6s ease, stroke 0.3s; }
.cg--needs_compact .cg__ring-fg { stroke: var(--v2-warning, #f59e0b); }
.cg--circuit_break .cg__ring-fg { stroke: var(--v2-error); }
.cg--compacted .cg__ring-fg { stroke: var(--v2-info, #3b82f6); }

.cg__pct { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; font-size: 8px; font-weight: 700; color: var(--v2-text-1); }

.cg__info { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.cg__label { font-size: 11px; font-weight: 600; color: var(--v2-text-1); }
.cg__tokens { font-size: 10px; color: var(--v2-text-3); font-family: var(--v2-font-mono, monospace); }
.cg__compact-badge { font-size: 9px; color: var(--v2-info, #3b82f6); font-family: var(--v2-font-mono, monospace); }
</style>
