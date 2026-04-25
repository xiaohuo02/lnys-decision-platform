<template>
  <div class="side-nav">
    <div class="side-nav__brand" :class="{ 'side-nav__brand--collapsed': collapsed }">
      <span class="side-nav__logo">柠</span>
      <transition name="fade">
        <div v-if="!collapsed" class="side-nav__brand-text">
          <span class="side-nav__title">柠优生活</span>
          <span class="side-nav__sub">大数据平台</span>
        </div>
      </transition>
    </div>
    <el-menu
      :default-active="activeRoute"
      router
      :collapse="collapsed"
      background-color="transparent"
      text-color="rgba(255,255,255,.65)"
      active-text-color="#ffffff"
      class="side-nav__menu"
    >
      <template v-for="item in visibleItems" :key="item.path">
        <el-menu-item :index="item.path" class="side-nav__item">
          <el-icon><component :is="item.icon" /></el-icon>
          <template #title>{{ item.title }}</template>
        </el-menu-item>
      </template>

      <el-divider v-if="canSeeConsole" class="side-nav__divider" />

      <el-menu-item v-if="canSeeConsole" index="/console/dashboard" class="side-nav__item side-nav__item--switch">
        <el-icon><Setting /></el-icon>
        <template #title>治理控制台</template>
      </el-menu-item>
    </el-menu>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Setting } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/useAuthStore'
import { hasAccess } from '@/constants/roles'
import businessRoutes from '@/router/modules/business'

defineProps({
  collapsed: { type: Boolean, default: false },
})

const route = useRoute()
const auth  = useAuthStore()
const activeRoute = computed(() => '/' + route.path.split('/')[1])
const canSeeConsole = computed(() => auth.canAccessGroup('console'))

const visibleItems = computed(() => {
  return businessRoutes
    .filter(r => r.name && r.meta?.menuGroup === 'business' && !r.meta?.hidden)
    .filter(r => hasAccess(auth.primaryRole, r.meta?.roles))
    .map(r => ({
      path:  '/' + r.path,
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
  background: var(--color-bg-aside);
}

.side-nav__brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 16px 14px;
  border-bottom: 1px solid rgba(255,255,255,.08);
}
.side-nav__brand--collapsed {
  justify-content: center;
  padding: 18px 0 14px;
}

.side-nav__logo {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-md);
  background: var(--color-accent);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 700;
  flex-shrink: 0;
}

.side-nav__brand-text { min-width: 0; }
.side-nav__title { display: block; color: #fff; font-size: 16px; font-weight: 700; letter-spacing: .5px; }
.side-nav__sub   { display: block; color: rgba(255,255,255,.4); font-size: 11px; margin-top: 1px; }

.side-nav__menu {
  border-right: none;
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
}

.side-nav__item {
  margin: 1px 8px;
  border-radius: var(--radius-sm);
  height: 40px;
  line-height: 40px;
}
.side-nav__item.is-active {
  background: rgba(255,255,255,.1) !important;
}
.side-nav__item:hover {
  background: rgba(255,255,255,.06) !important;
}

.side-nav__item--switch {
  color: rgba(255,255,255,.45) !important;
  font-size: var(--font-size-sm);
}

.side-nav__divider {
  border-color: rgba(255,255,255,.08);
  margin: 8px 16px;
}

.fade-enter-active, .fade-leave-active { transition: opacity .2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
