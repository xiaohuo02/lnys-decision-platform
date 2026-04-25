<template>
  <Teleport to="body">
    <Transition :name="transitionName">
      <div v-if="modelValue" class="v2-drawer__overlay" @click.self="close">
        <div class="v2-drawer" :class="[`v2-drawer--${placement}`, `v2-drawer--${size}`]">
          <div class="v2-drawer__hd">
            <span class="v2-drawer__title">{{ title }}</span>
            <span v-if="subtitle" class="v2-drawer__subtitle">{{ subtitle }}</span>
            <div class="v2-drawer__hd-actions">
              <slot name="header-actions" />
              <button class="v2-drawer__close" @click="close">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>
              </button>
            </div>
          </div>
          <div class="v2-drawer__body">
            <slot />
          </div>
          <div v-if="$slots.footer" class="v2-drawer__ft">
            <slot name="footer" />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed, watch, onUnmounted } from 'vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  title:      { type: String, default: '' },
  subtitle:   { type: String, default: '' },
  placement:  { type: String, default: 'right', validator: v => ['right', 'left', 'bottom'].includes(v) },
  size:       { type: String, default: 'md', validator: v => ['sm', 'md', 'lg', 'full'].includes(v) },
  closeOnEsc: { type: Boolean, default: true },
})
const emit = defineEmits(['update:modelValue', 'close'])

const transitionName = computed(() => `v2-drawer-${props.placement}`)

function close() {
  emit('update:modelValue', false)
  emit('close')
}

function onKeydown(e) {
  if (e.key === 'Escape' && props.closeOnEsc && props.modelValue) close()
}

watch(() => props.modelValue, (v) => {
  if (v) {
    document.addEventListener('keydown', onKeydown)
    document.body.style.overflow = 'hidden'
  } else {
    document.removeEventListener('keydown', onKeydown)
    document.body.style.overflow = ''
  }
})

onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
  document.body.style.overflow = ''
})
</script>

<style scoped>
.v2-drawer__overlay {
  position: fixed;
  inset: 0;
  z-index: var(--v2-z-drawer);
  background: var(--v2-bg-overlay);
  display: flex;
}

.v2-drawer {
  background: var(--v2-bg-elevated);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Placement */
.v2-drawer--right { margin-left: auto; height: 100%; border-left: var(--v2-border-width) solid var(--v2-border-1); }
.v2-drawer--left  { margin-right: auto; height: 100%; border-right: var(--v2-border-width) solid var(--v2-border-1); }
.v2-drawer--bottom { margin-top: auto; width: 100%; border-top: var(--v2-border-width) solid var(--v2-border-1); max-height: 80vh; }

/* Sizes */
.v2-drawer--right.v2-drawer--sm,
.v2-drawer--left.v2-drawer--sm  { width: 320px; }
.v2-drawer--right.v2-drawer--md,
.v2-drawer--left.v2-drawer--md  { width: 480px; }
.v2-drawer--right.v2-drawer--lg,
.v2-drawer--left.v2-drawer--lg  { width: 640px; }
.v2-drawer--right.v2-drawer--full,
.v2-drawer--left.v2-drawer--full { width: 90vw; max-width: 960px; }

.v2-drawer--bottom.v2-drawer--sm { height: 30vh; }
.v2-drawer--bottom.v2-drawer--md { height: 50vh; }
.v2-drawer--bottom.v2-drawer--lg { height: 70vh; }

/* Header */
.v2-drawer__hd {
  display: flex;
  align-items: center;
  gap: var(--v2-space-2);
  padding: var(--v2-space-4) var(--v2-space-5);
  border-bottom: var(--v2-border-width) solid var(--v2-border-2);
  flex-shrink: 0;
}
.v2-drawer__title {
  font-size: var(--v2-text-md);
  font-weight: var(--v2-font-semibold);
  color: var(--v2-text-1);
}
.v2-drawer__subtitle {
  font-size: var(--v2-text-xs);
  color: var(--v2-text-4);
}
.v2-drawer__hd-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: var(--v2-space-2);
}
.v2-drawer__close {
  width: 28px; height: 28px;
  display: flex; align-items: center; justify-content: center;
  background: transparent;
  border: none;
  color: var(--v2-text-3);
  cursor: pointer;
  border-radius: var(--v2-radius-sm);
  transition: var(--v2-trans-fast);
}
.v2-drawer__close:hover { color: var(--v2-text-1); background: var(--v2-bg-hover); }

/* Body */
.v2-drawer__body {
  flex: 1;
  overflow-y: auto;
  padding: var(--v2-space-4) var(--v2-space-5);
}

/* Footer */
.v2-drawer__ft {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--v2-space-2);
  padding: var(--v2-space-3) var(--v2-space-5);
  border-top: var(--v2-border-width) solid var(--v2-border-2);
  flex-shrink: 0;
}

/* Transitions — Right */
.v2-drawer-right-enter-active { transition: opacity .25s ease; }
.v2-drawer-right-enter-active .v2-drawer { transition: transform .3s cubic-bezier(0.16,1,0.3,1); }
.v2-drawer-right-leave-active { transition: opacity .2s ease; }
.v2-drawer-right-leave-active .v2-drawer { transition: transform .2s ease; }
.v2-drawer-right-enter-from { opacity: 0; }
.v2-drawer-right-enter-from .v2-drawer { transform: translateX(100%); }
.v2-drawer-right-leave-to { opacity: 0; }
.v2-drawer-right-leave-to .v2-drawer { transform: translateX(100%); }

/* Transitions — Left */
.v2-drawer-left-enter-active { transition: opacity .25s ease; }
.v2-drawer-left-enter-active .v2-drawer { transition: transform .3s cubic-bezier(0.16,1,0.3,1); }
.v2-drawer-left-leave-active { transition: opacity .2s ease; }
.v2-drawer-left-leave-active .v2-drawer { transition: transform .2s ease; }
.v2-drawer-left-enter-from { opacity: 0; }
.v2-drawer-left-enter-from .v2-drawer { transform: translateX(-100%); }
.v2-drawer-left-leave-to { opacity: 0; }
.v2-drawer-left-leave-to .v2-drawer { transform: translateX(-100%); }

/* Transitions — Bottom */
.v2-drawer-bottom-enter-active { transition: opacity .25s ease; }
.v2-drawer-bottom-enter-active .v2-drawer { transition: transform .3s cubic-bezier(0.16,1,0.3,1); }
.v2-drawer-bottom-leave-active { transition: opacity .2s ease; }
.v2-drawer-bottom-leave-active .v2-drawer { transition: transform .2s ease; }
.v2-drawer-bottom-enter-from { opacity: 0; }
.v2-drawer-bottom-enter-from .v2-drawer { transform: translateY(100%); }
.v2-drawer-bottom-leave-to { opacity: 0; }
.v2-drawer-bottom-leave-to .v2-drawer { transform: translateY(100%); }

@media (max-width: 768px) {
  .v2-drawer--right, .v2-drawer--left { width: 100% !important; }
}
</style>
