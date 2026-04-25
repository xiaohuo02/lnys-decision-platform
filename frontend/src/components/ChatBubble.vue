<template>
  <div class="bubble-wrap" :class="role">
    <div class="bubble">
      <slot />
    </div>
    <div class="meta" v-if="intent">
      意图：{{ intent }} <el-tag size="small" type="info">{{ (confidence * 100).toFixed(0) }}%</el-tag>
    </div>
  </div>
</template>
<script setup>
defineProps({ role: { type: String, default: 'bot' }, intent: String, confidence: Number })
</script>
<style scoped>
.bubble-wrap { margin: 8px 0; display: flex; flex-direction: column; }
.bubble-wrap.user { align-items: flex-end; }
.bubble-wrap.bot  { align-items: flex-start; }
.bubble { max-width: 70%; padding: 10px 14px; border-radius: 12px; font-size: 14px; line-height: 1.6; }
.user .bubble { background: var(--v2-brand-primary); color: var(--v2-text-inverse); }
.bot  .bubble { background: var(--v2-bg-elevated); color: var(--v2-text-1); }
.meta { font-size: 11px; color: var(--v2-text-3); margin-top: 4px; }
</style>
