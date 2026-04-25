<template>
  <div class="empty-state" :style="{ minHeight: height }">
    <el-empty :description="description" :image-size="imageSize" />
    <slot name="action" />
  </div>
</template>

<script setup>
defineProps({
  description: { type: String, default: '暂无数据' },
  imageSize:   { type: Number, default: 100 },
  height:      { type: String, default: '200px' },
})
</script>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
</style>
