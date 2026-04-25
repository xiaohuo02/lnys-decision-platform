import { defineStore } from 'pinia'
import { forecastApi } from '@/api/business/forecast'

export const useForecastStore = defineStore('forecast', {
  state: () => ({
    loading: false,
    error: null,
    summary: null,
    prediction: null,
  }),

  getters: {
    hasData: (state) => !!state.summary,
  },

  actions: {
    async fetchSummary() {
      this.loading = true; this.error = null
      try { this.summary = await forecastApi.getSummary() }
      catch (e) { this.error = e?.response?.data?.message || e.message }
      finally { this.loading = false }
    },

    async predict(params) {
      this.loading = true; this.error = null
      try { this.prediction = await forecastApi.predict(params) }
      catch (e) { this.error = e?.response?.data?.message || e.message }
      finally { this.loading = false }
    },

    reset() { this.summary = null; this.prediction = null; this.error = null },
  },
})

