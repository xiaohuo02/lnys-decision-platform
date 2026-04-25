<template>
  <div class="base-table">
    <el-table :data="data" v-bind="$attrs" stripe style="width: 100%">
      <slot />
    </el-table>
    <el-pagination
      v-if="showPagination && total > 0"
      class="base-table__pagination"
      :current-page="currentPage"
      :page-size="pageSize"
      :total="total"
      layout="total, prev, pager, next"
      @current-change="$emit('page-change', $event)"
    />
  </div>
</template>

<script setup>
defineProps({
  data:           { type: Array, default: () => [] },
  total:          { type: Number, default: 0 },
  currentPage:    { type: Number, default: 1 },
  pageSize:       { type: Number, default: 20 },
  showPagination: { type: Boolean, default: true },
})

defineEmits(['page-change'])
</script>

<style scoped>
.base-table__pagination { margin-top: 16px; display: flex; justify-content: flex-end; }
</style>
