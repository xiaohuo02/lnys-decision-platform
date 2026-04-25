import { ref, computed, readonly } from 'vue'

/**
 * 主题管理 composable
 *
 * 策略：
 *   - Console 默认深色，Business 默认浅色
 *   - 用户手动切换后存入 localStorage，优先级最高
 *   - 通过 html[data-theme="dark"] 属性驱动 CSS 变量切换
 */

const STORAGE_KEY = 'lnys-theme'

/** 'light' | 'dark' */
const current = ref('light')

/** 是否已由用户手动设置过 */
let userExplicit = false

/** 模块级 computed — 所有 useTheme() 调用共享同一个响应式引用 */
const isDark = computed(() => current.value === 'dark')

/* ── 底层操作 ─────────────────────────────────────────────── */

function applyToDOM(theme) {
  const html = document.documentElement
  html.setAttribute('data-theme', theme)
  // 同步 Element Plus 暗色类名（部分第三方组件依赖此类名）
  html.classList.toggle('dark', theme === 'dark')
}

function persist(theme) {
  try { localStorage.setItem(STORAGE_KEY, theme) } catch { /* SSR / 隐私模式 */ }
}

function readStorage() {
  try { return localStorage.getItem(STORAGE_KEY) } catch { return null }
}

/* ── 对外 API ─────────────────────────────────────────────── */

/**
 * 初始化主题（在 main.js 中调用一次）
 * @param {'light'|'dark'} fallback - 没有用户偏好时的默认值
 */
export function initTheme(fallback = 'light') {
  const stored = readStorage()
  if (stored === 'light' || stored === 'dark') {
    current.value = stored
    userExplicit = true
  } else {
    current.value = fallback
  }
  applyToDOM(current.value)
}

/**
 * 按布局设置默认主题（仅在用户未手动切换时生效）
 * @param {'light'|'dark'} layoutDefault
 */
export function setLayoutDefault(layoutDefault) {
  if (!userExplicit) {
    current.value = layoutDefault
    applyToDOM(current.value)
  }
}

export function useTheme() {
  /** 切换暗色 ↔ 亮色 */
  function toggle() {
    current.value = current.value === 'dark' ? 'light' : 'dark'
    userExplicit = true
    applyToDOM(current.value)
    persist(current.value)
  }

  /** 直接设置主题 */
  function set(theme) {
    if (theme !== 'light' && theme !== 'dark') return
    current.value = theme
    userExplicit = true
    applyToDOM(current.value)
    persist(current.value)
  }

  return {
    /** 当前主题 'light' | 'dark' */
    theme: readonly(current),
    /** 是否暗色模式 */
    isDark,
    toggle,
    set,
  }
}
