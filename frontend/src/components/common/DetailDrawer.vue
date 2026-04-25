<template>
  <el-drawer
    :model-value="visible"
    :title="title"
    :size="size"
    :destroy-on-close="true"
    @close="$emit('update:visible', false)"
  >
    <template #header>
      <div class="detail-drawer__header">
        <h3 class="detail-drawer__title">{{ title }}</h3>
        <span v-if="subtitle" class="detail-drawer__subtitle">{{ subtitle }}</span>
      </div>
    </template>
    <div class="detail-drawer__body">
      <slot />
    </div>
    <template v-if="$slots.footer" #footer>
      <slot name="footer" />
    </template>
  </el-drawer>
</template>

<script setup>
defineProps({
  visible:  { type: Boolean, default: false },
  title:    { type: String, default: '详情' },
  subtitle: { type: String, default: '' },
  size:     { type: String, default: '480px' },
})

defineEmits(['update:visible'])
</script>

<style scoped>
.detail-drawer__header { min-width: 0; }
.detail-drawer__title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin: 0;
}
.detail-drawer__subtitle {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  margin-top: 2px;
  display: block;
}
.detail-drawer__body {
  font-size: var(--font-size-body);
}
</style>
