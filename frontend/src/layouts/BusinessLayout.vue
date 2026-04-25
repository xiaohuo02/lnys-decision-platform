<template>
  <div class="bl">
    <AppSidebarV2 :collapsed="collapsed" variant="business" />
    <div class="bl__main-wrap">
      <HeaderBarV2 :collapsed="collapsed" @toggle-collapse="app.toggleSidebar" />
      <!-- 员工只读横幅 -->
      <div v-if="auth.isReadOnly" class="bl__readonly-bar">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
        当前为只读模式 — 您的账号尚未获得管理员授权，暂时仅可查看数据
      </div>
      <main class="bl__main" @click.capture="interceptReadonly">
        <router-view v-slot="{ Component }">
          <transition name="page" mode="out-in">
            <keep-alive :include="['AnalyzeProgress']">
              <component :is="Component" />
            </keep-alive>
          </transition>
        </router-view>
      </main>
    </div>
    <!-- 智能助手：右下角浮动入口（降为浮层，不再占主导航位） -->
    <CopilotFab mode="biz" />
  </div>
</template>

<script setup>
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'
import AppSidebarV2 from '@/components/v2/AppSidebarV2.vue'
import HeaderBarV2  from '@/components/v2/HeaderBarV2.vue'
import CopilotFab   from '@/components/copilot/CopilotFab.vue'
import { setLayoutDefault } from '@/composables/useTheme'
import { useAuthStore } from '@/stores/useAuthStore'
import { useAppStore } from '@/stores/useAppStore'

const app = useAppStore()
const { sidebarCollapsed: collapsed } = storeToRefs(app)
const auth = useAuthStore()
setLayoutDefault('light')

const INTERACTIVE_TAGS = new Set(['BUTTON', 'A', 'SELECT', 'TEXTAREA'])
const INTERACTIVE_TYPES = new Set(['submit', 'button', 'checkbox', 'radio', 'file'])

function interceptReadonly(e) {
  if (!auth.isReadOnly) return
  const el = e.target
  const tag = el.tagName
  const type = el.getAttribute?.('type') || ''
  const isLink = tag === 'A' && !el.getAttribute('href')?.startsWith('/')
  const isInteractive =
    INTERACTIVE_TAGS.has(tag) ||
    (tag === 'INPUT' && INTERACTIVE_TYPES.has(type)) ||
    el.closest('button') ||
    el.closest('[role="button"]') ||
    el.getAttribute('contenteditable') === 'true'

  if (isInteractive && !isLink) {
    e.preventDefault()
    e.stopPropagation()
    ElMessage.warning({ message: '无操作权限，请等待管理员授权', grouping: true, duration: 2000 })
  }
}
</script>

<style scoped>
.bl {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: var(--v2-bg-page);
}
.bl__main-wrap {
  flex: 1;
  position: relative;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}
.bl__main {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  /* Add top padding for the floating glass header */
  padding: calc(var(--v2-header-height) + var(--v2-space-3)) var(--v2-space-6) var(--v2-space-6);
  scroll-behavior: smooth;
}

.bl__readonly-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  margin-top: var(--v2-header-height);
  background: var(--v2-warning-bg);
  color: var(--v2-warning-text);
  font-size: var(--v2-text-sm);
  font-weight: var(--v2-font-medium);
  border-bottom: var(--v2-border-width) solid var(--v2-warning);
  z-index: var(--v2-z-sticky);
}
.bl__readonly-bar + .bl__main {
  padding-top: var(--v2-space-6);
}
</style>
