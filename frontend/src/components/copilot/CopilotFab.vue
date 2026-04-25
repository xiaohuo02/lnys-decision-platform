<template>
  <!-- 右下角浮动按钮 -->
  <button
    class="fab"
    :class="{ 'fab--open': open }"
    :title="open ? '关闭智能助手' : '打开智能助手'"
    @click="toggle"
  >
    <svg v-if="!open" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
    <svg v-else width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  </button>

  <!-- 遮罩 + 抽屉 -->
  <Teleport to="body">
    <Transition name="fab-fade">
      <div v-if="open" class="fab-mask" @click="close" />
    </Transition>
    <Transition name="fab-slide">
      <aside v-if="open" class="fab-drawer" @click.stop>
        <UnifiedCopilotPanel :mode="mode" />
      </aside>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed, watch, onMounted, onBeforeUnmount } from 'vue'
import UnifiedCopilotPanel from './UnifiedCopilotPanel.vue'
import { useCopilotStore } from '@/stores/useCopilotStore'

const props = defineProps({
  mode: { type: String, default: 'biz', validator: v => ['biz', 'ops'].includes(v) },
})

// B.3: open 状态接入 store，支持任何页面通过 copilotStore.toggleDrawer() 唤起
const copilotStore = useCopilotStore()
const open = computed({
  get: () => copilotStore.drawerOpen,
  set: (v) => copilotStore.toggleDrawer(v),
})

// 初始化时同步 Fab 的 mode 到 store
onMounted(() => {
  copilotStore.setMode(props.mode)
  window.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => { window.removeEventListener('keydown', onKey) })

watch(() => props.mode, (m) => copilotStore.setMode(m))

function toggle() { open.value = !open.value }
function close() { open.value = false }

function onKey(e) { if (e.key === 'Escape' && open.value) close() }

// 打开时锁定 body 滚动
watch(open, val => {
  document.body.style.overflow = val ? 'hidden' : ''
})
</script>

<style scoped>
/* ── Floating Action Button ── */
.fab {
  position: fixed;
  right: 24px;
  bottom: 24px;
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: var(--v2-text-1, #18181b);
  color: var(--v2-bg-page, #fff);
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow:
    0 10px 20px -6px rgba(0, 0, 0, 0.18),
    0 4px 8px -2px rgba(0, 0, 0, 0.12);
  z-index: 998;
  transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1),
              box-shadow 0.25s ease,
              background 0.2s ease;
}
.fab:hover {
  transform: translateY(-2px) scale(1.03);
  box-shadow:
    0 14px 28px -8px rgba(0, 0, 0, 0.24),
    0 6px 12px -4px rgba(0, 0, 0, 0.16);
}
.fab:active { transform: scale(0.97); }
.fab--open {
  transform: scale(0.92);
}

/* ── Mask ── */
.fab-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  backdrop-filter: blur(2px);
  z-index: 999;
}

/* ── Drawer ── */
.fab-drawer {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  width: min(480px, 100vw);
  background: var(--v2-bg-page, #fff);
  box-shadow: -16px 0 32px -12px rgba(0, 0, 0, 0.18);
  z-index: 1000;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ── Transitions ── */
.fab-fade-enter-active,
.fab-fade-leave-active {
  transition: opacity 0.2s ease;
}
.fab-fade-enter-from,
.fab-fade-leave-to {
  opacity: 0;
}

.fab-slide-enter-active,
.fab-slide-leave-active {
  transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}
.fab-slide-enter-from,
.fab-slide-leave-to {
  transform: translateX(100%);
}
</style>
