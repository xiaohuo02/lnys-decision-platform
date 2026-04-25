import { defineStore } from 'pinia'
import { authApi } from '@/api/admin/index'
import { ROLES, hasAccess, canSeeGroup } from '@/constants/roles'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('token') || '',
    user: null,
    roles: JSON.parse(localStorage.getItem('roles') || '[]'),
    primaryRole: localStorage.getItem('primaryRole') || '',
    loading: false,
    error: null,
    initialized: false,
  }),

  getters: {
    isLoggedIn:  (state) => !!state.token,
    username:    (state) => state.user?.username || localStorage.getItem('username') || '',
    displayName: (state) => state.user?.display_name || state.user?.username || '',
    roleLabel:   (state) => ROLES[state.primaryRole]?.label || '未知角色',
    isAdmin:     (state) => ['super_admin', 'platform_admin', 'business_admin'].includes(state.primaryRole),
    isEmployee:  (state) => state.primaryRole === 'employee',
    isReadOnly:  (state) => state.primaryRole === 'employee',

    canAccessGroup: (state) => (group) => canSeeGroup(state.primaryRole, group),
    canAccessRoute: (state) => (allowedRoles) => hasAccess(state.primaryRole, allowedRoles),
  },

  actions: {
    async register(form) {
      this.loading = true
      this.error = null
      try {
        const res = await authApi.register(form)
        return res
      } catch (e) {
        this.error = e?.response?.data?.message || e?.message || '注册失败'
        throw e
      } finally {
        this.loading = false
      }
    },

    async login(form) {
      this.loading = true
      this.error = null
      try {
        const res = await authApi.login(form)
        const token = res?.access_token ?? res?.token ?? ''
        if (!token) throw new Error('未获取到有效 token')

        this._setToken(token)

        // 从登录响应中直接提取角色信息，不依赖 fetchMe
        // fallback 角色: 取 DB roles 表的默认角色 'employee'（最小只读权限）
        const username = res?.username || form.username
        const roles = res?.roles || (res?.role ? [res.role] : ['employee'])
        this.user = { username }
        this.roles = roles
        this.primaryRole = roles[0] || 'employee'
        localStorage.setItem('username', username)
        localStorage.setItem('roles', JSON.stringify(roles))
        localStorage.setItem('primaryRole', this.primaryRole)
        this.initialized = true

        // fetchMe 仅用于补充完整用户信息，失败不影响登录
        try { await this.fetchMe() } catch { /* optional enrichment */ }

        return true
      } catch (e) {
        this.error = e?.response?.data?.message || e?.message || '登录失败'
        throw e
      } finally {
        this.loading = false
      }
    },

    async fetchMe() {
      if (!this.token) return
      try {
        const res = await authApi.me()
        this.user = res
        const roles = res?.roles || (res?.role ? [res.role] : this.roles)
        this.roles = roles
        this.primaryRole = roles[0] || this.primaryRole
        localStorage.setItem('roles', JSON.stringify(roles))
        localStorage.setItem('primaryRole', this.primaryRole)
        this.initialized = true
      } catch {
        // 不调用 logout — 保留已有 token 和角色数据
        if (!this.initialized) this.initialized = true
      }
    },

    async initAuth() {
      if (this.initialized || !this.token) return
      await this.fetchMe()
    },

    logout() {
      this.token = ''
      this.user = null
      this.roles = []
      this.primaryRole = ''
      this.initialized = false
      localStorage.removeItem('token')
      localStorage.removeItem('username')
      localStorage.removeItem('roles')
      localStorage.removeItem('primaryRole')
    },

    _setToken(token) {
      this.token = token
      localStorage.setItem('token', token)
    },
  },
})
