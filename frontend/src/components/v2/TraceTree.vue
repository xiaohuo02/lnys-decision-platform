<template>
  <div class="tt">
    <div
      v-for="(step, idx) in steps"
      :key="step.step_id"
      class="tt__node"
      :class="{ 'is-selected': modelValue === step.step_id }"
      @click="$emit('update:modelValue', step.step_id)"
    >
      <!-- Connector line -->
      <div class="tt__rail">
        <span class="tt__dot" :class="`tt__dot--${step.status}`">
          <el-icon v-if="step.status === 'completed'" :size="10"><Check /></el-icon>
          <el-icon v-else-if="step.status === 'failed'" :size="10"><Close /></el-icon>
          <span v-else-if="step.status === 'running'" class="tt__dot-pulse" />
          <span v-else class="tt__dot-inner" />
        </span>
        <span v-if="idx < steps.length - 1" class="tt__line" :class="`tt__line--${step.status}`" />
      </div>

      <!-- Content -->
      <div class="tt__body">
        <div class="tt__header">
          <span class="tt__name">{{ step.step_name }}</span>
          <span v-if="step.latency_ms || step.ended_at" class="tt__time">
            {{ formatDuration(step) }}
          </span>
        </div>
        <div class="tt__meta">
          <span class="tt__type">{{ stepTypeLabel(step.step_type) }}</span>
          <span v-if="step.agent_name" class="tt__agent">{{ step.agent_name }}</span>
          <span v-if="step.model_name" class="tt__model">{{ step.model_name }}</span>
        </div>
        <p v-if="step.output_summary" class="tt__summary">{{ step.output_summary }}</p>
      </div>
    </div>

    <div v-if="!steps.length" class="tt__empty">暂无步骤数据</div>
  </div>
</template>

<script setup>
import { Check, Close } from '@element-plus/icons-vue'

defineProps({
  steps: { type: Array, default: () => [] },
  modelValue: { type: String, default: '' },
})

defineEmits(['update:modelValue'])

function stepTypeLabel(type) {
  const map = {
    service_call: 'Service',
    agent_call: 'Agent',
    llm_call: 'LLM',
    tool_call: 'Tool',
    human_review: 'HITL',
  }
  return map[type] || type
}

function formatDuration(step) {
  if (step.latency_ms) {
    return step.latency_ms >= 1000
      ? `${(step.latency_ms / 1000).toFixed(1)}s`
      : `${step.latency_ms}ms`
  }
  if (step.started_at && step.ended_at) {
    const ms = new Date(step.ended_at) - new Date(step.started_at)
    return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`
  }
  return ''
}
</script>

<style scoped>
.tt { display: flex; flex-direction: column; }

.tt__node {
  display: flex;
  gap: var(--v2-space-3);
  padding: var(--v2-space-2) var(--v2-space-3);
  border-radius: var(--v2-radius-md);
  cursor: pointer;
  transition: background var(--v2-trans-fast);
}
.tt__node:hover { background: var(--v2-bg-hover); }
.tt__node.is-selected {
  background: var(--v2-brand-primary-bg);
}

/* ── Rail (dot + line) ───────────────────────────────── */
.tt__rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 18px;
  flex-shrink: 0;
  padding-top: 3px;
}

.tt__dot {
  width: 18px; height: 18px;
  border-radius: var(--v2-radius-full);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border: 2px solid var(--v2-border-1);
  background: var(--v2-bg-card);
}
.tt__dot--completed {
  background: var(--v2-success);
  border-color: var(--v2-success);
  color: #fff;
}
.tt__dot--running {
  border-color: var(--v2-brand-primary);
  background: var(--v2-brand-primary-bg);
}
.tt__dot--failed {
  background: var(--v2-error);
  border-color: var(--v2-error);
  color: #fff;
}
.tt__dot--review {
  border-color: var(--v2-ai-purple);
  background: var(--v2-ai-purple-bg);
}

.tt__dot-inner {
  width: 6px; height: 6px;
  border-radius: var(--v2-radius-full);
  background: var(--v2-gray-400);
}

.tt__dot-pulse {
  width: 6px; height: 6px;
  border-radius: var(--v2-radius-full);
  background: var(--v2-brand-primary);
  animation: tt-pulse 1.2s ease-in-out infinite;
}

.tt__line {
  flex: 1;
  width: 2px;
  min-height: 16px;
  background: var(--v2-border-1);
  margin: 2px 0;
}
.tt__line--completed { background: var(--v2-success); opacity: .5; }
.tt__line--running   { background: var(--v2-brand-primary); opacity: .4; }
.tt__line--failed    { background: var(--v2-error); opacity: .4; }

/* ── Body ────────────────────────────────────────────── */
.tt__body {
  flex: 1;
  min-width: 0;
  padding-bottom: var(--v2-space-2);
}

.tt__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v2-space-2);
}
.tt__name {
  font-size: var(--v2-text-sm);
  font-weight: var(--v2-font-medium);
  color: var(--v2-text-1);
  font-family: var(--v2-font-mono);
}
.tt__time {
  font-size: var(--v2-text-xs);
  color: var(--v2-text-3);
  font-family: var(--v2-font-mono);
  flex-shrink: 0;
}

.tt__meta {
  display: flex;
  align-items: center;
  gap: var(--v2-space-2);
  margin-top: 2px;
}
.tt__type,
.tt__agent,
.tt__model {
  font-size: var(--v2-text-2xs);
  padding: 1px 5px;
  border-radius: 3px;
  font-weight: var(--v2-font-medium);
}
.tt__type {
  background: var(--v2-tag-blue);
  color: var(--v2-tag-blue-text);
}
.tt__agent {
  background: var(--v2-tag-gray);
  color: var(--v2-tag-gray-text);
}
.tt__model {
  background: var(--v2-tag-purple);
  color: var(--v2-tag-purple-text);
}

.tt__summary {
  margin-top: 4px;
  font-size: var(--v2-text-xs);
  color: var(--v2-text-3);
  line-height: var(--v2-leading-snug);
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.tt__empty {
  padding: var(--v2-space-6);
  text-align: center;
  color: var(--v2-text-4);
  font-size: var(--v2-text-sm);
}

@keyframes tt-pulse {
  0%, 100% { opacity: 1; }
  50%      { opacity: .3; }
}
</style>
