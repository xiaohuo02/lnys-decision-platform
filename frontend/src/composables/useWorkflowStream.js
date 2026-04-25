import { ref, readonly, onUnmounted } from 'vue'

/**
 * SSE 工作流进度流
 *
 * 事件类型 (与后端对齐):
 *   route_decided       — 路由已决定，携带 workflow + modules 列表（支持并行拓扑）
 *   step_started        — 步骤开始
 *   step_completed      — 步骤完成，携带 latency_ms / progress_pct
 *   parallel_started    — 并行阶段开始，携带 nodes 列表
 *   parallel_completed  — 并行阶段完成，携带 completed / failed / latency_ms
 *   final               — 全部完成，携带最终结果
 *   error               — 执行出错
 *
 * 使用:
 *   const { steps, progress, status, result, error, start, stop } = useWorkflowStream()
 *   start('/api/v1/analyze/stream/run_xxx')
 */

export function useWorkflowStream() {
  const steps    = ref([])          // { name, status, message, latency_ms, progress_pct }[]
  const progress = ref(0)           // 0-100
  const status   = ref('idle')      // 'idle' | 'connecting' | 'running' | 'completed' | 'failed'
  const result   = ref(null)        // final 事件 data
  const error    = ref(null)        // 错误信息

  let eventSource = null
  let abortCtrl   = null

  /* ── 重置状态 ───────────────────────────────────────── */
  function reset() {
    steps.value    = []
    progress.value = 0
    status.value   = 'idle'
    result.value   = null
    error.value    = null
  }

  /* ── 处理单条 SSE 事件 ─────────────────────────────── */
  function handleEvent(eventType, data) {
    switch (eventType) {
      case 'route_decided': {
        status.value = 'running'
        const modules = data.modules || []
        // 支持并行拓扑格式: ["a", {parallel: ["b","c","d"]}, "e"]
        const flatSteps = []
        modules.forEach(m => {
          if (typeof m === 'string') {
            flatSteps.push({ name: m, status: 'pending', message: '', latency_ms: null, progress_pct: null, parallel: false })
          } else if (m && m.parallel) {
            m.parallel.forEach(n => {
              flatSteps.push({ name: n, status: 'pending', message: '', latency_ms: null, progress_pct: null, parallel: true })
            })
          }
        })
        steps.value = flatSteps
        break
      }

      case 'step_started': {
        status.value = 'running'
        const idx = steps.value.findIndex(s => s.name === data.step_name)
        if (idx !== -1) {
          steps.value[idx].status  = 'running'
          steps.value[idx].message = data.message || ''
        } else {
          steps.value.push({
            name: data.step_name,
            status: 'running',
            message: data.message || '',
            latency_ms: null,
            progress_pct: null,
            confidence: null,
          })
        }
        break
      }

      case 'step_completed': {
        const idx = steps.value.findIndex(s => s.name === data.step_name)
        if (idx !== -1) {
          steps.value[idx].status       = 'completed'
          steps.value[idx].message      = data.message || steps.value[idx].message
          steps.value[idx].latency_ms   = data.latency_ms ?? null
          steps.value[idx].progress_pct = data.progress_pct ?? null
          steps.value[idx].confidence   = data.confidence ?? null
        }
        if (data.progress_pct != null) {
          progress.value = data.progress_pct
        }
        break
      }

      case 'step_failed': {
        const idx = steps.value.findIndex(s => s.name === data.step_name)
        if (idx !== -1) {
          steps.value[idx].status  = 'failed'
          steps.value[idx].message = data.message || '步骤执行失败'
        }
        break
      }

      case 'final': {
        status.value   = data.status === 'failed' ? 'failed' : 'completed'
        progress.value = 100
        result.value   = data
        break
      }

      case 'hitl_required': {
        const idx = steps.value.findIndex(s => s.name === data.step_name)
        if (idx !== -1) {
          steps.value[idx].status  = 'hitl_pending'
          steps.value[idx].message = data.message || '等待人工审核'
        } else {
          steps.value.push({
            name: data.step_name || 'hitl',
            status: 'hitl_pending',
            message: data.message || '等待人工审核',
            latency_ms: null,
            progress_pct: null,
          })
        }
        break
      }

      case 'hitl_resolved': {
        const idx = steps.value.findIndex(s => s.name === data.step_name)
        if (idx !== -1) {
          steps.value[idx].status  = 'completed'
          steps.value[idx].message = data.message || '人工审核完成'
        }
        break
      }

      case 'parallel_started': {
        status.value = 'running'
        const nodes = data.nodes || []
        // Mark all parallel nodes as running simultaneously
        nodes.forEach(n => {
          const idx = steps.value.findIndex(s => s.name === n)
          if (idx !== -1) {
            steps.value[idx].status = 'running'
            steps.value[idx].message = data.message || '并行执行中…'
          }
        })
        break
      }

      case 'parallel_completed': {
        const completed = data.completed || []
        const failed = data.failed || []
        completed.forEach(n => {
          const idx = steps.value.findIndex(s => s.name === n)
          if (idx !== -1) {
            steps.value[idx].status = 'completed'
            steps.value[idx].message = ''
          }
        })
        failed.forEach(n => {
          const idx = steps.value.findIndex(s => s.name === n)
          if (idx !== -1) {
            steps.value[idx].status = 'failed'
            steps.value[idx].message = '执行失败'
          }
        })
        if (data.progress_pct != null) progress.value = data.progress_pct
        if (data.latency_ms != null) {
          // Store parallel total latency on all parallel steps
          steps.value.forEach(s => {
            if (s.parallel && completed.includes(s.name)) {
              // Use per-node timing if available
              const nt = data.node_timings || {}
              s.latency_ms = nt[s.name] != null ? Math.round(nt[s.name] * 1000) : data.latency_ms
            }
          })
        }
        break
      }

      case 'error': {
        status.value = 'failed'
        error.value  = data.message || data.error || '未知错误'
        // Fix G.2: 同上，错误终态也要 close 防重连
        if (eventSource) {
          eventSource.close()
          eventSource = null
        }
        break
      }

      default:
        break
    }
  }

  /* ── 启动 EventSource (GET) ────────────────────────── */
  function start(url) {
    stop()
    reset()
    status.value = 'connecting'

    const token = localStorage.getItem('token') || ''
    const separator = url.includes('?') ? '&' : '?'
    const fullUrl = token ? `${url}${separator}token=${encodeURIComponent(token)}` : url

    eventSource = new EventSource(fullUrl)

    eventSource.onopen = () => {
      status.value = 'running'
    }

    eventSource.onerror = (e) => {
      if (status.value === 'completed') return
      status.value = 'failed'
      error.value  = '连接中断'
      eventSource?.close()
    }

    // 通用 message 事件 (后端用 data: JSON)
    eventSource.onmessage = (e) => {
      try {
        const payload = JSON.parse(e.data)
        handleEvent(payload.event || 'message', payload.data || payload)
      } catch { /* ignore non-JSON */ }
    }

    // 具名事件监听
    const eventTypes = ['route_decided', 'step_started', 'step_completed', 'step_failed', 'parallel_started', 'parallel_completed', 'hitl_required', 'hitl_resolved', 'final', 'error']
    eventTypes.forEach(type => {
      eventSource.addEventListener(type, (e) => {
        try {
          const data = JSON.parse(e.data)
          handleEvent(type, data)
        } catch { /* ignore */ }
      })
    })
  }

  /* ── 启动 Fetch-SSE (POST) ─────────────────────────── */
  async function startPost(url, body = {}) {
    stop()
    reset()
    status.value = 'connecting'

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
        status.value = 'failed'
        try {
          const errBody = await response.json()
          error.value = errBody.message || `HTTP ${response.status}`
        } catch {
          error.value = `HTTP ${response.status}`
        }
        return
      }

      status.value = 'running'
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
              handleEvent(currentEvent || data.event || 'message', data.data || data)
            } catch { /* ignore */ }
            currentEvent = ''
          }
        }
      }

      if (status.value === 'running') {
        status.value = 'completed'
        progress.value = 100
      }
    } catch (err) {
      if (err.name === 'AbortError') return
      status.value = 'failed'
      error.value  = err.message || '连接失败'
    }
  }

  /* ── 停止 ──────────────────────────────────────────── */
  function stop() {
    eventSource?.close()
    eventSource = null
    abortCtrl?.abort()
    abortCtrl = null
  }

  onUnmounted(() => stop())

  /**
   * 注入单条事件（Mock 回放用）
   * @param {string} eventType
   * @param {object} data
   */
  function injectEvent(eventType, data) {
    handleEvent(eventType, data)
  }

  return {
    steps:    readonly(steps),
    progress: readonly(progress),
    status:   readonly(status),
    result:   readonly(result),
    error:    readonly(error),
    start,
    startPost,
    stop,
    reset,
    injectEvent,
  }
}
