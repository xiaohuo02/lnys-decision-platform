import { defineStore } from 'pinia'
import { sentimentApi } from '@/api/business/sentiment'

export const useSentimentStore = defineStore('sentiment', {
  state: () => ({
    loading: false,
    error: null,
    overview: null,
    topics: [],
    lastAnalysis: null,
  }),

  getters: {
    topicCount: (state) => state.topics.length,
    hasData:    (state) => !!state.overview,
  },

  actions: {
    async fetchOverview() {
      this.loading = true; this.error = null
      try { this.overview = await sentimentApi.getOverview() }
      catch (e) { this.error = e?.response?.data?.message || e.message }
      finally { this.loading = false }
    },

    async fetchTopics() {
      this.loading = true; this.error = null
      try { this.topics = await sentimentApi.getTopics() }
      catch (e) { this.error = e?.response?.data?.message || e.message }
      finally { this.loading = false }
    },

    async analyze(data) {
      this.loading = true; this.error = null
      try { this.lastAnalysis = await sentimentApi.analyze(data) }
      catch (e) { this.error = e?.response?.data?.message || e.message }
      finally { this.loading = false }
    },

    reset() { this.overview = null; this.topics = []; this.lastAnalysis = null; this.error = null },
  },
})

