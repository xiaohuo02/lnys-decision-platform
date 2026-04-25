import { ref, readonly, shallowRef, onUnmounted } from 'vue'

/**
 * Copilot SSE Stream Composable
 *
 * AG-UI inspired event protocol handler.
 * Parses 16+ event types from /admin/copilot/stream or /api/copilot/stream.
 *
 * Events parsed:
 *   run_start, run_end, run_error,
 *   text_delta,
 *   thinking_start, thinking_delta, thinking_end,
 *   tool_call_start, tool_call_args, tool_call_end, tool_result,
 *   artifact_start, artifact_delta, artifact_end,
 *   suggestions,
 *   intent, confidence, sources, memory_updated
 */
export function useCopilotStream() {
  const streaming    = ref(false)
  const text         = ref('')
  const thinking     = ref('')
  const isThinking   = ref(false)
  const error        = ref(null)
  const threadId     = ref('')
  const elapsedMs    = ref(0)
  const tokenUsage   = shallowRef(null)

  // Current active skill/tool call
  const activeSkill  = ref(null)

  // Artifacts — each { type, metadata, content, closed }
  const artifacts    = ref([])

  // Suggestions — array of { type, label, action?, payload? }
  const suggestions  = ref([])

  // Intent & confidence from the routing step
  const intent       = ref('')
  const confidence   = ref(0)
  const sources      = ref([])

  // Memory events
  const memoryEvents = ref([])

  // ── Decision Chain (governance visibility) ──
  const decisionSteps  = ref([])   // { step, detail, data, ts }
  const contextStatus  = ref(null) // { status, tokens, max_tokens, usage_pct, compacted, ... }
  const securityChecks = ref([])   // { check_type, passed, detail, hits }
  const memoryLayers   = ref([])   // { layer, count, keys }
  const skillCacheHit  = ref(null) // { skill, reason }

  let abortCtrl = null

  function reset() {
    streaming.value    = false
    text.value         = ''
    thinking.value     = ''
    isThinking.value   = false
    error.value        = null
    activeSkill.value  = null
    artifacts.value    = []
    suggestions.value  = []
    intent.value       = ''
    confidence.value   = 0
    sources.value      = []
    memoryEvents.value = []
    decisionSteps.value  = []
    contextStatus.value  = null
    securityChecks.value = []
    memoryLayers.value   = []
    skillCacheHit.value  = null
    elapsedMs.value    = 0
    tokenUsage.value   = null
  }

  /**
   * Send a question and stream the response.
   *
   * @param {string} url   — SSE endpoint
   * @param {object} body  — { question, thread_id?, page_context?, mode? }
   * @param {object} [callbacks] — optional { onEvent, onDone, onError }
   */
  async function send(url, body, callbacks = {}) {
    stop()
    reset()
    streaming.value = true

    abortCtrl = new AbortController()
    const token = localStorage.getItem('token') || ''

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(body),
        signal: abortCtrl.signal,
      })

      if (!response.ok) {
        error.value = `HTTP ${response.status}`
        streaming.value = false
        callbacks.onError?.(error.value)
        return
      }

      // Read thread ID from header
      const hdrThread = response.headers.get('X-Thread-Id')
      if (hdrThread) threadId.value = hdrThread

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const raw = line.slice(6).trim()
          if (!raw || raw === '[DONE]') continue

          try {
            const evt = JSON.parse(raw)
            handleEvent(evt, callbacks)
          } catch {
            // ignore malformed JSON
          }
        }
      }

      // Process remaining buffer
      if (buffer.startsWith('data: ')) {
        const raw = buffer.slice(6).trim()
        if (raw && raw !== '[DONE]') {
          try { handleEvent(JSON.parse(raw), callbacks) } catch { /* */ }
        }
      }

    } catch (err) {
      if (err.name !== 'AbortError') {
        error.value = err.message
        callbacks.onError?.(err.message)
      }
    } finally {
      streaming.value = false
      callbacks.onDone?.({
        text: text.value,
        threadId: threadId.value,
        elapsedMs: elapsedMs.value,
      })
    }
  }

  function handleEvent(evt, callbacks = {}) {
    const type = evt.type
    callbacks.onEvent?.(evt)

    switch (type) {
      case 'run_start':
        if (evt.metadata?.thread_id) threadId.value = evt.metadata.thread_id
        break

      case 'run_end':
        elapsedMs.value = evt.metadata?.elapsed_ms || 0
        if (evt.data?.token_usage) tokenUsage.value = evt.data.token_usage
        break

      case 'run_error':
        error.value = evt.content || 'Unknown error'
        break

      // ── Text ──
      case 'text_delta':
        text.value += evt.content || ''
        break

      // ── Thinking ──
      case 'thinking_start':
        isThinking.value = true
        thinking.value = ''
        break
      case 'thinking_delta':
        thinking.value += evt.content || ''
        break
      case 'thinking_end':
        isThinking.value = false
        break

      // ── Tool/Skill Call ──
      case 'tool_call_start':
        activeSkill.value = {
          name: evt.metadata?.skill || '',
          displayName: evt.metadata?.display_name || '',
          loading: true,
        }
        break
      case 'tool_call_args':
        // optional: update activeSkill args
        break
      case 'tool_call_end':
        if (activeSkill.value) activeSkill.value.loading = false
        break
      case 'tool_result':
        // data is available via artifacts
        break

      // ── Artifacts (GenUI) ──
      case 'artifact_start':
        artifacts.value.push({
          type: evt.artifact_type || 'unknown',
          metadata: evt.metadata || {},
          content: null,
          closed: false,
        })
        break
      case 'artifact_delta': {
        const last = artifacts.value[artifacts.value.length - 1]
        if (last) {
          if (last.content && typeof last.content === 'object' && typeof evt.content === 'object') {
            last.content = { ...last.content, ...evt.content }
          } else {
            last.content = evt.content
          }
        }
        break
      }
      case 'artifact_end': {
        const lastA = artifacts.value[artifacts.value.length - 1]
        if (lastA) lastA.closed = true
        break
      }

      // ── Suggestions ──
      case 'suggestions':
        suggestions.value = evt.items || []
        break

      // ── Metadata ──
      case 'intent':
        intent.value = evt.content || ''
        break
      case 'confidence':
        confidence.value = evt.content || 0
        break
      case 'sources':
        sources.value = evt.items || []
        break

      // ── Memory ──
      case 'memory_updated':
        memoryEvents.value.push(evt.content || '')
        break

      // ── Decision Chain (governance) ──
      case 'decision_step':
        decisionSteps.value.push({
          step: evt.content || '',
          detail: evt.metadata?.detail || '',
          data: evt.data || null,
          ts: evt.ts || Date.now() / 1000,
        })
        break
      case 'context_status':
        contextStatus.value = evt.metadata || {}
        break
      case 'security_check':
        securityChecks.value.push({
          check_type: evt.metadata?.check_type || '',
          passed: evt.metadata?.passed ?? true,
          detail: evt.metadata?.detail || '',
          hits: evt.items || [],
        })
        break
      case 'memory_recall':
        memoryLayers.value.push({
          layer: evt.metadata?.layer || '',
          count: evt.metadata?.count || 0,
          keys: (evt.items || []).map(i => i.key),
        })
        break
      case 'skill_cache_hit':
        skillCacheHit.value = evt.metadata || {}
        break
    }
  }

  function stop() {
    if (abortCtrl) {
      abortCtrl.abort()
      abortCtrl = null
    }
    streaming.value = false
  }

  onUnmounted(() => stop())

  return {
    // State
    streaming:    readonly(streaming),
    text:         readonly(text),
    thinking:     readonly(thinking),
    isThinking:   readonly(isThinking),
    error:        readonly(error),
    threadId:     readonly(threadId),
    elapsedMs:    readonly(elapsedMs),
    tokenUsage:   readonly(tokenUsage),
    activeSkill:  readonly(activeSkill),
    artifacts:    readonly(artifacts),
    suggestions:  readonly(suggestions),
    intent:       readonly(intent),
    confidence:   readonly(confidence),
    sources:      readonly(sources),
    memoryEvents: readonly(memoryEvents),
    // Decision chain governance
    decisionSteps:  readonly(decisionSteps),
    contextStatus:  readonly(contextStatus),
    securityChecks: readonly(securityChecks),
    memoryLayers:   readonly(memoryLayers),
    skillCacheHit:  readonly(skillCacheHit),
    // Actions
    send,
    stop,
    reset,
  }
}
