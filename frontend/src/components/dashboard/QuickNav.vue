<template>
  <div class="quick">
    <div class="quick__hd">
      <span class="quick__title">下一步</span>
      <span class="quick__sub">挑一项开始你的决策</span>
    </div>
    <div class="quick__grid">
      <div
        v-for="(m, i) in cards" :key="m.path"
        class="quick-card"
        :class="{ 'quick-card--primary': m.primary }"
        :style="{ '--i': i }"
        @click="$router.push(m.path)"
      >
        <span class="quick-card__emoji">{{ m.emoji }}</span>
        <div class="quick-card__body">
          <div class="quick-card__title">
            {{ m.title }}
            <span v-if="m.primary" class="quick-card__ai-tag">AI 推荐</span>
          </div>
          <div class="quick-card__desc">{{ m.desc }}</div>
        </div>
        <ChevronRight :size="14" class="quick-card__arrow" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ChevronRight } from 'lucide-vue-next'

defineProps({
  cards: { type: Array, required: true },
})
</script>

<style scoped>
.quick { display: flex; flex-direction: column; gap: 6px; }
.quick__hd { display: flex; align-items: baseline; gap: 10px; padding: 0 2px; }
.quick__title { font-family: var(--v2-font-mono); font-size: 11px; letter-spacing: 0.03em; color: var(--v2-text-3); text-transform: uppercase; }
.quick__sub { font-size: 11px; color: var(--v2-text-4); }
.quick__grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }

.quick-card {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 14px;
  background: var(--v2-bg-card);
  border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-card);
  cursor: pointer;
  transition: transform var(--v2-trans-fast), border-color var(--v2-trans-fast), background var(--v2-trans-fast);
}
.quick-card:hover { border-color: var(--v2-text-1); transform: translateY(-1px); }
.quick-card__emoji { font-size: 22px; flex-shrink: 0; line-height: 1; }
.quick-card__body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.quick-card__title { font-size: 14px; font-weight: var(--v2-font-semibold); color: var(--v2-text-1); letter-spacing: -0.01em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.quick-card__desc { font-size: 11px; line-height: 1.45; color: var(--v2-text-4); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.quick-card__ai-tag {
  display: inline-flex; align-items: center;
  font-family: var(--v2-font-mono); font-size: 9px; font-weight: 600;
  padding: 1px 6px; border-radius: 3px; margin-left: 6px;
  color: #15803d; background: #dcfce7; vertical-align: middle;
}
.quick-card--primary .quick-card__ai-tag { color: #dcfce7; background: rgba(255,255,255,0.2); }
.quick-card__arrow { color: var(--v2-text-4); flex-shrink: 0; transition: transform var(--v2-trans-fast), color var(--v2-trans-fast); }
.quick-card:hover .quick-card__arrow { color: var(--v2-text-1); transform: translateX(2px); }

.quick-card--primary { background: var(--v2-text-1); border-color: var(--v2-text-1); }
.quick-card--primary .quick-card__title { color: var(--v2-bg-page); }
.quick-card--primary .quick-card__desc { color: color-mix(in srgb, var(--v2-bg-page) 70%, transparent); }
.quick-card--primary .quick-card__arrow { color: var(--v2-bg-page); }
.quick-card--primary:hover { background: color-mix(in srgb, var(--v2-text-1) 92%, #000); }

@media (max-width: 768px) { .quick__grid { grid-template-columns: 1fr; } }
</style>
