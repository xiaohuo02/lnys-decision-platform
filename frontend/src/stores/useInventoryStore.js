import { defineStore } from 'pinia'
import { inventoryApi } from '@/api/business/inventory'

export const useInventoryStore = defineStore('inventory', {
  state: () => ({
    loading: false,
    error: null,
    status: null,
    alerts: [],
    abcXyz: null,
    trend: [],
  }),

  getters: {
    alertCount: (state) => state.alerts.length,
    hasData:    (state) => !!state.status,
  },

  actions: {
    async fetchStatus() {
      this.loading = true; this.error = null
      try { this.status = await inventoryApi.getStatus() }
      catch (e) { this.error = e?.response?.data?.message || e.message }
      finally { this.loading = false }
    },

    async fetchAlerts(params) {
      this.loading = true; this.error = null
      try {
        const d = await inventoryApi.getAlerts(params)
        this.alerts = Array.isArray(d) ? d : (d?.data ?? [])
      }
      catch (e) { this.error = e?.response?.data?.message || e.message }
      finally { this.loading = false }
    },

    async fetchAbcXyz() {
      this.loading = true; this.error = null
      try { this.abcXyz = await inventoryApi.getAbcXyz() }
      catch (e) { this.error = e?.response?.data?.message || e.message }
      finally { this.loading = false }
    },

    async fetchTrend(params) {
      try {
        const d = await inventoryApi.getTrend(params)
        this.trend = Array.isArray(d) ? d : (d?.data ?? [])
      }
      catch (e) { this.error = e?.response?.data?.message || e.message }
    },

    reset() { this.status = null; this.alerts = []; this.abcXyz = null; this.trend = []; this.error = null },
  },
})

