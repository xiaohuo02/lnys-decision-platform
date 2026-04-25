<template>
  <div class="ph">
    <div class="ph__left">
      <h1 class="ph__title">{{ title }}</h1>
      <p v-if="desc" class="ph__desc">{{ desc }}</p>
    </div>
    <div v-if="$slots.actions" class="ph__actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  desc:  { type: String, default: '' },
})
</script>

<style scoped>
.ph {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--v2-space-4);
  margin-bottom: var(--v2-space-5);
}
.ph__left { min-width: 0; }
.ph__title {
  font-size: var(--v2-text-xl);
  font-weight: var(--v2-font-semibold);
  color: var(--v2-text-1);
  line-height: var(--v2-leading-tight);
  margin: 0;
}
.ph__desc {
  font-size: var(--v2-text-sm);
  color: var(--v2-text-3);
  margin: var(--v2-space-1) 0 0;
  line-height: var(--v2-leading-normal);
}
.ph__actions {
  display: flex;
  align-items: center;
  gap: var(--v2-space-2);
  flex-shrink: 0;
}
</style>
