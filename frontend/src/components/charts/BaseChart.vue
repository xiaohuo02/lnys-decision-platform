<template>
  <div class="base-chart" :style="{ height }">
    <v-chart v-if="option" :option="option" autoresize />
    <EmptyState v-else description="暂无图表数据" :height="height" />
  </div>
</template>

<script setup>
import { EmptyState } from '@/components/status'

defineProps({
  option: { type: Object, default: null },
  height: { type: String, default: '320px' },
})
</script>

<style scoped>
.base-chart { width: 100%; }
</style>
