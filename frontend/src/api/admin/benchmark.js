import axios from 'axios'

const api = axios.create({ baseURL: '/admin/evals' })

api.interceptors.request.use(cfg => {
  const token = localStorage.getItem('token')
  if (token) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})

export const fetchBenchmarkSummary = () =>
  api.get('/benchmark/summary').then(r => r.data)
