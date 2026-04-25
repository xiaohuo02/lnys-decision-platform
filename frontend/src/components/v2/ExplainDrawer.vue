<template>
  <Teleport to="body">
    <transition name="drawer">
      <div v-if="visible" class="ed-overlay" @click.self="close">
        <aside class="ed">
          <div class="ed__header">
            <div class="ed__header-left">
              <AIInlineLabel size="sm" />
              <h3 class="ed__title">{{ title }}</h3>
            </div>
            <button class="ed__close" @click="close">&times;</button>
          </div>
          <div class="ed__body">
            <slot>
              <div v-if="loading" class="ed__loading">
                <SkeletonBlockV2 :rows="6" />
              </div>
              <div v-else class="ed__content" v-html="content" />
            </slot>
          </div>
          <div v-if="$slots.footer" class="ed__footer">
            <slot name="footer" />
          </div>
        </aside>
      </div>
    </transition>
  </Teleport>
</template>

<script setup>
import AIInlineLabel from './AIInlineLabel.vue'
import SkeletonBlockV2 from './SkeletonBlockV2.vue'

defineProps({
  visible: { type: Boolean, default: false },
  title:   { type: String, default: '解释' },
  content: { type: String, default: '' },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['update:visible', 'close'])

function close() {
  emit('update:visible', false)
  emit('close')
}
</script>

<style scoped>
.ed-overlay {
  position: fixed;
  inset: 0;
  z-index: var(--v2-z-modal);
  background: var(--v2-bg-overlay);
  display: flex;
  justify-content: flex-end;
}

.ed {
  width: 420px;
  max-width: 90vw;
  height: 100vh;
  background: var(--v2-bg-card);
  display: flex;
  flex-direction: column;
  box-shadow: var(--v2-shadow-xl);
}

.ed__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--v2-space-4) var(--v2-space-5);
  border-bottom: 1px solid var(--v2-border-2);
  flex-shrink: 0;
}
.ed__header-left {
  display: flex;
  align-items: center;
  gap: var(--v2-space-2);
}
.ed__title {
  font-size: var(--v2-text-md);
  font-weight: var(--v2-font-semibold);
  color: var(--v2-text-1);
  margin: 0;
}
.ed__close {
  width: 28px; height: 28px;
  border: none;
  border-radius: var(--v2-radius-md);
  background: transparent;
  font-size: 18px;
  color: var(--v2-text-3);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all var(--v2-trans-fast);
}
.ed__close:hover { background: var(--v2-bg-hover); color: var(--v2-text-1); }

.ed__body {
  flex: 1;
  overflow-y: auto;
  padding: var(--v2-space-5);
}
.ed__content {
  font-size: var(--v2-text-md);
  color: var(--v2-text-2);
  line-height: var(--v2-leading-relaxed);
}
.ed__content :deep(code) {
  font-family: var(--v2-font-mono);
  font-size: var(--v2-text-sm);
  background: var(--v2-bg-sunken);
  padding: 1px 4px;
  border-radius: var(--v2-radius-sm);
}

.ed__footer {
  padding: var(--v2-space-3) var(--v2-space-5);
  border-top: 1px solid var(--v2-border-2);
  background: var(--v2-bg-sunken);
  flex-shrink: 0;
}

/* Transitions */
.drawer-enter-active { transition: opacity .2s ease; }
.drawer-enter-active .ed { transition: transform .25s var(--v2-ease); }
.drawer-leave-active { transition: opacity .15s ease .05s; }
.drawer-leave-active .ed { transition: transform .2s var(--v2-ease); }
.drawer-enter-from { opacity: 0; }
.drawer-enter-from .ed { transform: translateX(100%); }
.drawer-leave-to { opacity: 0; }
.drawer-leave-to .ed { transform: translateX(100%); }
</style>
