<template>
  <div class="side-nav">
    <div class="side-nav__brand" :class="{ 'side-nav__brand--collapsed': collapsed }">
      <span class="side-nav__logo side-nav__logo--console">C</span>
      <transition name="fade">
        <div v-if="!collapsed" class="side-nav__brand-text">
          <span class="side-nav__title">Console</span>
          <span class="side-nav__sub">AI Governance</span>
        </div>
      </transition>
    </div>
    <el-menu
      :default-active="activeRoute"
      router
      :collapse="collapsed"
      background-color="transparent"
      text-color="rgba(255,255,255,.6)"
      active-text-color="#ffffff"
      class="side-nav__menu"
    >
      <template v-for="item in visibleItems" :key="item.path">
        <el-menu-item :index="item.path" class="side-nav__item">
          <el-icon><component :is="item.icon" /></el-icon>
          <template #title>{{ item.title }}</template>
        </el-menu-item>
      </template>

      <el-divider class="side-nav__divider" />

      <el-menu-item index="/dashboard" class="side-nav__item side-nav__item--switch">
        <el-icon><DataAnalysis /></el-icon>
        <template #title>业务工作台</template>
      </el-menu-item>
    </el-menu>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { DataAnalysis } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/useAuthStore'
import { hasAccess } from '@/constants/roles'
import consoleRoutes from '@/router/modules/console'

defineProps({
  collapsed: { type: Boolean, default: false },
})

const route = useRoute()
const auth  = useAuthStore()
const activeRoute = computed(() => route.path)

const visibleItems = computed(() => {
  return consoleRoutes
    .filter(r => r.name && r.meta?.menuGroup === 'console' && !r.meta?.hidden)
    .filter(r => hasAccess(auth.primaryRole, r.meta?.roles))
    .map(r => ({
      path:  '/console/' + r.path,
      title: r.meta.title,
      icon:  r.meta.icon,
    }))
})
</script>

<style scoped>
.side-nav {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--color-bg-console);
}

.side-nav__brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 16px 14px;
  border-bottom: 1px solid rgba(255,255,255,.06);
}
.side-nav__brand--collapsed {
  justify-content: center;
  padding: 18px 0 14px;
}

.side-nav__logo {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  font-weight: 700;
  flex-shrink: 0;
}
.side-nav__logo--console {
  background: rgba(255,255,255,.1);
  color: #fff;
  border: 1px solid rgba(255,255,255,.15);
}

.side-nav__brand-text { min-width: 0; }
.side-nav__title { display: block; color: #fff; font-size: 16px; font-weight: 700; letter-spacing: 1px; }
.side-nav__sub   { display: block; color: rgba(255,255,255,.35); font-size: 10px; margin-top: 1px; text-transform: uppercase; letter-spacing: 1.5px; }

.side-nav__menu {
  border-right: none;
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
}

.side-nav__item {
  margin: 1px 8px;
  border-radius: var(--radius-sm);
  height: 38px;
  line-height: 38px;
  font-size: var(--font-size-body);
}
.side-nav__item.is-active {
  background: rgba(255,255,255,.08) !important;
}
.side-nav__item:hover {
  background: rgba(255,255,255,.05) !important;
}

.side-nav__item--switch {
  color: rgba(255,255,255,.4) !important;
  font-size: var(--font-size-sm);
}

.side-nav__divider {
  border-color: rgba(255,255,255,.06);
  margin: 8px 16px;
}

.fade-enter-active, .fade-leave-active { transition: opacity .2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
