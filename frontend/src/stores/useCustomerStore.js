import { defineStore } from 'pinia'
import { customersApi } from '@/api/business/customers'

export const useCustomerStore = defineStore('customer', {
  state: () => ({
    loading: false,
    error: null,
    rfmData: null,
    segments: [],
    clvData: null,
    churnRisk: null,
  }),

  getters: {
    segmentCount: (state) => state.segments.length,
    hasData:      (state) => !!(state.rfmData || state.segments.length || state.clvData),
  },

  actions: {
    async fetchRfm(params = {}) {
      this.loading = true; this.error = null
      try { this.rfmData = await customersApi.getRfm(params) }
      catch (e) { this.error = e?.response?.data?.message || e.message }
      finally { this.loading = false }
    },

    async fetchSegments() {
      this.loading = true; this.error = null
      try { this.segments = await customersApi.getSegments() }
      catch (e) { this.error = e?.response?.data?.message || e.message }
      finally { this.loading = false }
    },

    async fetchClv(params = {}) {
      this.loading = true; this.error = null
      try { this.clvData = await customersApi.getClv(params) }
      catch (e) { this.error = e?.response?.data?.message || e.message }
      finally { this.loading = false }
    },

    async fetchChurnRisk(params = {}) {
      this.loading = true; this.error = null
      try { this.churnRisk = await customersApi.getChurnRisk(params) }
      catch (e) { this.error = e?.response?.data?.message || e.message }
      finally { this.loading = false }
    },

    reset() {
      this.rfmData = null; this.segments = []; this.clvData = null; this.churnRisk = null; this.error = null
    },
  },
})

