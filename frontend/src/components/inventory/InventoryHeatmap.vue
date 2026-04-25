<template>
  <div class="hm">
    <!-- Row headers -->
    <div class="hm__corner"></div>
    <div class="hm__col-hdr" v-for="x in xLabels" :key="'x'+x">{{ x }}</div>

    <template v-for="a in yLabels" :key="'row'+a">
      <div class="hm__row-hdr">{{ a }}</div>
      <button
        v-for="x in xLabels"
        :key="a+x"
        class="hm__cell"
        :class="[
          `hm__cell--${getCellPriority(a + x)}`,
          { 'hm__cell--active': activeCell === a + x }
        ]"
        @click="$emit('cellClick', a + x)"
        @mouseenter="hovered = a + x"
        @mouseleave="hovered = ''"
      >
        <span class="hm__cell-label">{{ a }}{{ x }}</span>
        <span class="hm__cell-count">{{ getCellCount(a + x) }}</span>
        <Transition name="hm-tooltip">
          <div class="hm__tooltip" v-if="hovered === a + x && getCellStrategy(a + x)">
            {{ getCellStrategy(a + x) }}
          </div>
        </Transition>
      </button>
    </template>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  data:       { type: Array, default: () => [] },
  activeCell: { type: String, default: '' },
})

defineEmits(['cellClick'])

const hovered = ref('')
const yLabels = ['A', 'B', 'C']
const xLabels = ['X', 'Y', 'Z']

const PRIORITY = {
  AX: 'critical', AY: 'critical', AZ: 'high',
  BX: 'high',     BY: 'medium',   BZ: 'medium',
  CX: 'medium',   CY: 'low',      CZ: 'low',
}

function getCellPriority(key) {
  return PRIORITY[key] || 'low'
}

function getCellCount(key) {
  return props.data.filter(i => i.matrix_cell === key).length
}

function getCellStrategy(key) {
  const item = props.data.find(i => i.matrix_cell === key)
  return item?.strategy || ''
}
</script>

<style scoped>
.hm {
  display: grid;
  grid-template-columns: 32px repeat(3, 1fr);
  gap: 4px;
  user-select: none;
}

.hm__corner { }

.hm__col-hdr, .hm__row-hdr {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 600;
  color: var(--v2-text-3, #71717a);
  letter-spacing: 0.5px;
}
.hm__row-hdr {
  font-size: 12px;
}

.hm__cell {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  padding: 12px 6px;
  border-radius: 8px;
  border: 2px solid transparent;
  cursor: pointer;
  transition: all 0.15s ease;
  background: none;
  font-family: inherit;
}

.hm__cell--critical { background: rgba(239, 68, 68, 0.08); }
.hm__cell--critical:hover { background: rgba(239, 68, 68, 0.14); }

.hm__cell--high { background: rgba(245, 158, 11, 0.08); }
.hm__cell--high:hover { background: rgba(245, 158, 11, 0.14); }

.hm__cell--medium { background: rgba(59, 130, 246, 0.06); }
.hm__cell--medium:hover { background: rgba(59, 130, 246, 0.1); }

.hm__cell--low { background: rgba(0, 0, 0, 0.03); }
.hm__cell--low:hover { background: rgba(0, 0, 0, 0.06); }

.hm__cell--active {
  border-color: #18181b;
  box-shadow: 0 0 0 1px rgba(24, 24, 27, 0.15);
}

.hm__cell-label {
  font-size: 11px;
  font-weight: 500;
  color: var(--v2-text-2, #3f3f46);
}

.hm__cell-count {
  font-size: 20px;
  font-weight: 700;
  line-height: 1;
  color: var(--v2-text-1, #18181b);
  font-variant-numeric: tabular-nums;
}

.hm__tooltip {
  position: absolute;
  bottom: calc(100% + 6px);
  left: 50%;
  transform: translateX(-50%);
  white-space: nowrap;
  padding: 4px 10px;
  border-radius: 6px;
  background: #18181b;
  color: #fff;
  font-size: 11px;
  font-weight: 400;
  z-index: 10;
  pointer-events: none;
}
.hm__tooltip::after {
  content: '';
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  border: 4px solid transparent;
  border-top-color: #18181b;
}

.hm-tooltip-enter-active { transition: opacity 0.12s, transform 0.12s; }
.hm-tooltip-leave-active { transition: opacity 0.08s; }
.hm-tooltip-enter-from { opacity: 0; transform: translateX(-50%) translateY(2px); }
.hm-tooltip-leave-to { opacity: 0; }
</style>
