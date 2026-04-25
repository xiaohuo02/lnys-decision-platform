import { ref, readonly, onUnmounted } from 'vue'

/**
 * SSE 聊天流式 composable
 *
 * 支持逐 token 流式输出，适配 OpenClaw / OpsCopilot 聊天场景。
 *
 * 后端 SSE 事件格式:
 *   event: token        data: { content: "..." }
 *   event: tool_call    data: { tool: "...", input: {...}, status: "..." }
 *   event: done         data: { intent?, confidence?, sources? }
 *   event: error        data: { message: "..." }
 *
 * 使用:
 *   const { streaming, streamText, streamMeta, send, stop } = useChatStream()
 *   await send('/api/v1/chat/stream', { message: '...', thread_id: '...' })
 */

export function useChatStream() {
  const streaming  = ref(false)      // 是否正在接收流
  const streamText = ref('')         // 当前累积的文本
  const streamMeta = ref(null)       // done 事件携带的元数据 (intent/confidence/sources)
  const error      = ref(null)

  let abortCtrl = null

  function reset() {
    streaming.value  = false
    streamText.value = ''
    streamMeta.value = null
    error.value      = null
  }

  /**
   * 发起流式聊天请求 (POST + SSE)
   * @param {string} url    - SSE 端点
   * @param {object} body   - 请求体 { message, thread_id, ... }
   * @param {object} [opts] - { onToken, onToolCall, onDone, onError }
   */
  async function send(url, body, opts = {}) {
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
        streaming.value = false
        try {
          const errBody = await response.json()
          error.value = errBody.message || `HTTP ${response.status}`
        } catch {
          error.value = `HTTP ${response.status}`
        }
        opts.onError?.(error.value)
        return
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        let currentEvent = ''
        for (const line of lines) {
          if (line.startsWith('event:')) {
            currentEvent = line.slice(6).trim()
          } else if (line.startsWith('data:')) {
            const raw = line.slice(5).trim()
            if (!raw) continue

            try {
              const data = JSON.parse(raw)
              const eventType = currentEvent || data.event || 'token'

              switch (eventType) {
                case 'token':
                  streamText.value += data.content || data.text || ''
                  opts.onToken?.(data.content || data.text || '')
                  break

                case 'tool_call':
                  opts.onToolCall?.(data)
                  break

                case 'done':
                  streamMeta.value = data
                  opts.onDone?.(data)
                  break

                case 'error':
                  error.value = data.message || '流式响应出错'
                  opts.onError?.(error.value)
                  break

                default:
                  // 未知事件类型当做 token 处理
                  if (data.content) {
                    streamText.value += data.content
                    opts.onToken?.(data.content)
                  }
              }
            } catch { /* ignore non-JSON lines */ }
            currentEvent = ''
          }
        }
      }
    } catch (err) {
      if (err.name === 'AbortError') return
      error.value = err.message || '连接失败'
      opts.onError?.(error.value)
    } finally {
      streaming.value = false
    }
  }

  /**
   * 使用 EventSource (GET) 监听流式聊天
   * 适合 OpsCopilot 等可用 GET 的场景
   */
  function listen(url, opts = {}) {
    stop()
    reset()
    streaming.value = true

    const token = localStorage.getItem('token') || ''
    const sep = url.includes('?') ? '&' : '?'
    const fullUrl = token ? `${url}${sep}token=${encodeURIComponent(token)}` : url

    const es = new EventSource(fullUrl)

    es.addEventListener('token', (e) => {
      try {
        const data = JSON.parse(e.data)
        streamText.value += data.content || ''
        opts.onToken?.(data.content || '')
      } catch {}
    })

    es.addEventListener('done', (e) => {
      try {
        streamMeta.value = JSON.parse(e.data)
        opts.onDone?.(streamMeta.value)
      } catch {}
      streaming.value = false
      es.close()
    })

    es.addEventListener('error', (e) => {
      if (!streaming.value) return
      error.value = '连接中断'
      opts.onError?.(error.value)
      streaming.value = false
      es.close()
    })

    // Store ref for cleanup
    abortCtrl = { abort: () => es.close() }
  }

  function stop() {
    abortCtrl?.abort()
    abortCtrl = null
    streaming.value = false
  }

  onUnmounted(() => stop())

  return {
    streaming:  readonly(streaming),
    streamText: readonly(streamText),
    streamMeta: readonly(streamMeta),
    error:      readonly(error),
    send,
    listen,
    stop,
    reset,
  }
}
