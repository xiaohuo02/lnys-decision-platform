<template>
  <div class="ticker">
    <!-- Trigger button -->
    <button
      class="ticker__trigger"
      :class="{ 'ticker__trigger--active': activeCount > 0, 'ticker__trigger--recently-done': recentlyDone }"
      @click="open = !open"
      :title="`${activeCount} 个 AI 任务运行中`"
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75">
        <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
      </svg>
      <span v-if="activeCount > 0" class="ticker__badge">{{ activeCount }}</span>
      <span v-else-if="recentlyDone" class="ticker__badge ticker__badge--done">✓</span>
    </button>

    <!-- Dropdown -->
    <Teleport to="body">
      <Transition name="ticker-fade">
        <div v-if="open" class="ticker-mask" @click="open = false" />
      </Transition>
      <Transition name="ticker-slide">
        <div v-if="open" class="ticker-panel" @click.stop>
          <div class="ticker-panel__hd">
            <span class="ticker-panel__title">AI 任务</span>
            <div class="ticker-panel__hd-actions">
              <button
                class="ticker-panel__new"
                title="跳转到经营分析页发起新任务"
                @click="handleNewTask"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
                </svg>
                新建任务
              </button>
              <button
                v-if="completedRuns.length > 0"
                class="ticker-panel__clear"
                @click="handleClearCompleted"
              >清除已完成</button>
            </div>
          </div>

          <div class="ticker-panel__body">
            <!-- Active section -->
            <div v-if="activeRuns.length > 0" class="ticker-panel__section">
              <div class="ticker-panel__section-title">运行中 ({{ activeRuns.length }})</div>
              <div
                v-for="r in activeRuns"
                :key="r.runId"
                class="run-item run-item--active"
                @click="jumpToAnalyze(r)"
              >
                <div class="run-item__row">
                  <span class="run-item__route">{{ routeLabel(r.route) }}</span>
                  <span class="run-item__status">运行中</span>
                </div>
                <div class="run-item__query" :title="r.query">{{ truncate(r.query, 60) || '(无查询文本)' }}</div>
                <div class="run-item__progress">
                  <div class="run-item__progress-bar" :style="{ width: (r.progress || 0) + '%' }"></div>
                </div>
                <div class="run-item__meta">
                  <span>{{ formatRelative(r.startedAt) }}</span>
                  <span>{{ r.progress || 0 }}%</span>
                  <button class="run-item__cancel" @click.stop="handleCancel(r)">终止</button>
                </div>
              </div>
            </div>

            <!-- Completed section -->
            <div v-if="completedRuns.length > 0" class="ticker-panel__section">
              <div class="ticker-panel__section-title">已完成 ({{ completedRuns.length }})</div>
              <div
                v-for="r in completedRuns.slice(0, 10)"
                :key="r.runId"
                class="run-item"
                :class="`run-item--${r.status}`"
                @click="jumpToAnalyze(r)"
              >
                <div class="run-item__row">
                  <span class="run-item__route">{{ routeLabel(r.route) }}</span>
                  <span class="run-item__status">{{ statusLabel(r.status) }}</span>
                </div>
                <div class="run-item__query" :title="r.query">{{ truncate(r.query, 60) || '(无查询文本)' }}</div>
                <div class="run-item__meta">
                  <span>{{ formatRelative(r.startedAt) }}</span>
                  <span v-if="r.completedAt">{{ formatDuration(r.completedAt - r.startedAt) }}</span>
                  <button class="run-item__cancel" @click.stop="handleRemove(r)">移除</button>
                </div>
              </div>
            </div>

            <!-- Empty state -->
            <div v-if="runs.length === 0" class="ticker-panel__empty">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <circle cx="12" cy="12" r="10" />
                <path d="M12 6v6l4 2" />
              </svg>
              <p>暂无 AI 任务</p>
              <span>在经营分析页触发任务后会出现在这里</span>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useRunStore } from '@/stores/useRunStore'

const router = useRouter()
const runStore = useRunStore()

const open = ref(false)
const recentlyDone = ref(false)
let doneTimer = null

const runs = computed(() => runStore.runs)
const activeRuns = computed(() => runStore.activeRuns)
const completedRuns = computed(() => runStore.completedRuns)
const activeCount = computed(() => runStore.activeCount)

// 完成状态提示：2s 徽章
watch(
  () => runStore.completedRuns.length,
  (newLen, oldLen) => {
    if (newLen > oldLen) {
      recentlyDone.value = true
      clearTimeout(doneTimer)
      doneTimer = setTimeout(() => { recentlyDone.value = false }, 3000)
    }
  },
)

