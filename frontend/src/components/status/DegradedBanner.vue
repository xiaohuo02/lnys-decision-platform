<template>
  <el-alert
    v-if="visible"
    :title="title"
    :description="description"
    type="warning"
    show-icon
    :closable="closable"
    class="degraded-banner"
    @close="$emit('close')"
  />
</template>

<script setup>
defineProps({
  visible:     { type: Boolean, default: true },
  title:       { type: String, default: '数据降级提示' },
  description: { type: String, default: '当前展示的部分数据可能不完整或来自缓存，请关注数据时效性。' },
  closable:    { type: Boolean, default: true },
})

defineEmits(['close'])
</script>

<style scoped>
.degraded-banner { margin-bottom: 16px; }
</style>
