/**
 * usePageCopilot — 页面级 Copilot composable
 *
 * 封装 useCopilotStream，为业务页面提供开箱即用的 AI 对话能力：
 *  - 自动注入 page_context（页面名称 + 动态上下文）
 *  - Thread 管理（创建 / 恢复 / 切换 / 跳转独立 Copilot 页）
 *  - Skill 作用域引导（defaultSkills + @ 手动扩展）
 *  - AI 后端不可用时的优雅降级
 *
 * @example
 *   const ai = usePageCopilot('inventory', ['inventory_skill', 'kb_rag'])
 *   onMounted(() => ai.init())
 *   ai.ask('当前库存健康概览')
 */
import { ref, readonly, onUnmounted, onMounted } from 'vue'
import { useCopilotStream } from './useCopilotStream'
import { useCopilotStore } from '@/stores/useCopilotStore'
import {
  listThreads,
  getThreadMessages,
  submitFeedback,
  executeAction,
  COPILOT_STREAM_URL,
} from '@/api/admin/copilot'

/**
 * @param {string}   pageName      — 页面标识，用于 page_origin / page_context.page
 * @param {string[]} defaultSkills — 默认关联的 skill id 列表（引导路由，不做硬性屏蔽）
 * @param {object}   options       — { mode: 'biz'|'ops' }
 */
