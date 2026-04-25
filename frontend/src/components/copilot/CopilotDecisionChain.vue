<template>
  <div v-if="steps.length" class="dc">
    <div class="dc__hd">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 2v20M2 12h20"/><circle cx="12" cy="6" r="2"/><circle cx="12" cy="18" r="2"/></svg>
      <span class="dc__title">决策链</span>
      <span class="dc__count">{{ steps.length }} 步</span>
    </div>
    <div class="dc__track">
      <div
        v-for="(s, i) in steps" :key="i"
        class="dc__step"
        :class="'dc__step--' + stepType(s.step)"
      >
        <div class="dc__line" v-if="i > 0"></div>
        <div class="dc__dot">
          <svg v-if="stepType(s.step) === 'security'" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
          <svg v-else-if="stepType(s.step) === 'context'" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
          <svg v-else-if="stepType(s.step) === 'routing'" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M16 3h5v5M4 20L21 3"/></svg>
          <svg v-else-if="stepType(s.step) === 'skill'" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/></svg>
          <svg v-else-if="stepType(s.step) === 'cache'" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
          <svg v-else width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="3"/></svg>
        </div>
        <div class="dc__body">
          <span class="dc__label">{{ stepLabel(s.step) }}</span>
          <span class="dc__detail" v-if="s.detail">{{ s.detail }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  steps: { type: Array, default: () => [] },
})

const STEP_LABELS = {
  routing: '意图路由',
  skill_exec: 'Skill 执行',
  synthesize: 'LLM 综合',
  cache_hit: '缓存命中',
  output_pii: 'PII 检测',
}
function stepLabel(step) { return STEP_LABELS[step] || step }

function stepType(step) {
  if (step.includes('security') || step.includes('pii')) return 'security'
  if (step.includes('context') || step.includes('compact')) return 'context'
  if (step.includes('routing')) return 'routing'
  if (step.includes('skill') || step.includes('synthesize')) return 'skill'
  if (step.includes('cache')) return 'cache'
  return 'default'
}
</script>

<style scoped>
.dc { padding: 8px 0; }
.dc__hd { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; color: var(--v2-text-2); }
.dc__title { font-size: 12px; font-weight: 600; }
.dc__count { font-size: 10px; color: var(--v2-text-4); margin-left: auto; }

.dc__track { display: flex; flex-direction: column; padding-left: 4px; }

.dc__step { display: flex; align-items: flex-start; gap: 8px; position: relative; min-height: 28px; }
.dc__line { position: absolute; left: 8px; top: -6px; width: 1px; height: 8px; background: var(--v2-border-2); }

.dc__dot {
  width: 18px; height: 18px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  background: var(--v2-bg-2); border: 1px solid var(--v2-border-1);
  transition: all 0.3s;
}
.dc__step--security .dc__dot { border-color: var(--v2-warning, #f59e0b); color: var(--v2-warning, #f59e0b); }
.dc__step--context .dc__dot { border-color: var(--v2-info, #3b82f6); color: var(--v2-info, #3b82f6); }
.dc__step--routing .dc__dot { border-color: var(--v2-text-1); color: var(--v2-text-1); }
.dc__step--skill .dc__dot { border-color: var(--v2-success); color: var(--v2-success); }
.dc__step--cache .dc__dot { border-color: var(--v2-success); color: var(--v2-success); background: color-mix(in srgb, var(--v2-success) 10%, transparent); }

.dc__body { display: flex; flex-direction: column; gap: 1px; padding-top: 1px; min-width: 0; }
.dc__label { font-size: 11px; font-weight: 500; color: var(--v2-text-1); white-space: nowrap; }
.dc__detail { font-size: 10px; color: var(--v2-text-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 200px; }

/* Enter animation */
.dc__step { animation: dc-in 0.3s ease-out both; }
@keyframes dc-in { from { opacity: 0; transform: translateX(-8px); } to { opacity: 1; transform: translateX(0); } }
</style>
