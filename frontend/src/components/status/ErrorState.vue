<template>
  <div class="error-state" :style="{ minHeight: height }">
    <el-result icon="error" :title="title" :sub-title="subTitle">
      <template #extra>
        <el-button type="primary" @click="$emit('retry')">重试</el-button>
        <slot name="action" />
      </template>
    </el-result>
  </div>
</template>

<script setup>
defineProps({
  title:    { type: String, default: '加载失败' },
  subTitle: { type: String, default: '请检查网络后重试' },
  height:   { type: String, default: '200px' },
})

defineEmits(['retry'])
</script>

<style scoped>
.error-state {
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
