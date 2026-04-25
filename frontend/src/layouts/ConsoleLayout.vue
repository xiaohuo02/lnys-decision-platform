<template>
  <div class="cl">
    <AppSidebarV2 :collapsed="collapsed" variant="console" />
    <div class="cl__main-wrap">
      <HeaderBarV2 :collapsed="collapsed" compact @toggle-collapse="app.toggleSidebar" />
      <main class="cl__main">
        <router-view v-slot="{ Component }">
          <transition name="page" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </main>
    </div>
    <!-- 运维助手：右下角浮动入口（与业务前台对称） -->
    <CopilotFab mode="ops" />
  </div>
</template>

<script setup>
import { storeToRefs } from 'pinia'
import AppSidebarV2 from '@/components/v2/AppSidebarV2.vue'
import HeaderBarV2  from '@/components/v2/HeaderBarV2.vue'
import CopilotFab   from '@/components/copilot/CopilotFab.vue'
import { setLayoutDefault } from '@/composables/useTheme'
import { useAppStore } from '@/stores/useAppStore'

const app = useAppStore()
const { sidebarCollapsed: collapsed } = storeToRefs(app)
// Force dark mode for the console layout (Zinc 950 deep black)
setLayoutDefault('dark')
</script>

<style scoped>
.cl {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: var(--v2-bg-page); /* Will be pure black in dark mode */
}
.cl__main-wrap {
  flex: 1;
  position: relative;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}
.cl__main {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  /* Add top padding for the floating glass header */
  padding: calc(var(--v2-header-height) + var(--v2-space-3)) var(--v2-space-6) var(--v2-space-6);
  scroll-behavior: smooth;
}
</style>
