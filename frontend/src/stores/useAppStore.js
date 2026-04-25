import { defineStore } from 'pinia'

export const useAppStore = defineStore('app', {
  state: () => ({
    sidebarCollapsed: localStorage.getItem('sidebarCollapsed') === 'true',
    tableDensity: localStorage.getItem('tableDensity') || 'default',
    globalLoading: false,
    notifications: [],
  }),

  getters: {
    unreadCount: (state) => state.notifications.filter(n => !n.read).length,
    isCompact:   (state) => state.tableDensity === 'compact',
  },

  actions: {
    toggleSidebar() {
      this.sidebarCollapsed = !this.sidebarCollapsed
      localStorage.setItem('sidebarCollapsed', String(this.sidebarCollapsed))
    },

    setTableDensity(val) {
      this.tableDensity = val
      localStorage.setItem('tableDensity', val)
    },

    addNotification(msg) {
      this.notifications.unshift({ id: Date.now(), message: msg, read: false, time: new Date().toISOString() })
    },

    markAllRead() {
      this.notifications.forEach(n => { n.read = true })
    },

    setGlobalLoading(val) { this.globalLoading = val },
  },
})

