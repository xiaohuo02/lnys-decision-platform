<template>
  <div class="section-card" :class="{ 'section-card--compact': compact }">
    <div v-if="title || $slots.header" class="section-card__header">
      <div class="section-card__title-group">
        <h3 class="section-card__title">{{ title }}</h3>
        <span v-if="desc" class="section-card__desc">{{ desc }}</span>
      </div>
      <div v-if="$slots.header" class="section-card__header-extra">
        <slot name="header" />
      </div>
    </div>
    <div class="section-card__body">
      <slot />
    </div>
  </div>
</template>

<script setup>
defineProps({
  title:   { type: String, default: '' },
  desc:    { type: String, default: '' },
  compact: { type: Boolean, default: false },
})
</script>

<style scoped>
.section-card {
  background: var(--color-bg-card);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-xs);
  overflow: hidden;
}
.section-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-md) var(--spacing-lg);
  border-bottom: 1px solid var(--color-border-light);
  gap: var(--spacing-md);
}
.section-card__title-group { min-width: 0; }
.section-card__title {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin: 0;
}
.section-card__desc {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-top: 1px;
  display: block;
}
.section-card__header-extra {
  flex-shrink: 0;
}
.section-card__body {
  padding: var(--spacing-lg);
}
.section-card--compact .section-card__body {
  padding: var(--spacing-md);
}
</style>
