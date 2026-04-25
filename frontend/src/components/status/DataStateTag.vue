<template>
  <el-tag
    :type="tagType"
    :effect="effect"
    size="small"
    class="data-state-tag"
  >
    <el-icon v-if="showIcon" style="margin-right:2px"><component :is="iconName" /></el-icon>
    {{ label }}
  </el-tag>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  /** ai_generated | cached | degraded | human_reviewed | fallback */
  state:    { type: String, required: true },
  effect:   { type: String, default: 'light' },
  showIcon: { type: Boolean, default: true },
})

const stateMap = {
  ai_generated:   { type: '',        label: 'AI 生成',    icon: 'Cpu' },
  cached:         { type: 'info',    label: '缓存数据',   icon: 'Clock' },
  degraded:       { type: 'warning', label: '降级数据',   icon: 'WarningFilled' },
  human_reviewed: { type: 'success', label: '人工审核',   icon: 'CircleCheckFilled' },
  fallback:       { type: 'danger',  label: 'Fallback',  icon: 'CircleCloseFilled' },
}

const cfg = computed(() => stateMap[props.state] || { type: 'info', label: props.state, icon: 'InfoFilled' })
const tagType  = computed(() => cfg.value.type)
const label    = computed(() => cfg.value.label)
const iconName = computed(() => cfg.value.icon)
</script>

<style scoped>
.data-state-tag { cursor: default; }
</style>
