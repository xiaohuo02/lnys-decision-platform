<template>
  <div class="err" :style="{ minHeight: height }">
    <div class="err__icon">
      <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
        <circle cx="24" cy="24" r="20" stroke="currentColor" stroke-width="2" fill="none"/>
        <path d="M24 14v12M24 30v4" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/>
      </svg>
    </div>
    <p class="err__title">{{ title }}</p>
    <p v-if="desc" class="err__desc">{{ desc }}</p>
    <el-button v-if="showRetry" size="small" @click="$emit('retry')">重试</el-button>
  </div>
</template>

<script setup>
defineProps({
  title:     { type: String, default: '加载失败' },
  desc:      { type: String, default: '请稍后重试或联系管理员' },
  height:    { type: String, default: '240px' },
  showRetry: { type: Boolean, default: true },
})
defineEmits(['retry'])
</script>

<style scoped>
.err {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: var(--v2-space-8);
}
.err__icon { color: var(--v2-error); margin-bottom: var(--v2-space-4); opacity: .6; }
.err__title {
  font-size: var(--v2-text-md);
  color: var(--v2-text-1);
  font-weight: var(--v2-font-medium);
  margin: 0;
}
.err__desc {
  font-size: var(--v2-text-sm);
  color: var(--v2-text-3);
  margin: var(--v2-space-1) 0 var(--v2-space-4);
  max-width: 320px;
}
</style>
