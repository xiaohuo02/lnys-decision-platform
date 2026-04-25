import axios from 'axios'

const api = axios.create({ baseURL: '/admin/memory/governance' })

api.interceptors.request.use(cfg => {
  const token = localStorage.getItem('token')
  if (token) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})

export const fetchMemoryHealth = () =>
  api.get('/health').then(r => r.data)

export const fetchMemoryFreshness = (limit = 50, domain, statusFilter) =>
  api.get('/freshness', {
    params: {
      limit,
      ...(domain ? { domain } : {}),
      ...(statusFilter ? { status_filter: statusFilter } : {}),
    },
  }).then(r => r.data)
