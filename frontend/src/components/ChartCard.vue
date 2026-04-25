<template>
  <el-card :header="title" shadow="hover" class="chart-card">
    <div :style="{ height: height + 'px' }">
      <v-chart v-if="option" :option="option" autoresize />
      <el-empty v-else description="暂无数据" />
    </div>
  </el-card>
</template>
<script setup>
defineProps({ title: String, option: Object, height: { type: Number, default: 320 } })
</script>
<style scoped>
.chart-card { margin-bottom: 16px; }
</style>
