<template>
  <div class="kpi-grid">
    <ClickToAsk
      v-for="(k, i) in items" :key="k.key"
      :question="k.aiQ || `分析${k.label}的趋势和影响因素`"
      :style="{ '--i': i }"
      @ask="$emit('ask-ai', $event)"
    >
      <div class="kpi" :class="[{ 'kpi--hero': k.hero }, `kpi--sev-${k.severity || 'ok'}`]">
        <!-- C-γ: severity 异常时显示委托 AI 按钮 -->
        <button
          v-if="k.severity && k.severity !== 'ok' && k.value != null"
          class="kpi__delegate"
          title="让 AI 异步归因（任务可在右上角查看进度）"
          @click.stop="handleDelegate(k)"
          :disabled="delegating[k.key]"
        >
          <Sparkles :size="11" :class="{ 'is-spin': delegating[k.key] }" />
          <span>{{ delegating[k.key] ? '委派中…' : '委托 AI' }}</span>
        </button>
        <div class="kpi__val">
          <template v-if="k.value != null">
            <span v-if="k.prefix" class="kpi__prefix">{{ k.prefix }}</span>
            <Odometer :value="k.value" :decimals="k.decimals || 0" />
            <span v-if="k.suffix" class="kpi__suffix">{{ k.suffix }}</span>
          </template>
          <span v-else class="kpi__empty">—</span>
        </div>
        <div class="kpi__label">
          <span>{{ k.label }}</span>
          <span v-if="k.severity === 'critical'" class="kpi__sev-tag kpi__sev-tag--critical">严重偏离</span>
          <span v-else-if="k.severity === 'warn'" class="kpi__sev-tag kpi__sev-tag--warn">注意</span>
        </div>
        <div class="kpi__sub">
          {{ k.sub }}
          <button
            v-if="k.actionLabel"
            class="kpi__action"
            @click.stop="k.actionLink ? $router.push(k.actionLink) : $emit('ask-ai', { question: k.aiQ })"
          >
            {{ k.actionLabel }}
            <ChevronRight :size="11" />
          </button>
        </div>
      </div>
    </ClickToAsk>
  </div>
</template>

<script setup>
import { reactive } from 'vue'
import { ChevronRight, Sparkles } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import { ClickToAsk, Odometer } from '@/components/v2'
import { useRunStore } from '@/stores/useRunStore'
import { workflowApi } from '@/api/workflow'

defineProps({
  items: { type: Array, required: true },
})
defineEmits(['ask-ai'])

const runStore = useRunStore()
const delegating = reactive({})

/**
 * C-γ.2: 委托 AI 异步分析指定 KPI 异常
 * 触发 business_overview workflow，让 AI 综合多维度做归因；
 * 任务进度和结果通过 Header RunTicker 跟踪。
 */
async function handleDelegate(k) {
  if (delegating[k.key]) return
  delegating[k.key] = true
  try {
    const request_text = k.aiQ || `分析${k.label}的异常原因和影响因素`
    const res = await workflowApi.run({
      request_text,
      request_type: 'business_overview',
      use_mock: false,
    })
    const runId = res?.run_id || res?.data?.run_id
    if (!runId) throw new Error('未获取到 run_id')
    runStore.track({
      runId,
      streamUrl: `/api/v1/workflows/${runId}/stream`,
      route: 'business_overview',
      query: request_text,
      origin: 'kpi_delegate',
    })
    ElMessage.success(`已交给 AI 分析「${k.label}」，可在右上角任务栏查看进度`)
  } catch (e) {
    console.error('[KpiGrid] delegate failed:', e)
    ElMessage.error(e?.message || '委托失败，请稍后重试')
  } finally {
    delegating[k.key] = false
  }
}
</script>

<style scoped>
.kpi-grid {
  display: grid; grid-template-columns: 1.4fr repeat(3, 1fr); gap: 1px;
  background: var(--v2-border-2); border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-card); overflow: hidden;
}
.kpi {
  padding: 12px 14px; background: var(--v2-bg-card);
  display: flex; flex-direction: column; gap: 3px;
  position: relative;
  transition: background var(--v2-trans-fast);
}
.kpi__val {
  font-size: 22px; font-weight: var(--v2-font-semibold); color: var(--v2-text-1);
  font-variant-numeric: tabular-nums; letter-spacing: -0.02em; line-height: 1.2;
  display: flex; align-items: baseline;
}
.kpi__prefix { font-size: 15px; color: var(--v2-text-3); margin-right: 1px; }
.kpi__suffix { font-size: 12px; color: var(--v2-text-3); margin-left: 2px; }
.kpi__empty  { font-size: 20px; color: var(--v2-text-4); font-weight: 400; }

