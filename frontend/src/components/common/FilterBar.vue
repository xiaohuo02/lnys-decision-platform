<template>
  <div class="filter-bar">
    <div class="filter-bar__fields">
      <slot />
    </div>
    <div class="filter-bar__actions">
      <el-button type="primary" size="small" @click="$emit('search')">查询</el-button>
      <el-button size="small" @click="$emit('reset')">重置</el-button>
      <slot name="extra-actions" />
    </div>
  </div>
</template>

<script setup>
defineEmits(['search', 'reset'])
</script>

<style scoped>
.filter-bar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--spacing-md);
  padding: var(--spacing-md) var(--spacing-lg);
  background: var(--color-bg-card);
  border-radius: var(--radius-md);
  margin-bottom: var(--spacing-md);
  box-shadow: var(--shadow-xs);
  flex-wrap: wrap;
}
.filter-bar__fields {
  display: flex;
  align-items: flex-end;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
  flex: 1;
  min-width: 0;
}
.filter-bar__fields :deep(.el-form-item) {
  margin-bottom: 0;
}
.filter-bar__actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  flex-shrink: 0;
}
</style>
