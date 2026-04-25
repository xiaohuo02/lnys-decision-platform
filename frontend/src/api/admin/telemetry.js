import axios from 'axios'

const api = axios.create({ baseURL: '/admin/telemetry' })

api.interceptors.request.use(cfg => {
  const token = localStorage.getItem('token')
  if (token) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})

export const fetchTelemetrySummary = (runId) =>
  api.get('/summary', { params: runId ? { run_id: runId } : {} }).then(r => r.data)

export const fetchTelemetryEvents = (limit = 50, eventType) =>
  api.get('/events', { params: { limit, ...(eventType ? { event_type: eventType } : {}) } }).then(r => r.data)

export const fetchTelemetryCounters = () =>
  api.get('/counters').then(r => r.data)

export const fetchContextDiagnostics = (currentTokens = 0, threadId) =>
  api.get('/context', { params: { current_tokens: currentTokens, ...(threadId ? { thread_id: threadId } : {}) } }).then(r => r.data)

export const fetchModelRouting = () =>
  api.get('/models').then(r => r.data)