/* C-γ: delegate 按钮（委托 AI 异步归因） */
.kpi__delegate {
  position: absolute; top: 8px; right: 8px;
  display: inline-flex; align-items: center; gap: 4px;
  padding: 3px 8px;
  font-family: inherit; font-size: 10px; font-weight: var(--v2-font-medium);
  color: var(--v2-text-1);
  background: var(--v2-bg-card);
  border: 1px solid var(--v2-border-1);
  border-radius: var(--v2-radius-pill);
  cursor: pointer;
  transition: all var(--v2-trans-fast);
  opacity: 0.8;
}
.kpi__delegate:hover { opacity: 1; background: var(--v2-text-1); color: var(--v2-bg-card); border-color: var(--v2-text-1); }
.kpi__delegate:disabled { opacity: 0.5; cursor: not-allowed; }
.kpi__delegate .is-spin { animation: kpi-delegate-spin 0.8s linear infinite; }
@keyframes kpi-delegate-spin { to { transform: rotate(360deg); } }
.kpi__label {
  font-family: var(--v2-font-mono); font-size: 11px; letter-spacing: 0.03em;
  color: var(--v2-text-3); white-space: nowrap;
  display: flex; align-items: center; gap: 6px;
}
.kpi__sev-tag {
  font-family: var(--v2-font-mono); font-size: 9px; font-weight: 600;
  padding: 1px 5px; border-radius: 3px;
}
.kpi__sev-tag--critical { color: #fff; background: var(--v2-error, #dc2626); }
.kpi__sev-tag--warn     { color: var(--v2-warning-text, #92400e); background: var(--v2-warning-bg, #fef3c7); }
.kpi__sub {
  font-size: 12px; color: var(--v2-text-4); white-space: nowrap;
  display: flex; align-items: center; gap: 8px;
}
.kpi__action {
  display: inline-flex; align-items: center; gap: 2px;
  font-family: inherit; font-size: 11px; font-weight: var(--v2-font-medium);
  color: var(--v2-text-1); border: none; background: transparent;
  padding: 2px 0; cursor: pointer;
  border-bottom: 1px solid currentColor; transition: opacity 0.15s;
}
.kpi__action:hover { opacity: 0.7; }

.kpi--sev-warn {
  background: linear-gradient(135deg,
    color-mix(in srgb, var(--v2-warning, #f59e0b) 8%, var(--v2-bg-card)) 0%,
    var(--v2-bg-card) 60%);
}
.kpi--sev-warn .kpi__val { color: var(--v2-warning-text, #92400e); }

.kpi--sev-critical {
  background: linear-gradient(135deg,
    color-mix(in srgb, var(--v2-error, #dc2626) 10%, var(--v2-bg-card)) 0%,
    var(--v2-bg-card) 60%);
  animation: kpi-pulse-critical 2.4s ease-in-out infinite;
}
.kpi--sev-critical .kpi__val { color: var(--v2-error, #dc2626); }
.kpi--sev-critical .kpi__action { color: var(--v2-error, #dc2626); }

@keyframes kpi-pulse-critical {
  0%, 100% { box-shadow: inset 0 0 0 0 transparent; }
  50%      { box-shadow: inset 0 0 0 2px color-mix(in srgb, var(--v2-error, #dc2626) 35%, transparent); }
}
@media (prefers-reduced-motion: reduce) { .kpi--sev-critical { animation: none; } }

.kpi--hero { padding: 14px 18px; gap: 4px; }
.kpi--hero:not(.kpi--sev-warn):not(.kpi--sev-critical) {
  background: linear-gradient(140deg, var(--v2-bg-hover) 0%, var(--v2-bg-card) 55%);
}
.kpi--hero .kpi__val { font-size: 28px; }
.kpi--hero .kpi__prefix { font-size: 16px; }
.kpi--hero .kpi__label { font-size: 11px; color: var(--v2-text-2); font-weight: var(--v2-font-medium); }
.kpi--hero .kpi__sub { font-size: 12px; }

@media (max-width: 1024px) {
  .kpi-grid { grid-template-columns: repeat(2, 1fr); }
  .kpi--hero { grid-column: span 2; }
}
@media (max-width: 768px) {
  .kpi-grid { grid-template-columns: repeat(2, 1fr); }
  .kpi--hero { grid-column: span 2; padding: 14px 16px; }
  .kpi--hero .kpi__val { font-size: 24px; }
  .kpi--hero .kpi__prefix { font-size: 14px; }
}
</style>
