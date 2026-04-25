<template>
  <el-card shadow="hover" class="stat-card">
    <el-statistic :title="title" :value="value" :precision="precision">
      <template #suffix><slot name="suffix" /></template>
    </el-statistic>
    <div class="trend" :class="trend > 0 ? 'up' : 'down'" v-if="trend !== undefined">
      <el-icon><ArrowUp v-if="trend > 0" /><ArrowDown v-else /></el-icon>
      {{ Math.abs(trend) }}%
    </div>
  </el-card>
</template>
<script setup>
defineProps({ title: String, value: [Number, String], precision: { type: Number, default: 0 }, trend: Number })
</script>
<style scoped>
.stat-card { text-align: center; }
.trend { font-size: 12px; margin-top: 8px; }
.up   { color: var(--v2-success); }
.down { color: var(--v2-error); }
</style>
