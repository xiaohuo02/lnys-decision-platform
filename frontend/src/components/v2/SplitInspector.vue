<template>
  <div class="si" :class="[`si--${columns}`]">
    <div v-if="$slots.left" class="si__panel si__panel--left">
      <slot name="left" />
    </div>
    <div class="si__panel si__panel--main">
      <slot name="main" />
    </div>
    <div v-if="$slots.right && !hideRight" class="si__panel si__panel--right">
      <slot name="right" />
    </div>
  </div>
</template>

<script setup>
import { computed, useSlots } from 'vue'

const props = defineProps({
  hideRight: { type: Boolean, default: false },
})

const slots = useSlots()

const columns = computed(() => {
  const hasLeft  = !!slots.left
  const hasRight = !!slots.right && !props.hideRight
  if (hasLeft && hasRight) return 3
  if (hasLeft) return '2l'
  if (hasRight) return '2r'
  return 1
})
</script>

<style scoped>
.si {
  display: grid;
  gap: var(--v2-space-3);
  min-height: 0;
  flex: 1;
  grid-template-rows: minmax(0, 1fr);
}

/* 3-col: nav tree | main content | detail inspector */
.si--3 {
  grid-template-columns: 220px 1fr 320px;
}

/* 2-col: left panel | main content */
.si--2l {
  grid-template-columns: 280px 1fr;
}

/* 2-col: main content | right inspector */
.si--2r {
  grid-template-columns: 1fr 340px;
}

/* 1-col: full width */
.si--1 {
  grid-template-columns: 1fr;
}

.si__panel {
  position: relative;
  background: var(--v2-bg-card);
  border: 1px solid var(--v2-border-2);
  border-radius: var(--v2-radius-lg);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.si__panel--left {
  overflow-y: auto;
}
.si__panel--main {
  overflow-y: auto;
}
.si__panel--right {
  overflow-y: auto;
}

/* ── Responsive ──────────────────────────────────────── */
@media (max-width: 1400px) {
  .si--3 {
    grid-template-columns: 200px 1fr 280px;
  }
  .si--2r {
    grid-template-columns: 1fr 300px;
  }
}
@media (max-width: 1100px) {
  .si--3 {
    grid-template-columns: 1fr;
    grid-template-rows: auto 1fr auto;
  }
  .si--2l, .si--2r {
    grid-template-columns: 1fr;
  }
  .si {
    min-height: auto;
  }
}
</style>
