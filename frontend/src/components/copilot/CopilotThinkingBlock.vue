<template>
  <div class="cop-think" :class="{ 'cop-think--active': active }">
    <div class="cop-think__hd" @click="expanded = !expanded">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>
      <span class="cop-think__label">{{ active ? 'Thinking...' : 'Thought process' }}</span>
      <svg class="cop-think__chevron" :class="{ 'cop-think__chevron--open': expanded }" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="6 9 12 15 18 9"/></svg>
    </div>
    <Transition name="cop-think-slide">
      <div class="cop-think__body" v-show="expanded">
        <div class="cop-think__text">{{ text }}</div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
const props = defineProps({ text: String, active: Boolean })
const expanded = ref(true)
watch(() => props.active, (v) => { if (!v) expanded.value = false })
</script>

<style scoped>
.cop-think { border: 1px solid rgba(0,0,0,0.04); border-radius: 8px; margin: 8px 0; overflow: hidden; }
.cop-think--active { border-color: rgba(0,0,0,0.08); }
.cop-think__hd { display: flex; align-items: center; gap: 8px; padding: 8px 12px; cursor: pointer; font-size: 12px; color: #71717a; user-select: none; }
.cop-think__hd:hover { background: rgba(0,0,0,0.02); }
.cop-think__label { flex: 1; }
.cop-think__chevron { transition: transform 0.2s; }
.cop-think__chevron--open { transform: rotate(180deg); }
.cop-think__body { padding: 8px 12px 12px; }
.cop-think__text { font-size: 12px; line-height: 1.6; color: #71717a; font-family: 'Geist Mono', monospace; white-space: pre-wrap; max-height: 200px; overflow: auto; }
.cop-think-slide-enter-active, .cop-think-slide-leave-active { transition: all 0.2s ease; }
.cop-think-slide-enter-from, .cop-think-slide-leave-to { opacity: 0; max-height: 0; }
</style>
