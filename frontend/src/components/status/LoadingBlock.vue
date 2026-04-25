<template>
  <div class="loading-block" :style="{ minHeight: height }">
    <el-icon class="loading-block__icon is-loading" :size="28"><Loading /></el-icon>
    <span class="loading-block__text">{{ text }}</span>
  </div>
</template>

<script setup>
import { Loading } from '@element-plus/icons-vue'

defineProps({
  text:   { type: String, default: '加载中…' },
  height: { type: String, default: '200px' },
})
</script>

<style scoped>
.loading-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--v2-text-3);
  gap: 12px;
}
.loading-block__text { font-size: 13px; }
</style>
