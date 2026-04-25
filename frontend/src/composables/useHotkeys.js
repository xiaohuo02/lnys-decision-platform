/**
 * useHotkeys — V2 Global Keyboard Shortcut System
 *
 * Provides a centralized hotkey registry with:
 * - Modifier combos (Ctrl+K, Ctrl+Shift+P)
 * - Vim-style sequences (g d, g t)
 * - Auto-skip when user is in input/textarea
 * - Expose registry for help display
 */
import { ref, onMounted, onBeforeUnmount } from 'vue'

const SEQUENCE_TIMEOUT = 600

/** @type {Array<{id:string, keys:string, label:string, group:string, handler:Function, allowInInput?:boolean}>} */
const _registry = ref([])
let _seqBuffer = ''
let _seqTimer = null

function isInputTarget(e) {
  const t = e.target
  return t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable
}

function _handleKeydown(e) {
  const inInput = isInputTarget(e)

  for (const entry of _registry.value) {
    if (inInput && !entry.allowInInput) continue

    // Modifier combos: "ctrl+k", "ctrl+shift+p"
    if (entry.keys.includes('+')) {
      const parts = entry.keys.toLowerCase().split('+')
      const key = parts.pop()
      const needCtrl  = parts.includes('ctrl') || parts.includes('cmd') || parts.includes('meta')
      const needShift = parts.includes('shift')
      const needAlt   = parts.includes('alt')

      if (
        e.key.toLowerCase() === key &&
        (needCtrl  ? (e.ctrlKey || e.metaKey) : true) &&
        (needShift ? e.shiftKey : true) &&
        (needAlt   ? e.altKey : true) &&
        (!needCtrl  || e.ctrlKey || e.metaKey) &&
        (!needShift || e.shiftKey) &&
        (!needAlt   || e.altKey)
      ) {
        // Verify no extra modifiers
        if (!needCtrl && (e.ctrlKey || e.metaKey)) continue
        if (!needShift && e.shiftKey) continue
        e.preventDefault()
        entry.handler(e)
        return
      }
      continue
    }

    // Single key (non-sequence, non-modifier)
    if (entry.keys.length === 1 && !entry.keys.includes(' ')) {
      if (inInput) continue
      if (e.ctrlKey || e.metaKey || e.altKey) continue
      if (e.key === entry.keys) {
        e.preventDefault()
        entry.handler(e)
        return
      }
    }
  }

  // Sequence handling (g d, g t, etc.)
  if (inInput || e.ctrlKey || e.metaKey || e.altKey) return

  clearTimeout(_seqTimer)
  _seqBuffer += e.key
  _seqTimer = setTimeout(() => { _seqBuffer = '' }, SEQUENCE_TIMEOUT)

  for (const entry of _registry.value) {
    if (!entry.keys.includes(' ')) continue
    const seq = entry.keys.replace(/\s+/g, '')
    if (_seqBuffer === seq) {
      _seqBuffer = ''
      clearTimeout(_seqTimer)
      e.preventDefault()
      entry.handler(e)
      return
    }
  }
}

let _listening = false

function _ensureListener() {
  if (_listening) return
  document.addEventListener('keydown', _handleKeydown)
  _listening = true
}

function _removeListener() {
  document.removeEventListener('keydown', _handleKeydown)
  _listening = false
}

/**
 * Register hotkeys in a component.
 * @param {Array<{id:string, keys:string, label:string, group?:string, handler:Function, allowInInput?:boolean}>} bindings
 */
export function useHotkeys(bindings = []) {
  onMounted(() => {
    for (const b of bindings) {
      // Avoid duplicates
      _registry.value = _registry.value.filter(r => r.id !== b.id)
      _registry.value.push({
        group: 'General',
        allowInInput: false,
        ...b,
      })
    }
    _ensureListener()
  })

  onBeforeUnmount(() => {
    const ids = new Set(bindings.map(b => b.id))
    _registry.value = _registry.value.filter(r => !ids.has(r.id))
    if (_registry.value.length === 0) _removeListener()
  })

  return { registry: _registry }
}

/** Get the full hotkey registry (read-only) */
export function getHotkeyRegistry() {
  return _registry
}
