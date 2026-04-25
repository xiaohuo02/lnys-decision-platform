/**
 * 三套请求客户端：
 * - requestBusiness : /api/*  业务接口，响应格式 { code, data, message }
 * - requestAdmin    : /admin/* 治理后台接口，响应格式为裸对象
 * - requestWorkflow : /api/v1/* workflow 接口
 *
 * 缓存策略（仅 requestBusiness 的 GET 请求）：
 * - L1 内存缓存（TTL 按接口配置，30~120s）
 * - 请求去重（同 URL 并发 N 次 → 只发 1 次）
 * - Stale-While-Revalidate（过期后先返回旧数据，后台静默刷新）
 */
import axios from 'axios'
import { ElMessage } from 'element-plus'
import {
  cacheKeyOf, ttlFor, isCacheable,
  getEntry, setEntry,
  getInflight, setInflight, removeInflight,
  clearApiCache,
} from '@/utils/apiCache'

export { clearApiCache }

/* ── 公共工具 ───────────────────────────────────────────────── */

function getToken() {
  return localStorage.getItem('token') || ''
}

function injectAuth(config) {
  const token = getToken()
  if (token) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
}

function handleNetworkError(err) {
  if (err.response?.status === 401) {
    // 如果当前已在登录页，或正在登录流程中，不做硬跳转，只透传错误
    const onLoginPage = window.location.pathname === '/login'
    if (!onLoginPage) {
      ElMessage.warning('登录已过期，请重新登录')
      localStorage.removeItem('token')
      localStorage.removeItem('roles')
      localStorage.removeItem('primaryRole')
      // 使用 replace 而非 href 避免全页面刷新导致状态丢失
      window.location.replace('/login')
    }
    return Promise.reject(err)
  }
  // 非 401 错误不在拦截器弹 toast，避免与组件 catch 块产生 double-toast。
  // 组件层统一负责用户提示（ElMessage / 设置 error state）。
  return Promise.reject(err)
}

/**
 * 解包 { code, data, message, meta } 响应，返回 data
 */
function unwrapBusinessBody(body) {
  if (body && (body.code === 0 || body.code === 200)) {
    const data = body.data
    if (data != null && typeof data === 'object' && body.meta) {
      Object.defineProperty(data, '_meta', { value: body.meta, enumerable: false, configurable: true })
    }
    return data
  }
  if (body && body.code === undefined) {
    return body
  }
  return undefined  // 表示业务错误
}

/* ── requestBusiness: /api/* ── 带缓存 ─────────────────────── */

export const requestBusiness = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

requestBusiness.interceptors.request.use(injectAuth)
requestBusiness.interceptors.request.use((config) => {
  if (!isCacheable(config)) return config

  const key = cacheKeyOf(config)
  config._cacheKey = key

  const hit = getEntry(key)
  if (hit && hit.fresh) {
    // ✅ 新鲜缓存命中 → 用自定义 adapter 直接返回，跳过 HTTP 请求
    config.adapter = () => Promise.resolve({
      data: hit.data,
      status: 200,
      statusText: 'OK (cache)',
      headers: {},
      config,
      _fromCache: true,
    })
    return config
  }

  if (hit && !hit.fresh) {
    // ⏳ SWR：标记 stale data，请求继续发出
    config._staleData = hit.data
  }

  // 🔀 请求去重：同 key 正在 inflight → 复用
  const pending = getInflight(key)
  if (pending) {
    config.adapter = () => pending.then(data => ({
      data,
      status: 200,
      statusText: 'OK (dedup)',
      headers: {},
      config,
      _fromCache: true,
    }))
  }

  return config
})

requestBusiness.interceptors.response.use(
  (res) => {
    // 缓存命中 / 去重命中 → data 已经是解包后的数据
    if (res._fromCache) return res.data

    const body = res.data
    const data = unwrapBusinessBody(body)

    // 业务错误
    if (data === undefined) {
      const msg = body?.message || '业务请求异常'
      ElMessage.error(msg)
      return Promise.reject(new Error(msg))
    }

    // 写入缓存 + 清除 inflight
    const key = res.config?._cacheKey
    if (key && data != null) {
      setEntry(key, data, ttlFor(key))
      removeInflight(key)
    }

    return data
  },
  (err) => {
    // SWR 降级：请求失败但有 stale 数据 → 静默返回旧数据
    const config = err.config || {}
    if (config._staleData !== undefined) {
      return Promise.resolve(config._staleData)
    }
    const key = config._cacheKey
    if (key) removeInflight(key)
    return handleNetworkError(err)
  },
)

/* ── requestAdmin: /admin/* ── 裸对象响应（不缓存） ──────────── */

export const requestAdmin = axios.create({
  baseURL: '/admin',
  timeout: 15000,
})

requestAdmin.interceptors.request.use(injectAuth)
requestAdmin.interceptors.response.use(
  (res) => {
    const body = res.data
    // 兼容 ok() / degraded() 包装格式
    if (body && (body.code === 0 || body.code === 200) && body.data !== undefined) {
      const data = body.data
      if (data != null && typeof data === 'object' && body.meta) {
        Object.defineProperty(data, '_meta', { value: body.meta, enumerable: false, configurable: true })
      }
      return data
    }
    return body
  },
  handleNetworkError,
)

/* ── requestWorkflow: /api/v1/* ── workflow 风格（不缓存） ──── */

export const requestWorkflow = axios.create({
  baseURL: '/api/v1',
  timeout: 60000,
})

requestWorkflow.interceptors.request.use(injectAuth)
requestWorkflow.interceptors.response.use(
  (res) => {
    const body = res.data
    // 兼容 ok() 包装的 {code, data, message} 和裸对象两种格式
    if (body && (body.code === 0 || body.code === 200) && body.data !== undefined) {
      const data = body.data
      if (data != null && typeof data === 'object' && body.meta) {
        Object.defineProperty(data, '_meta', { value: body.meta, enumerable: false, configurable: true })
      }
      return data
    }
    // 非 ok() 包装或无 code 字段 → 直接返回裸对象
    return body
  },
  handleNetworkError,
)
