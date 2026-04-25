/**
 * 时间工具函数
 *
 * 后端存储 UTC 时间，序列化带 +00:00 后缀。
 * 此模块提供安全解析 + 常用格式化，确保即使后端返回 naive ISO 字符串
 * （无时区后缀）也能正确按 UTC 解析，避免 8 小时偏移。
 */

/**
 * 安全解析服务端时间字符串。
 * 如果 ISO 字符串没有时区后缀（T 分隔且无 Z/+/-），追加 Z 强制按 UTC 解析。
 * @param {string|Date|null} v
 * @returns {Date|null}
 */
export function parseServerTime(v) {
  if (!v) return null
  if (v instanceof Date) return isNaN(v) ? null : v
  const s = String(v)
  // 已有时区信息（Z 或 +/-HH:MM）→ 直接解析
  if (/[Zz]$/.test(s) || /[+-]\d{2}:\d{2}$/.test(s)) {
    const d = new Date(s)
    return isNaN(d) ? null : d
  }
  // 含 T 分隔符的 ISO 格式但无时区 → 追加 Z
  if (s.includes('T')) {
    const d = new Date(s + 'Z')
    return isNaN(d) ? null : d
  }
  // 其他格式 fallback
  const d = new Date(s)
  return isNaN(d) ? null : d
}

/** 相对时间："刚刚" / "3 分钟前" / "2 小时前" / "昨天" / "MM-DD HH:mm" */
export function fmtRelative(v) {
  const d = parseServerTime(v)
  if (!d) return '-'
  const diff = Date.now() - d.getTime()
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return Math.floor(diff / 60000) + ' 分钟前'
  if (diff < 86400000) return Math.floor(diff / 3600000) + ' 小时前'
  if (diff < 172800000) return '昨天'
  const pad = n => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** 完整时间："YYYY-MM-DD HH:mm:ss" */
export function fmtFull(v) {
  const d = parseServerTime(v)
  if (!d) return '-'
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

/** 短时间："MM-DD HH:mm" */
export function fmtShort(v) {
  const d = parseServerTime(v)
  if (!d) return ''
  const pad = n => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** 时分："HH:mm" */
export function fmtHM(v) {
  const d = parseServerTime(v)
  if (!d) return ''
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
