<template>
  <div v-if="loading" class="mask">
    <el-icon class="spin" size="32"><Loading /></el-icon>
    <p>{{ text }}</p>
  </div>
  <slot v-else />
</template>
<script setup>
defineProps({ loading: Boolean, text: { type: String, default: '加载中...' } })
</script>
<style scoped>
.mask { display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 200px; color: var(--v2-text-3); gap: 12px; }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
