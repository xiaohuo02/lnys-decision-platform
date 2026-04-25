/**
 * API 响应缓存层 — 三大能力:
 *
 * 1. 内存缓存 (TTL)       — GET 响应缓存在内存 Map 中，TTL 过期自动失效
 * 2. 请求去重 (Dedup)      — 同一 URL 并发 N 次，只发 1 次请求，N 个 caller 共享结果
 * 3. Stale-While-Revalidate — TTL 过期后先返回旧数据，后台静默刷新
 *
 * 设计：导出工具函数，由 request.js 在既有拦截器中内联调用，
 * 避免多层 interceptor 顺序问题。
 */

// ── 缓存存储 ──────────────────────────────────────────────────

const _cache = new Map()       // key → { data, timestamp, ttl }
const _inflight = new Map()    // key → Promise<data>（去重用）

// 默认 TTL 规则（秒）
const _TTL_RULES = [
  { match: '/dashboard/kpis',      ttl: 60 },
  { match: '/forecast/summary',    ttl: 120 },
  { match: '/customers/',          ttl: 90 },
  { match: '/inventory/',          ttl: 90 },
  { match: '/fraud/stats',         ttl: 60 },
  { match: '/association/',        ttl: 120 },
  { match: '/sentiment/overview',  ttl: 90 },
  { match: '/sentiment/topics',    ttl: 120 },
]

const _DEFAULT_TTL = 30  // 其他 GET 接口默认 30s
const _SWR_GRACE = 300   // stale-while-revalidate 宽限期（秒）

// ── 工具函数 ──────────────────────────────────────────────────

/**
 * 从 axios config 构建缓存 key
 */
export function cacheKeyOf(config) {
  const url = config.url || ''
  const params = config.params
    ? '?' + new URLSearchParams(config.params).toString()
    : ''
  return `${config.baseURL || ''}${url}${params}`
}

/**
 * 根据 URL 匹配 TTL
 */
export function ttlFor(key) {
  for (const rule of _TTL_RULES) {
    if (key.includes(rule.match)) return rule.ttl
  }
  return _DEFAULT_TTL
}

/**
 * 是否可缓存（仅 GET，且未标记 noCache）
 */
export function isCacheable(config) {
  return (config.method || 'get').toLowerCase() === 'get' && !config.noCache
}

/**
 * 读取缓存条目
 * @returns {{ data: any, fresh: boolean } | null}
 */
export function getEntry(key) {
  const entry = _cache.get(key)
  if (!entry) return null

  const age = (Date.now() - entry.timestamp) / 1000
  if (age <= entry.ttl)                return { data: entry.data, fresh: true }
  if (age <= entry.ttl + _SWR_GRACE)   return { data: entry.data, fresh: false }

  _cache.delete(key)
  return null
}

/**
 * 写入缓存
 */
export function setEntry(key, data, ttl) {
  _cache.set(key, { data, timestamp: Date.now(), ttl })
  // 防止内存泄漏：最多缓存 200 个 key
  if (_cache.size > 200) {
    const oldest = _cache.keys().next().value
    _cache.delete(oldest)
  }
}

/**
 * 请求去重：获取正在进行的请求 Promise
 */
export function getInflight(key)          { return _inflight.get(key) }
export function setInflight(key, promise) { _inflight.set(key, promise) }
export function removeInflight(key)       { _inflight.delete(key) }

/**
 * 手动清除缓存（登出、数据变更后调用）
 */
export function clearApiCache(pattern) {
  if (!pattern) { _cache.clear(); return }
  for (const key of _cache.keys()) {
    if (key.includes(pattern)) _cache.delete(key)
  }
}

/**
 * 获取缓存统计（调试用）
 */
export function getCacheStats() {
  let fresh = 0, stale = 0
  const now = Date.now()
  for (const [, entry] of _cache) {
    const age = (now - entry.timestamp) / 1000
    if (age <= entry.ttl) fresh++
    else stale++
  }
  return { size: _cache.size, fresh, stale }
}
