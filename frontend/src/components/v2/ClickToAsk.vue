<template>
  <component :is="tag" class="cta" :class="{ 'cta--active': hovered }" @mouseenter="hovered = true" @mouseleave="hovered = false" @click="onClick">
    <slot />
    <Transition name="cta-tip">
      <span v-if="hovered && !disabled" class="cta__tip">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
        {{ tipText }}
      </span>
    </Transition>
  </component>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  question: { type: String, required: true },
  context: { type: Object, default: () => ({}) },
  tag: { type: String, default: 'div' },
  tipText: { type: String, default: '询问 AI' },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['ask'])
const hovered = ref(false)

function onClick(e) {
  if (props.disabled) return
  emit('ask', { question: props.question, context: props.context })
}
</script>

<style scoped>
.cta { position: relative; cursor: pointer; transition: background 0.15s; border-radius: 6px; }
.cta:hover { background: rgba(0,0,0,0.02); }
.cta__tip {
  position: absolute; top: -28px; left: 50%; transform: translateX(-50%);
  display: flex; align-items: center; gap: 4px;
  padding: 4px 10px; border-radius: 6px;
  background: #18181b; color: #fff; font-size: 11px; white-space: nowrap;
  pointer-events: none; z-index: 20;
  box-shadow: 0 2px 8px rgba(0,0,0,0.15);
}
.cta-tip-enter-active { transition: opacity 0.12s, transform 0.12s; }
.cta-tip-leave-active { transition: opacity 0.08s; }
.cta-tip-enter-from { opacity: 0; transform: translateX(-50%) translateY(4px); }
.cta-tip-leave-to { opacity: 0; }
</style>
