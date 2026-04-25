<template>
  <button class="cab" :class="{ 'cab--loading': loading }" :disabled="loading || disabled" @click="invoke" :title="tipText">
    <svg v-if="!loading" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
      <path d="M16 3h5v5M4 20L21 3M21 16v5h-5M4 4l17 17"/>
    </svg>
    <span v-if="loading" class="cab__spinner"></span>
    <span class="cab__label">{{ label }}</span>
  </button>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  ai: { type: Object, required: true },
  skillId: { type: String, required: true },
  question: { type: String, required: true },
  context: { type: Object, default: () => ({}) },
  label: { type: String, default: '跨智能体分析' },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['result', 'error'])
const loading = ref(false)
const tipText = `调用 ${props.skillId} 智能体`

async function invoke() {
  if (loading.value || props.disabled) return
  loading.value = true
  try {
    if (props.context && Object.keys(props.context).length) {
      props.ai?.setContext?.(props.context)
    }
    await props.ai?.askAgent?.(props.skillId, props.question)
    emit('result')
  } catch (e) {
    emit('error', e)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.cab {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 5px 12px;
  border: 1px solid rgba(0,0,0,0.08); border-radius: 6px;
  background: #fff; color: #18181b; font-size: 12px;
  cursor: pointer; transition: all 0.15s; font-family: inherit; font-weight: 500;
}
.cab:hover { background: #f4f4f5; border-color: rgba(0,0,0,0.15); }
.cab:disabled { opacity: 0.5; cursor: not-allowed; }
.cab--loading { pointer-events: none; }
.cab__spinner { width: 12px; height: 12px; border: 2px solid rgba(0,0,0,0.1); border-top-color: #18181b; border-radius: 50%; animation: cab-spin 0.6s linear infinite; }
@keyframes cab-spin { to { transform: rotate(360deg); } }
.cab__label { white-space: nowrap; }
</style>
