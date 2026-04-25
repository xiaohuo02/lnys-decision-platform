import { defineStore } from 'pinia'
import { chatApi } from '@/api/business/chat'

export const useChatStore = defineStore('chat', {
  state: () => ({
    loading: false,
    error: null,
    messages: [],
    sessionId: null,
    streaming: false,
  }),

  getters: {
    messageCount: (state) => state.messages.length,
    lastMessage:  (state) => state.messages[state.messages.length - 1] || null,
    hasSession:   (state) => !!state.sessionId,
  },

  actions: {
    async fetchHistory(sessionId) {
      this.loading = true; this.error = null
      try {
        this.sessionId = sessionId
        const res = await chatApi.getHistory(sessionId)
        this.messages = res?.messages ?? (Array.isArray(res) ? res : [])
      }
      catch (e) { this.error = e?.response?.data?.message || e.message }
      finally { this.loading = false }
    },

    addMessage(msg) {
      this.messages.push({ id: Date.now(), time: new Date().toISOString(), ...msg })
    },

    setStreaming(val) { this.streaming = val },

    newSession() {
      this.sessionId = `sess_${Date.now()}`
      this.messages = []
      this.error = null
    },

    reset() { this.messages = []; this.sessionId = null; this.error = null; this.streaming = false },
  },
})

