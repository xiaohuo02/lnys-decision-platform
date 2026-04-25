/**
 * 路由守卫
 * 1. 未登录 → /login
 * 2. 已登录但未初始化 → initAuth
 * 3. 无角色权限 → /403
 * 4. 设置页面标题
 */
import { useAuthStore } from '@/stores/useAuthStore'

const APP_TITLE = '柠优生活大数据平台'

export function setupGuards(router) {
  router.beforeEach(async (to, _from, next) => {
    document.title = `${to.meta.title || '平台总览'} · ${APP_TITLE}`

    const auth = useAuthStore()

    // 已登录用户访问 login/register 页 → 跳转首页（必须在 public 检查之前）
    if ((to.name === 'Login' || to.name === 'Register') && auth.isLoggedIn) {
      // 走 '/' 让 router 按首屏 redirect 规则决定目标（目前指向 /analyze）
      next('/')
      return
    }

    // public 路由直接放行
    if (to.meta.public) {
      next()
      return
    }

    // 未登录 → login
    if (!auth.isLoggedIn) {
      next({ name: 'Login', query: { redirect: to.fullPath } })
      return
    }

    // 已登录但未初始化用户信息 → 尝试获取
    if (!auth.initialized) {
      await auth.initAuth()
    }

    // 员工角色：禁止进入控制台
    if (auth.isEmployee && to.path.startsWith('/console')) {
      next({ name: 'Forbidden' })
      return
    }

    // 角色权限检查
    const allowedRoles = to.meta.roles
    if (allowedRoles && allowedRoles.length > 0 && !auth.canAccessRoute(allowedRoles)) {
      next({ name: 'Forbidden' })
      return
    }

    next()
  })
}