export function usePageCopilot(pageName, defaultSkills = [], options = {}) {
  const mode = options.mode || 'biz'
  const copilot = useCopilotStream()

  // B.4: 向全局 CopilotStore 上报当前页 context
  // 页面级对话状态保持本地独立（向后兼容），但全局 Drawer 可感知当前页。
  const copilotStore = useCopilotStore()
  onMounted(() => { copilotStore.pushContext(pageName, {}) })
  onUnmounted(() => { copilotStore.popContext(pageName) })

  // ── Messages ──
  const messages = ref([])
  const pageContext = ref({})

  // ── Thread Management ──
  const currentThreadId = ref('')
  const threadHistory = ref([])
  const threadLoading = ref(false)

  // ── Degradation ──
  const degraded = ref(false)

  // ── Context ──

  function setContext(ctx) {
    pageContext.value = { ...pageContext.value, ...ctx }
    // B.4: 同步到全局 Store，让 Drawer 能读到
    copilotStore.updateContext(pageName, pageContext.value)
  }

  function clearContext() {
    pageContext.value = {}
    copilotStore.updateContext(pageName, {})
  }

  // ── Thread Operations ──

  async function loadPageThreads() {
    threadLoading.value = true
    try {
      const res = await listThreads({
        mode,
        page_origin: pageName,
        limit: 20,
      })
      threadHistory.value = res.data?.threads || res.threads || []
    } catch {
      threadHistory.value = []
    } finally {
      threadLoading.value = false
    }
  }

  async function resumeLastThread() {
    await loadPageThreads()
    if (!threadHistory.value.length) return false
    const last = threadHistory.value[0]
    currentThreadId.value = last.id
    try {
      const res = await getThreadMessages(last.id, { limit: 50 })
      const raw = res.data?.messages || res.messages || []
      messages.value = raw.map(_formatMsg)
      return true
    } catch {
      return false
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
    copilot.reset()
  }

  function openInFullCopilot(router) {
    if (!currentThreadId.value) return
    router.push({
      name: 'BizCopilot',
      query: { thread_id: currentThreadId.value },
    })
  }

  // ── Ask ──

  async function ask(question, extraMentions = []) {
    const q = (question || '').trim()
    if (!q) return

    // Stop previous streaming
    if (copilot.streaming.value) {
      copilot.stop()
    }

    messages.value.push({
      role: 'user',
      content: q,
      timestamp: Date.now(),
    })

    const mentions = [
      ...defaultSkills.map(id => ({ type: 'skill', id })),
      ...extraMentions,
    ]

    const url = COPILOT_STREAM_URL[mode] || COPILOT_STREAM_URL.biz

    try {
      await copilot.send(url, {
        question: q,
        thread_id: currentThreadId.value || undefined,
        mode,
        page_context: {
          page: pageName,
          think_mode: 'auto',
          mentions,
          ...pageContext.value,
        },
      }, {
        onDone: (result) => {
          if (result.threadId && !currentThreadId.value) {
            currentThreadId.value = result.threadId
          }
          messages.value.push({
            role: 'assistant',
            content: copilot.text.value,
            thinking: copilot.thinking.value,
            skill: copilot.activeSkill.value?.displayName
              || copilot.activeSkill.value?.name
              || '',
            artifacts: [...copilot.artifacts.value],
            suggestions: [...copilot.suggestions.value],
            sources: [...copilot.sources.value],
            intent: copilot.intent.value,
            confidence: copilot.confidence.value,
            feedback: null,
            messageId: null,
            _showSources: false,
            timestamp: Date.now(),
          })
          // Refresh thread list
          loadPageThreads()
        },
        onError: () => {
          degraded.value = true
        },
      })
    } catch {
      degraded.value = true
    }
  }

  /**
   * 快捷方法：触发特定 Agent/Skill
   */
  function askAgent(skillId, question) {
    return ask(question, [{ type: 'skill', id: skillId }])
  }

  /**
   * 跨智能体调用 — 注入临时上下文后触发目标 skill
   * @param {string} skillId  — 目标 skill
   * @param {string} question — 问题
   * @param {object} extraCtx — 额外注入的上下文（一次性）
   */
  function askCrossAgent(skillId, question, extraCtx = {}) {
    if (extraCtx && Object.keys(extraCtx).length) {
      setContext(extraCtx)
    }
    return ask(question, [{ type: 'skill', id: skillId }])
  }

  /**
   * 数据→AI 联动 — 注入数据上下文后提问（配合 ClickToAsk 组件）
   * @param {string} question   — 自然语言问题
   * @param {object} dataContext — 绑定的数据行/字段上下文
   */
  function askWithData(question, dataContext = {}) {
    setContext(dataContext)
    return ask(question)
  }

  // ── Actions ──

  async function handleSuggestion(item) {
    if (item.type === 'question') {
      await ask(item.label)
    } else if (item.type === 'action') {
      await confirmAction(item)
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
      console.error('[page-copilot:action]', e)
    }
  }

  async function setFeedback(msg, value) {
    msg.feedback = value
    if (msg.messageId) {
      try { await submitFeedback(msg.messageId, value) } catch { /* silent */ }
    }
  }

  // ── Init ──

  async function init() {
    const resumed = await resumeLastThread()
    return resumed
  }

  // ── Cleanup ──

  function stop() {
    copilot.stop()
  }

  onUnmounted(() => {
    stop()
  })

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

  return {
    // Stream state (readonly)
    streaming: copilot.streaming,
    text: copilot.text,
    thinking: copilot.thinking,
    isThinking: copilot.isThinking,
    activeSkill: copilot.activeSkill,
    artifacts: copilot.artifacts,
    suggestions: copilot.suggestions,
    sources: copilot.sources,
    error: copilot.error,
    elapsedMs: copilot.elapsedMs,

    // Page-level state
    messages,
    pageContext: readonly(pageContext),
    currentThreadId: readonly(currentThreadId),
    threadHistory: readonly(threadHistory),
    threadLoading: readonly(threadLoading),
    degraded: readonly(degraded),

    // Context
    setContext,
    clearContext,

    // Thread operations
    loadPageThreads,
    resumeLastThread,
    switchThread,
    startNewThread,
    openInFullCopilot,

    // Chat
    ask,
    askAgent,
    askCrossAgent,
    askWithData,
    stop,
    init,

    // Interactions
    handleSuggestion,
    confirmAction,
    setFeedback,
  }
}
