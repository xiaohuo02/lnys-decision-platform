/**
 * useCopilotStore — 全局 Copilot 会话 Store（B.2）
 *
 * 职责：
 *   - 全站单一 thread + messages 历史（跨页继承）
 *   - 页面级上下文栈：页面 onMounted 时 pushContext，onUnmounted 时 popContext
 *   - 包装 useCopilotStream 提供流式能力
 *   - 提供 ask / stop / switchThread / startNewThread / loadThreads 入口
 *
 * 设计要点：
 *   - `usePageCopilot` 作为 per-page 适配层保留（避免破坏现有 9 个业务页面）
 *   - 新页面建议直接用 `useCopilotStore`
 *   - 全局 Drawer 通过 store 消费状态，page 面板依然能各自 mount PageAICopilotPanel
 *
 * 与 usePageCopilot 的区别：
 *   - usePageCopilot: 每页一个 thread，消息不跨页
 *   - useCopilotStore: 全站一个 thread，消息跨页延续；页面只负责 push/pop context
 */
import { defineStore } from 'pinia'
import { ref, computed, shallowRef } from 'vue'
import { useCopilotStream } from '@/composables/useCopilotStream'
import {
  listThreads,
  getThreadMessages,
  submitFeedback,
  executeAction,
  COPILOT_STREAM_URL,
} from '@/api/admin/copilot'

