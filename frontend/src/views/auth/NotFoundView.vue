<template>
  <div class="error-page">
    <div class="error-page__code">404</div>
    <h2 class="error-page__title">页面不存在</h2>
    <p class="error-page__desc">您访问的页面不存在或已被移除。</p>
    <div class="error-page__actions">
      <el-button type="primary" @click="$router.replace('/')">返回首页</el-button>
      <el-button @click="$router.back()">返回上页</el-button>
    </div>
  </div>
</template>

<script setup>
</script>

<style scoped>
.error-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-page);
  padding: var(--spacing-xl);
}
.error-page__code {
  font-size: 96px;
  font-weight: var(--font-weight-bold);
  color: var(--color-border);
  line-height: 1;
  font-variant-numeric: tabular-nums;
}
.error-page__title {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin: var(--spacing-sm) 0 var(--spacing-xs);
}
.error-page__desc {
  font-size: var(--font-size-body);
  color: var(--color-text-tertiary);
  margin: 0 0 var(--spacing-lg);
}
.error-page__actions {
  display: flex;
  gap: var(--spacing-sm);
}
</style>
