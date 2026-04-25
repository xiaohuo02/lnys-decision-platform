import { defineStore } from 'pinia'
import { fraudApi } from '@/api/business/fraud'

export const useFraudStore = defineStore('fraud', {
  state: () => ({
    loading: false,
    error: null,
    stats: null,
    pendingReviews: [],
    lastScore: null,
  }),

  getters: {
    pendingCount: (state) => state.pendingReviews.length,
    hasStats:     (state) => !!state.stats,
  },

  actions: {
    async fetchStats() {
      this.loading = true; this.error = null
      try { this.stats = await fraudApi.getStats() }
      catch (e) { this.error = e?.response?.data?.message || e.message }
      finally { this.loading = false }
    },

    async fetchPendingReviews() {
      this.loading = true; this.error = null
      try { this.pendingReviews = await fraudApi.getPendingReviews() }
      catch (e) { this.error = e?.response?.data?.message || e.message }
      finally { this.loading = false }
    },

    async score(data) {
      this.loading = true; this.error = null
      try { this.lastScore = await fraudApi.score(data) }
      catch (e) { this.error = e?.response?.data?.message || e.message }
      finally { this.loading = false }
    },

    reset() { this.stats = null; this.pendingReviews = []; this.lastScore = null; this.error = null },
  },
})

