<template>
  <div class="dense-table">
    <el-table
      :data="data"
      v-bind="$attrs"
      stripe
      size="small"
      :header-cell-style="headerStyle"
      :cell-style="cellStyle"
      style="width:100%"
    >
      <slot />
    </el-table>
    <div v-if="total > 0" class="dense-table__footer">
      <span class="dense-table__total">共 {{ total }} 条</span>
      <el-pagination
        size="small"
        background
        layout="prev, pager, next"
        :current-page="currentPage"
        :page-size="pageSize"
        :total="total"
        @current-change="$emit('page-change', $event)"
      />
    </div>
  </div>
</template>

<script setup>
defineProps({
  data:        { type: Array, default: () => [] },
  total:       { type: Number, default: 0 },
  currentPage: { type: Number, default: 1 },
  pageSize:    { type: Number, default: 20 },
})

defineEmits(['page-change'])

const headerStyle = {
  background: 'var(--color-bg-elevated)',
  color: 'var(--color-text-secondary)',
  fontWeight: '500',
  fontSize: '12px',
  padding: '8px 0',
}

const cellStyle = {
  fontSize: '13px',
  padding: '6px 0',
  color: 'var(--color-text-primary)',
}
</script>

<style scoped>
.dense-table {
  background: var(--color-bg-card);
  border-radius: var(--radius-md);
  overflow: hidden;
  box-shadow: var(--shadow-xs);
}
.dense-table__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-sm) var(--spacing-md);
  border-top: 1px solid var(--color-border-light);
}
.dense-table__total {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}
</style>
