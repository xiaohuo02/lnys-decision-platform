<template>
  <div class="stl">
    <!-- Overall progress bar -->
    <div v-if="showProgress" class="stl__progress">
      <div class="stl__progress-bar">
        <div class="stl__progress-fill" :style="{ width: progressPct + '%' }" />
      </div>
      <span class="stl__progress-text">{{ progressPct }}%</span>
    </div>

    <!-- Step list -->
    <div class="stl__list">
      <div
        v-for="(step, idx) in normalizedSteps"
        :key="step.name"
        class="stl__item"
        :class="`stl__item--${step.status}`"
      >
        <div class="stl__rail">
          <span class="stl__icon">
            <el-icon v-if="step.status === 'completed'" :size="12"><Check /></el-icon>
            <el-icon v-else-if="step.status === 'failed'" :size="12"><Close /></el-icon>
            <span v-else-if="step.status === 'running'" class="stl__spinner" />
            <span v-else class="stl__circle" />
          </span>
          <span v-if="idx < normalizedSteps.length - 1" class="stl__line" :class="`stl__line--${step.status}`" />
        </div>

        <div class="stl__body">
          <div class="stl__header">
            <span class="stl__name">{{ step.name }}</span>
            <span v-if="step.latency" class="stl__latency">{{ step.latency }}</span>
          </div>
          <p v-if="step.message" class="stl__msg">{{ step.message }}</p>
        </div>
      </div>
    </div>

    <div v-if="!normalizedSteps.length" class="stl__empty">等待步骤开始…</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Check, Close } from '@element-plus/icons-vue'

const props = defineProps({
  /**
   * 步骤数组，每项: { name, status, message?, latency_ms?, progress_pct? }
   * status: 'pending' | 'running' | 'completed' | 'failed'
   */
  steps: { type: Array, default: () => [] },
  showProgress: { type: Boolean, default: true },
})

const normalizedSteps = computed(() =>
  props.steps.map(s => ({
    name: s.name || s.step_name || '未知步骤',
    status: s.status || 'pending',
    message: s.message || '',
    latency: formatLatency(s.latency_ms),
  }))
)

const progressPct = computed(() => {
  if (!props.steps.length) return 0
  const last = [...props.steps].reverse().find(s => s.progress_pct != null)
  return last?.progress_pct ?? 0
})

function formatLatency(ms) {
  if (!ms) return ''
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`
}
</script>

<style scoped>
.stl {
  display: flex;
  flex-direction: column;
  gap: var(--v2-space-3);
}

/* ── Progress bar ──────────────────────────────────────── */
.stl__progress {
  display: flex;
  align-items: center;
  gap: var(--v2-space-2);
}
.stl__progress-bar {
  flex: 1;
  height: 4px;
  background: var(--v2-bg-sunken);
  border-radius: var(--v2-radius-full);
  overflow: hidden;
}
.stl__progress-fill {
  height: 100%;
  background: var(--v2-brand-primary);
  border-radius: var(--v2-radius-full);
  transition: width .4s var(--v2-ease);
}
.stl__progress-text {
  font-size: var(--v2-text-xs);
  font-family: var(--v2-font-mono);
  color: var(--v2-text-3);
  min-width: 36px;
  text-align: right;
}

/* ── Step list ─────────────────────────────────────────── */
.stl__list {
  display: flex;
  flex-direction: column;
}

.stl__item {
  display: flex;
  gap: var(--v2-space-3);
}

/* Rail */
.stl__rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 20px;
  flex-shrink: 0;
}

.stl__icon {
  width: 20px; height: 20px;
  border-radius: var(--v2-radius-full);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 12px;
}

.stl__item--completed .stl__icon {
  background: var(--v2-success);
  color: #fff;
}
.stl__item--running .stl__icon {
  background: var(--v2-brand-primary-bg);
  border: 2px solid var(--v2-brand-primary);
}
.stl__item--failed .stl__icon {
  background: var(--v2-error);
  color: #fff;
}
.stl__item--pending .stl__icon {
  background: var(--v2-bg-card);
  border: 2px solid var(--v2-border-1);
}

.stl__circle {
  width: 6px; height: 6px;
  border-radius: var(--v2-radius-full);
  background: var(--v2-gray-400);
}

.stl__spinner {
  width: 8px; height: 8px;
  border: 2px solid var(--v2-brand-primary);
  border-top-color: transparent;
  border-radius: var(--v2-radius-full);
  animation: stl-spin .8s linear infinite;
}

.stl__line {
  flex: 1;
  width: 2px;
  min-height: 12px;
  background: var(--v2-border-1);
  margin: 2px 0;
}
.stl__line--completed { background: var(--v2-success); opacity: .5; }
.stl__line--running   { background: var(--v2-brand-primary); opacity: .4; }
.stl__line--failed    { background: var(--v2-error); opacity: .4; }

/* Body */
.stl__body {
  flex: 1;
  min-width: 0;
  padding-bottom: var(--v2-space-3);
}
.stl__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v2-space-2);
}
.stl__name {
  font-size: var(--v2-text-sm);
  font-weight: var(--v2-font-medium);
  color: var(--v2-text-1);
}
.stl__item--pending .stl__name { color: var(--v2-text-4); }

.stl__latency {
  font-size: var(--v2-text-xs);
  font-family: var(--v2-font-mono);
  color: var(--v2-text-3);
}

.stl__msg {
  margin-top: 2px;
  font-size: var(--v2-text-xs);
  color: var(--v2-text-3);
  line-height: var(--v2-leading-snug);
}
.stl__item--failed .stl__msg { color: var(--v2-error-text); }

.stl__empty {
  padding: var(--v2-space-6);
  text-align: center;
  color: var(--v2-text-4);
  font-size: var(--v2-text-sm);
}

@keyframes stl-spin {
  to { transform: rotate(360deg); }
}
</style>
