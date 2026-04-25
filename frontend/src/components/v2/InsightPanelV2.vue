<template>
  <div class="ip" :class="{ 'ip--expanded': expanded }">
    <button class="ip__trigger" @click="expanded = !expanded">
      <span class="ip__icon">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
          <path d="M8 1.5a3 3 0 013 3v.25c0 .966-.393 1.84-1.028 2.472L9.5 7.694V9.5a.5.5 0 01-.5.5H7a.5.5 0 01-.5-.5V7.694l-.472-.472A3.49 3.49 0 015 4.75V4.5a3 3 0 013-3z" fill="currentColor"/>
          <path d="M6.5 11.5h3v.5a1.5 1.5 0 01-3 0v-.5z" fill="currentColor"/>
        </svg>
      </span>
      <span class="ip__label">{{ label }}</span>
      <el-icon :size="12" class="ip__arrow" :class="{ 'ip__arrow--open': expanded }"><ArrowDown /></el-icon>
    </button>
    <transition name="ip-slide">
      <div v-if="expanded" class="ip__body">
        <slot>
          <p class="ip__text">{{ text }}</p>
        </slot>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'

defineProps({
  label: { type: String, default: 'AI 洞察' },
  text:  { type: String, default: '' },
})

const expanded = ref(false)
</script>

<style scoped>
.ip {
  border: 1px solid var(--v2-border-2);
  border-radius: var(--v2-radius-lg);
  background: var(--v2-ai-purple-bg);
  overflow: hidden;
  transition: border-color var(--v2-trans-fast);
}
.ip--expanded { border-color: var(--v2-ai-purple); }

.ip__trigger {
  display: flex;
  align-items: center;
  gap: var(--v2-space-2);
  width: 100%;
  padding: var(--v2-space-3) var(--v2-space-4);
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: var(--v2-text-sm);
  color: var(--v2-ai-purple);
  font-weight: var(--v2-font-medium);
}
.ip__trigger:hover { background: rgba(124,58,237,.05); }

.ip__icon { display: flex; align-items: center; }
.ip__arrow { transition: transform var(--v2-trans-fast); margin-left: auto; }
.ip__arrow--open { transform: rotate(180deg); }

.ip__body {
  padding: 0 var(--v2-space-4) var(--v2-space-4);
}
.ip__text {
  font-size: var(--v2-text-base);
  color: var(--v2-text-2);
  line-height: var(--v2-leading-relaxed);
  margin: 0;
}

.ip-slide-enter-active { transition: all .2s ease; }
.ip-slide-leave-active { transition: all .15s ease; }
.ip-slide-enter-from, .ip-slide-leave-to { opacity: 0; max-height: 0; padding-top: 0; padding-bottom: 0; }
.ip-slide-enter-to, .ip-slide-leave-from { opacity: 1; max-height: 300px; }
</style>