function routeLabel(route) {
  const map = {
    business_overview: '经营综述',
    risk_review: '风险审查',
    openclaw: '智能客服',
    ops_copilot: '运维诊断',
  }
  return map[route] || route || 'workflow'
}

function statusLabel(status) {
  return { completed: '已完成', failed: '失败', canceled: '已取消' }[status] || status
}

function truncate(s, n) {
  if (!s) return ''
  return s.length > n ? s.slice(0, n) + '…' : s
}

function formatRelative(ts) {
  const diff = Date.now() - ts
  if (diff < 60_000) return `${Math.floor(diff / 1000)}s 前`
  if (diff < 3600_000) return `${Math.floor(diff / 60_000)}m 前`
  if (diff < 86400_000) return `${Math.floor(diff / 3600_000)}h 前`
  return new Date(ts).toLocaleDateString()
}

function formatDuration(ms) {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60_000)}m${Math.floor((ms % 60_000) / 1000)}s`
}

function jumpToAnalyze(r) {
  open.value = false
  router.push({ path: '/analyze', query: { run_id: r.runId } })
}

/**
 * Fix C: 新建任务 — 跳转到 /analyze 且清除 run_id，让页面回到 form 阶段
 * 当前若已在 /analyze?run_id=xxx，watch 的 query.run_id 变成 undefined，
 * AnalyzeProgress 可据此 reset form。
 */
function handleNewTask() {
  open.value = false
  router.push({ path: '/analyze', query: {} })
}

function handleCancel(r) {
  runStore.cancel(r.runId)
}

function handleRemove(r) {
  runStore.remove(r.runId)
}

function handleClearCompleted() {
  runStore.clearCompleted()
}

function onKey(e) {
  if (e.key === 'Escape' && open.value) open.value = false
}

onMounted(() => { window.addEventListener('keydown', onKey) })
onUnmounted(() => {
  window.removeEventListener('keydown', onKey)
  if (doneTimer) clearTimeout(doneTimer)
})
</script>

<style scoped>
.ticker { position: relative; }

/* ── Trigger ── */
.ticker__trigger {
  display: flex; align-items: center; justify-content: center;
  width: 32px; height: 32px;
  border: none; background: transparent;
  color: var(--v2-text-3);
  cursor: pointer; border-radius: var(--v2-radius-btn);
  position: relative;
  transition: color var(--v2-trans-fast);
}
.ticker__trigger:hover { color: var(--v2-text-1); }
.ticker__trigger--active {
  color: var(--v2-success, #22c55e);
  animation: ticker-pulse 2s ease-in-out infinite;
}
.ticker__trigger--recently-done { color: var(--v2-success, #22c55e); }

.ticker__badge {
  position: absolute;
  top: 2px; right: 2px;
  min-width: 16px; height: 16px;
  padding: 0 4px;
  border-radius: var(--v2-radius-pill);
  background: var(--v2-success, #22c55e);
  color: #fff;
  font-size: 10px; font-weight: 600; font-family: var(--v2-font-mono);
  display: flex; align-items: center; justify-content: center;
  border: 2px solid var(--v2-bg-page);
}
.ticker__badge--done { background: var(--v2-text-1); }

@keyframes ticker-pulse {
  0%, 100% { opacity: 1; }
  50%      { opacity: 0.55; }
}
@media (prefers-reduced-motion: reduce) {
  .ticker__trigger--active { animation: none; }
}

/* ── Mask ── */
.ticker-mask {
  position: fixed; inset: 0; z-index: 1100;
}

/* ── Panel ── */
.ticker-panel {
  position: fixed;
  top: calc(var(--v2-header-height, 56px) + 6px);
  right: var(--v2-space-6, 24px);
  width: 360px; max-height: 70vh;
  border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-card);
  background: var(--v2-bg-card);
  box-shadow: 0 16px 32px -8px rgba(0, 0, 0, 0.12), 0 4px 8px -2px rgba(0, 0, 0, 0.06);
  z-index: 1101;
  display: flex; flex-direction: column;
  overflow: hidden;
}

.ticker-panel__hd {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 14px;
  border-bottom: var(--v2-border-width) solid var(--v2-border-2);
  flex-shrink: 0;
}
.ticker-panel__title {
  font-size: 13px; font-weight: var(--v2-font-semibold); color: var(--v2-text-1);
}
.ticker-panel__hd-actions { display: flex; align-items: center; gap: 4px; }
.ticker-panel__new {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 3px 8px; font-family: inherit; font-size: 11px; font-weight: var(--v2-font-medium);
  color: var(--v2-text-1); background: var(--v2-bg-card);
  border: 1px solid var(--v2-border-1); border-radius: var(--v2-radius-btn);
  cursor: pointer; transition: all var(--v2-trans-fast);
}
.ticker-panel__new:hover { background: var(--v2-text-1); color: var(--v2-bg-card); border-color: var(--v2-text-1); }
.ticker-panel__clear {
  border: none; background: transparent;
  color: var(--v2-text-3); font-size: 11px; cursor: pointer;
  font-family: inherit; padding: 2px 6px;
  border-radius: var(--v2-radius-btn);
}
.ticker-panel__clear:hover { color: var(--v2-text-1); background: var(--v2-bg-hover); }

.ticker-panel__body { overflow-y: auto; flex: 1; }

.ticker-panel__section {
  padding: 8px 0;
  border-bottom: var(--v2-border-width) solid var(--v2-border-2);
}
.ticker-panel__section:last-child { border-bottom: none; }
.ticker-panel__section-title {
  font-family: var(--v2-font-mono); font-size: 10px; letter-spacing: 0.05em;
  color: var(--v2-text-4); text-transform: uppercase;
  padding: 4px 14px;
}

/* ── Run Item ── */
.run-item {
  display: flex; flex-direction: column; gap: 4px;
  padding: 10px 14px;
  cursor: pointer;
  border-left: 2px solid transparent;
  transition: background var(--v2-trans-fast);
}
.run-item:hover { background: var(--v2-bg-hover); }
.run-item--active { border-left-color: var(--v2-success, #22c55e); }
.run-item--completed { border-left-color: var(--v2-brand-primary, #18181b); }
.run-item--failed { border-left-color: var(--v2-error, #dc2626); }
.run-item--canceled { border-left-color: var(--v2-text-4); opacity: 0.6; }

.run-item__row {
  display: flex; justify-content: space-between; align-items: center;
}
.run-item__route {
  font-size: 12px; font-weight: var(--v2-font-medium); color: var(--v2-text-1);
}
.run-item__status {
  font-family: var(--v2-font-mono); font-size: 10px;
  padding: 1px 6px; border-radius: 3px;
  color: var(--v2-text-3); background: var(--v2-bg-sunken);
}
.run-item--active .run-item__status { color: var(--v2-success, #22c55e); background: color-mix(in srgb, var(--v2-success, #22c55e) 12%, transparent); }
.run-item--failed .run-item__status { color: var(--v2-error, #dc2626); background: color-mix(in srgb, var(--v2-error, #dc2626) 12%, transparent); }

.run-item__query {
  font-size: 11px; color: var(--v2-text-3); line-height: 1.4;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden;
}

.run-item__progress {
  height: 3px; background: var(--v2-border-2);
  border-radius: 2px; overflow: hidden;
}
.run-item__progress-bar {
  height: 100%; background: var(--v2-success, #22c55e);
  transition: width 0.3s ease;
}

.run-item__meta {
  display: flex; gap: 10px; align-items: center;
  font-size: 10px; color: var(--v2-text-4); font-family: var(--v2-font-mono);
}
.run-item__meta > span:last-of-type { margin-right: auto; }
.run-item__cancel {
  border: none; background: transparent;
  color: var(--v2-text-4); font-size: 10px;
  cursor: pointer; padding: 2px 4px;
  font-family: inherit;
  border-radius: var(--v2-radius-btn);
}
.run-item__cancel:hover { color: var(--v2-error, #dc2626); background: color-mix(in srgb, var(--v2-error, #dc2626) 8%, transparent); }

/* ── Empty ── */
.ticker-panel__empty {
  padding: 40px 20px;
  display: flex; flex-direction: column; align-items: center; gap: 8px;
  color: var(--v2-text-4); text-align: center;
}
.ticker-panel__empty p { font-size: 13px; color: var(--v2-text-3); margin: 4px 0 0; }
.ticker-panel__empty span { font-size: 11px; color: var(--v2-text-4); }

/* ── Transitions ── */
.ticker-fade-enter-active, .ticker-fade-leave-active { transition: opacity 0.15s; }
.ticker-fade-enter-from, .ticker-fade-leave-to { opacity: 0; }

.ticker-slide-enter-active, .ticker-slide-leave-active { transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1); }
.ticker-slide-enter-from, .ticker-slide-leave-to {
  opacity: 0; transform: translateY(-8px);
}
</style>
