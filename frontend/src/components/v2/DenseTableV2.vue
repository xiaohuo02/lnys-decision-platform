<template>
  <div class="dt" tabindex="0" @keydown="handleKeydown">
    <div v-if="title || $slots.toolbar" class="dt__toolbar">
      <span v-if="title" class="dt__title">{{ title }}</span>
      <div v-if="$slots.toolbar" class="dt__toolbar-right"><slot name="toolbar" /></div>
    </div>
    <el-table
      ref="tableRef"
      v-bind="$attrs"
      :data="data"
      :max-height="maxHeight"
      :stripe="false"
      :border="false"
      :default-sort="defaultSort"
      :highlight-current-row="highlightCurrentRow"
      class="dt__table"
      size="small"
      header-cell-class-name="dt__th"
      cell-class-name="dt__td"
      @sort-change="onSortChange"
      @current-change="onCurrentChange"
      @row-click="onRowClick"
    >
      <slot />
    </el-table>
    <div v-if="pagination || $slots.footer" class="dt__footer">
      <slot name="footer" />
      <el-pagination
        v-if="pagination"
        size="small"
        background
        :layout="paginationLayout"
        :total="pagination.total || 0"
        :page-size="pagination.pageSize || 20"
        :current-page="pagination.currentPage || 1"
        :page-sizes="pagination.pageSizes || [10, 20, 50, 100]"
        @current-change="onPageChange"
        @size-change="onSizeChange"
      />
    </div>
    <div v-if="!data.length && !$slots.default" class="dt__empty">暂无数据</div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  data:                { type: Array, default: () => [] },
  title:               { type: String, default: '' },
  maxHeight:           { type: [String, Number], default: undefined },
  pagination:          { type: Object, default: null },
  paginationLayout:    { type: String, default: 'total, sizes, prev, pager, next' },
  defaultSort:         { type: Object, default: undefined },
  highlightCurrentRow: { type: Boolean, default: true },
  keyboardNav:         { type: Boolean, default: true },
})

const emit = defineEmits([
  'page-change', 'size-change', 'sort-change',
  'row-click', 'current-change', 'row-select',
])

const tableRef = ref(null)
const currentRowIndex = ref(-1)

function onSortChange({ column, prop, order }) {
  emit('sort-change', { column, prop, order })
}

function onPageChange(page) {
  emit('page-change', page)
}

function onSizeChange(size) {
  emit('size-change', size)
}

function onCurrentChange(row) {
  if (row) {
    currentRowIndex.value = props.data.indexOf(row)
  }
  emit('current-change', row)
}

function onRowClick(row, column, event) {
  emit('row-click', row, column, event)
}

function handleKeydown(e) {
  if (!props.keyboardNav || !props.data.length) return

  if (e.key === 'ArrowDown' || e.key === 'j') {
    e.preventDefault()
    const next = Math.min(currentRowIndex.value + 1, props.data.length - 1)
    selectRowByIndex(next)
  } else if (e.key === 'ArrowUp' || e.key === 'k') {
    e.preventDefault()
    const prev = Math.max(currentRowIndex.value - 1, 0)
    selectRowByIndex(prev)
  } else if (e.key === 'Enter') {
    if (currentRowIndex.value >= 0 && currentRowIndex.value < props.data.length) {
      emit('row-select', props.data[currentRowIndex.value])
    }
  }
}

function selectRowByIndex(idx) {
  if (idx < 0 || idx >= props.data.length) return
  currentRowIndex.value = idx
  tableRef.value?.setCurrentRow(props.data[idx])
}

watch(() => props.data, () => {
  currentRowIndex.value = -1
})

defineExpose({ tableRef, selectRowByIndex })
</script>

<style scoped>
.dt {
  background: var(--v2-bg-card);
  border: 1px solid var(--v2-border-2);
  border-radius: var(--v2-radius-lg);
  overflow: hidden;
  outline: none;
}
.dt:focus-within {
  box-shadow: 0 0 0 2px var(--v2-brand-bg);
}
.dt__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--v2-space-3) var(--v2-space-4);
  border-bottom: 1px solid var(--v2-border-2);
}
.dt__title {
  font-size: var(--v2-text-sm);
  font-weight: var(--v2-font-semibold);
  color: var(--v2-text-1);
}
.dt__toolbar-right {
  display: flex;
  align-items: center;
  gap: var(--v2-space-2);
}

:deep(.dt__th) {
  background: var(--v2-bg-sunken) !important;
  color: var(--v2-text-3) !important;
  font-size: var(--v2-text-xs) !important;
  font-weight: var(--v2-font-semibold) !important;
  text-transform: uppercase;
  letter-spacing: .4px;
  padding: 6px 12px !important;
  border-bottom: 1px solid var(--v2-border-1) !important;
}
:deep(.dt__td) {
  padding: 8px 12px !important;
  font-size: var(--v2-text-base) !important;
  color: var(--v2-text-1) !important;
  border-bottom-color: var(--v2-border-2) !important;
}
:deep(.el-table__row--current td) {
  background: var(--v2-brand-bg) !important;
}
:deep(.el-table__row:hover td) {
  background: var(--v2-bg-sunken) !important;
}

.dt__footer {
  padding: var(--v2-space-3) var(--v2-space-4);
  border-top: 1px solid var(--v2-border-2);
  background: var(--v2-bg-sunken);
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--v2-space-3);
}

.dt__empty {
  padding: var(--v2-space-8);
  text-align: center;
  font-size: var(--v2-text-sm);
  color: var(--v2-text-4);
}
</style>
