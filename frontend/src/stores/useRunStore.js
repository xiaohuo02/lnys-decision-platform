/**
 * useRunStore — 全局 AI 任务队列（C-β）
 *
 * 解决"AI 任务必须守在 AnalyzeProgress 页等"的痛点：
 *   - 触发 POST /api/v1/workflows/run 或 /analyze 后把 runId 注册到 Store
 *   - Store 独立开 SSE 订阅每个 run，记录进度 / 结果 / 错误
 *   - 全站 Header 右上角用 RunTicker 实时展示"N 个 AI 任务运行中"
 *   - 用户可切换到其他页面，完成后通过 RunTicker 回到结果
 *
 * 设计要点：
 *   - 每个 run 内部拥有自己的 useWorkflowStream 实例（生命周期随 Store 存活）
 *   - 使用 reactive Map 存储，触发 Map 变化需要 ref 的 trigger（Vue 3 提供内建支持）
 *   - 页面（如 AnalyzeProgress）仍保留自己的 stream 连接以获得完整 UI，Store 并行订阅不冲突
 *   - 保留运行历史（最近 20 条）方便用户查看已完成任务
 */
import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { useWorkflowStream } from '@/composables/useWorkflowStream'
import { workflowApi } from '@/api/workflow'

const MAX_HISTORY = 20

/**
 * @typedef {Object} RunEntry
 * @property {string} runId
 * @property {string} route        — business_overview / risk_review / openclaw / ...
 * @property {string} status       — pending | running | completed | failed | canceled
 * @property {number} progress     — 0-100
 * @property {string} query        — 用户原始查询文本
 * @property {string} origin       — analyze / kpi_delegate / focus_action
 * @property {number} startedAt    — ms timestamp
 * @property {number|null} completedAt
 * @property {any} result          — 最终 result（final 事件 data）
 * @property {string|null} error
 * @property {Array} steps         — 当前步骤数组（useWorkflowStream.steps）
 */

export const useRunStore = defineStore('run', () => {
  // 使用 ref + Map，Pinia setup store 下 reactive 依赖追踪正常
  const _runs = ref(new Map())
  // 记录每个 run 的 stream 实例（不放在 _runs 里避免序列化/序列比较干扰）
  const _streams = new Map()
  // 订阅 tick，用于触发 Map 变化
  const _tick = ref(0)

  function _touch() {
    _tick.value++
  }

  // ── Read ──
  const runs = computed(() => {
    // 依赖 _tick 触发更新
    _tick.value // eslint-disable-line no-unused-expressions
    return Array.from(_runs.value.values()).sort((a, b) => b.startedAt - a.startedAt)
  })

  const activeRuns = computed(() =>
    runs.value.filter((r) => r.status === 'pending' || r.status === 'running'),
  )
  const completedRuns = computed(() =>
    runs.value.filter((r) => r.status === 'completed' || r.status === 'failed' || r.status === 'canceled'),
  )
  const activeCount = computed(() => activeRuns.value.length)

  function getRun(runId) {
    _tick.value // trigger dep
    return _runs.value.get(runId) || null
  }

  // ── Track a new run ──

  /**
   * 开始跟踪一个 run。若 runId 已存在则复用（幂等）。
   * @param {Object} opts { runId, streamUrl, route, query, origin }
   * @returns {RunEntry}
   */
  function track({ runId, streamUrl, route = '', query = '', origin = 'inline' }) {
    if (!runId) return null
    const existing = _runs.value.get(runId)
    if (existing) return existing

    /** @type {RunEntry} */
    const entry = {
      runId,
      route,
      status: 'pending',
      progress: 0,
      query,
      origin,
      startedAt: Date.now(),
      completedAt: null,
      result: null,
      error: null,
      steps: [],
    }
    _runs.value.set(runId, entry)
    _touch()

    // 开启独立 SSE 订阅
    const stream = useWorkflowStream()
    _streams.set(runId, stream)

    // Watch stream state → 同步到 entry
    watch(
      () => stream.status.value,
      (s) => {
        if (!_runs.value.has(runId)) return
        const e = _runs.value.get(runId)
        // Fix G.3: terminal 状态不可逆（即使上游 stream 被重连误触发也不会回滚 UI）
        if (e.status === 'completed' || e.status === 'failed' || e.status === 'canceled') {
          return
        }
        if (s === 'connecting' || s === 'running') e.status = 'running'
        else if (s === 'completed') {
          e.status = 'completed'
          e.completedAt = Date.now()
          e.progress = 100
        } else if (s === 'failed') {
          e.status = 'failed'
          e.completedAt = Date.now()
        }
        _touch()
        _enforceHistoryLimit()
      },
    )

    watch(
      () => stream.progress.value,
      (p) => {
        if (!_runs.value.has(runId)) return
        _runs.value.get(runId).progress = p
        _touch()
      },
    )

    watch(
      () => stream.steps.value,
      (s) => {
        if (!_runs.value.has(runId)) return
        _runs.value.get(runId).steps = s
        _touch()
      },
      { deep: true },
    )

    watch(
      () => stream.result.value,
      (r) => {
        if (!r || !_runs.value.has(runId)) return
        _runs.value.get(runId).result = r
        _touch()
      },
    )

    watch(
      () => stream.error.value,
      (err) => {
        if (!err || !_runs.value.has(runId)) return
        _runs.value.get(runId).error = err
        _touch()
      },
    )

    // 启动 SSE 订阅
    const url = streamUrl || `/api/v1/workflows/${runId}/stream`
    stream.start(url)

    return entry
  }

  // ── Cancel ──

  async function cancel(runId) {
    const entry = _runs.value.get(runId)
    if (!entry) return
    try {
      await workflowApi.cancel(runId)
    } catch (e) {
      console.warn('[runStore] cancel api failed:', e)
    }
    const stream = _streams.get(runId)
    if (stream) stream.stop()
    entry.status = 'canceled'
    entry.completedAt = Date.now()
    _touch()
  }

  // ── Remove (user dismisses a finished run) ──

  function remove(runId) {
    const stream = _streams.get(runId)
    if (stream) {
      stream.stop()
      _streams.delete(runId)
    }
    _runs.value.delete(runId)
    _touch()
  }

  function clearCompleted() {
    for (const entry of Array.from(_runs.value.values())) {
      if (entry.status === 'completed' || entry.status === 'failed' || entry.status === 'canceled') {
        remove(entry.runId)
      }
    }
  }

  function _enforceHistoryLimit() {
    const completed = completedRuns.value
    if (completed.length <= MAX_HISTORY) return
    // 已排序 startedAt 降序，保留最新 MAX_HISTORY 条
    const toDelete = completed.slice(MAX_HISTORY)
    for (const r of toDelete) remove(r.runId)
  }

  return {
    // State
    runs,
    activeRuns,
    completedRuns,
    activeCount,
    // Ops
    track,
    cancel,
    remove,
    clearCompleted,
    getRun,
  }
})
