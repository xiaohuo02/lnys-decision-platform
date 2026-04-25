<template>
  <div class="dsw">
    <!-- Degraded banner (shown above content when degraded but still has data) -->
    <DegradedBannerV2
      v-if="degraded && state === 'ok'"
      :title="degradedTitle"
      :desc="degradedDesc"
      :level="degradedLevel"
    />

    <!-- Loading / Skeleton -->
    <SkeletonBlockV2
      v-if="state === 'loading'"
      :rows="skeletonRows"
      :columns="skeletonCols"
      :height="minHeight"
    />

    <!-- Error -->
    <ErrorStateV2
      v-else-if="state === 'error'"
      :title="errorTitle"
      :desc="errorDesc"
      :height="minHeight"
      :show-retry="showRetry"
      @retry="$emit('retry')"
    />

    <!-- Empty -->
    <EmptyStateV2
      v-else-if="state === 'empty'"
      :title="emptyTitle"
      :desc="emptyDesc"
      :height="minHeight"
    >
      <slot name="empty-action" />
    </EmptyStateV2>

    <!-- OK: render default slot -->
    <slot v-else-if="state === 'ok'" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import SkeletonBlockV2 from './SkeletonBlockV2.vue'
import EmptyStateV2 from './EmptyStateV2.vue'
import ErrorStateV2 from './ErrorStateV2.vue'
import DegradedBannerV2 from './DegradedBannerV2.vue'

const props = defineProps({
  loading:       { type: Boolean, default: false },
  error:         { type: [Boolean, String], default: false },
  empty:         { type: Boolean, default: false },
  degraded:      { type: Boolean, default: false },
  minHeight:     { type: String, default: '200px' },
  skeletonRows:  { type: Number, default: 4 },
  skeletonCols:  { type: Number, default: 1 },
  emptyTitle:    { type: String, default: '暂无数据' },
  emptyDesc:     { type: String, default: '' },
  errorTitle:    { type: String, default: '加载失败' },
  errorDesc:     { type: String, default: '请稍后重试或联系管理员' },
  showRetry:     { type: Boolean, default: true },
  degradedTitle: { type: String, default: '部分数据可能不完整' },
  degradedDesc:  { type: String, default: '' },
  degradedLevel: { type: String, default: 'warning' },
})

defineEmits(['retry'])

const state = computed(() => {
  if (props.loading) return 'loading'
  if (props.error) return 'error'
  if (props.empty) return 'empty'
  return 'ok'
})
</script>

<style scoped>
.dsw { min-height: 0; }
</style>
