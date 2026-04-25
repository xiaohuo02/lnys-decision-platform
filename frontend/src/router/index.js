import { createRouter, createWebHistory } from 'vue-router'
import { setupGuards } from './guards'
import authRoutes from './modules/auth'
import businessRoutes from './modules/business'
import consoleRoutes from './modules/console'
import errorRoutes from './modules/error'

import BusinessLayout from '@/layouts/BusinessLayout.vue'
import ConsoleLayout from '@/layouts/ConsoleLayout.vue'

const routes = [
  // ── 认证页（每个路由自带 AuthLayout，避免 path 冲突） ─────
  ...authRoutes,

  // ── 业务前台 ───────────────────────────────────────────────
  {
    path: '/',
    component: BusinessLayout,
    children: businessRoutes,
  },

  // ── Console 治理控制台 ─────────────────────────────────────
  {
    path: '/console',
    component: ConsoleLayout,
    children: consoleRoutes,
  },

  // ── 兜底 404 ──────────────────────────────────────────────
  ...errorRoutes,
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

setupGuards(router)

export default router