export const useCopilotStore = defineStore('copilot', () => {
  // ── Stream (单例，跨页共享流式能力) ───────────────────
  const stream = useCopilotStream()

  // ── Thread ──
  const currentThreadId = ref('')
  const threadHistory = shallowRef([])
  const threadLoading = ref(false)

  // ── Messages ──
  const messages = ref([])

  // ── Page Context Stack ──
  //   每项: { page, data, registeredAt }
  //   顶部是当前页的 context，会被 ask() 自动注入到 page_context
  const contextStack = ref([])

  // ── UI State ──
  const drawerOpen = ref(false)
  const mode = ref('biz')  // 'biz' | 'ops'
  const degraded = ref(false)

  // ── Derived ──
  const currentPageContext = computed(() => {
    const top = contextStack.value[contextStack.value.length - 1]
    return top ? top.data : {}
  })

  const currentPage = computed(() => {
    const top = contextStack.value[contextStack.value.length - 1]
    return top ? top.page : ''
  })

  // ── Context Stack Actions ──

  function pushContext(page, data = {}) {
    contextStack.value.push({ page, data, registeredAt: Date.now() })
  }

  function popContext(page) {
    // 只弹指定 page 的最近一条，防止串页
    for (let i = contextStack.value.length - 1; i >= 0; i--) {
      if (contextStack.value[i].page === page) {
        contextStack.value.splice(i, 1)
        return
      }
    }
  }

  function updateContext(page, patch = {}) {
    for (let i = contextStack.value.length - 1; i >= 0; i--) {
      if (contextStack.value[i].page === page) {
        contextStack.value[i].data = { ...contextStack.value[i].data, ...patch }
        return
      }
    }
  }

  function clearContext() {
    contextStack.value = []
  }

  // ── Thread Actions ──

  async function loadThreads(pageOrigin = null) {
    threadLoading.value = true
    try {
      const res = await listThreads({
        mode: mode.value,
        ...(pageOrigin ? { page_origin: pageOrigin } : {}),
        limit: 20,
      })
      threadHistory.value = res.data?.threads || res.threads || []
    } catch {
      threadHistory.value = []
    } finally {
      threadLoading.value = false
    }
  }

  async function switchThread(threadId) {
    currentThreadId.value = threadId
    messages.value = []
    try {
      const res = await getThreadMessages(threadId, { limit: 50 })
      const raw = res.data?.messages || res.messages || []
      messages.value = raw.map(_formatMsg)
    } catch {
      messages.value = []
    }
  }

  function startNewThread() {
    currentThreadId.value = ''
    messages.value = []
    stream.reset()
  }

  async function resumeLastThread() {
    if (!threadHistory.value.length) await loadThreads()
    if (!threadHistory.value.length) return false
    const last = threadHistory.value[0]
    await switchThread(last.id)
    return true
  }

  // ── Ask ──

  /**
   * 发起一个 ask，自动拼装当前页面 context 和 mentions
   * @param {string} question
   * @param {object} options — { mentions, mode, pageOverride }
   */
  async function ask(question, options = {}) {
    const q = (question || '').trim()
    if (!q) return

    if (stream.streaming.value) {
      stream.stop()
    }

    messages.value.push({
      role: 'user',
      content: q,
      timestamp: Date.now(),
    })

    const effectiveMode = options.mode || mode.value
    const url = COPILOT_STREAM_URL[effectiveMode] || COPILOT_STREAM_URL.biz
    const effectivePage = options.pageOverride || currentPage.value || 'global'

    try {
      await stream.send(
        url,
        {
          question: q,
          thread_id: currentThreadId.value || undefined,
          mode: effectiveMode,
          page_context: {
            page: effectivePage,
            think_mode: options.thinkMode || 'auto',
            mentions: options.mentions || [],
            ...currentPageContext.value,
          },
        },
        {
          onDone: (result) => {
            if (result.threadId && !currentThreadId.value) {
              currentThreadId.value = result.threadId
            }
            messages.value.push({
              role: 'assistant',
              content: stream.text.value,
              thinking: stream.thinking.value,
              skill: stream.activeSkill.value?.displayName || stream.activeSkill.value?.name || '',
              artifacts: [...stream.artifacts.value],
              suggestions: [...stream.suggestions.value],
              sources: [...stream.sources.value],
              intent: stream.intent.value,
              confidence: stream.confidence.value,
              feedback: null,
              messageId: null,
              _showSources: false,
              timestamp: Date.now(),
            })
            loadThreads()
          },
          onError: () => {
            degraded.value = true
          },
        },
      )
    } catch {
      degraded.value = true
    }
  }

  function askAgent(skillId, question) {
    return ask(question, { mentions: [{ type: 'skill', id: skillId }] })
  }

  // ── Feedback / Action ──

  async function setFeedback(msg, value) {
    msg.feedback = value
    if (msg.messageId) {
      try { await submitFeedback(msg.messageId, value) } catch { /* silent */ }
    }
  }

  async function confirmAction(item) {
    const confirmed = window.confirm(`执行操作: ${item.label}?`)
    if (!confirmed) return
    try {
      await executeAction(
        item.action,
        item.payload?.group || item.payload?.target || '',
        item.payload,
        currentThreadId.value,
      )
    } catch (e) {
      console.error('[copilot-store:action]', e)
    }
  }

  // ── UI ──

  function toggleDrawer(next) {
    drawerOpen.value = typeof next === 'boolean' ? next : !drawerOpen.value
  }

  function setMode(m) {
    if (m === 'biz' || m === 'ops') mode.value = m
  }

  // ── Helpers ──

  function _formatMsg(m) {
    return {
      role: m.role,
      content: m.content,
      thinking: m.thinking || '',
      skill: m.skills_used?.[0] || '',
      artifacts: m.artifacts || [],
      suggestions: m.suggestions || [],
      sources: m.sources || [],
      intent: m.intent || '',
      confidence: m.confidence || 0,
      feedback: m.feedback,
      messageId: m.id,
      _showSources: false,
      timestamp: m.created_at ? new Date(m.created_at).getTime() : 0,
    }
  }

  function stop() {
    stream.stop()
  }

  return {
    // State
    currentThreadId,
    threadHistory,
    threadLoading,
    messages,
    contextStack,
    drawerOpen,
    mode,
    degraded,
    // Stream state (re-export)
    streaming: stream.streaming,
    text: stream.text,
    thinking: stream.thinking,
    isThinking: stream.isThinking,
    activeSkill: stream.activeSkill,
    artifacts: stream.artifacts,
    suggestions: stream.suggestions,
    sources: stream.sources,
    error: stream.error,
    elapsedMs: stream.elapsedMs,
    // Derived
    currentPageContext,
    currentPage,
    // Context
    pushContext,
    popContext,
    updateContext,
    clearContext,
    // Thread
    loadThreads,
    switchThread,
    startNewThread,
    resumeLastThread,
    // Chat
    ask,
    askAgent,
    stop,
    // Actions
    setFeedback,
    confirmAction,
    // UI
    toggleDrawer,
    setMode,
  }
})
