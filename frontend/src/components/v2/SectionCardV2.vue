<template>
  <section class="sec">
    <div v-if="title || $slots.header" class="sec__header">
      <div class="sec__header-left">
        <h3 v-if="title" class="sec__title">{{ title }}</h3>
        <span v-if="subtitle" class="sec__subtitle">{{ subtitle }}</span>
      </div>
      <div v-if="$slots.header" class="sec__header-right">
        <slot name="header" />
      </div>
    </div>
    <div class="sec__body" :class="{ 'sec__body--flush': flush }">
      <slot />
    </div>
    <div v-if="$slots.footer" class="sec__footer">
      <slot name="footer" />
    </div>
  </section>
</template>

<script setup>
defineProps({
  title:    { type: String, default: '' },
  subtitle: { type: String, default: '' },
  flush:    { type: Boolean, default: false },
})
</script>

<style scoped>
.sec {
  background: var(--v2-bg-card);
  border: 1px solid var(--v2-border-2);
  border-radius: var(--v2-radius-lg);
  overflow: hidden;
}
.sec__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--v2-space-4) var(--v2-space-5);
  border-bottom: 1px solid var(--v2-border-2);
}
.sec__header-left {
  display: flex;
  align-items: baseline;
  gap: var(--v2-space-2);
  min-width: 0;
}
.sec__title {
  font-size: var(--v2-text-md);
  font-weight: var(--v2-font-semibold);
  color: var(--v2-text-1);
  margin: 0;
  white-space: nowrap;
}
.sec__subtitle {
  font-size: var(--v2-text-xs);
  color: var(--v2-text-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sec__header-right {
  display: flex;
  align-items: center;
  gap: var(--v2-space-2);
  flex-shrink: 0;
}
.sec__body { padding: var(--v2-space-5); }
.sec__body--flush { padding: 0; }
.sec__footer {
  padding: var(--v2-space-3) var(--v2-space-5);
  border-top: 1px solid var(--v2-border-2);
  background: var(--v2-bg-sunken);
}
</style>
