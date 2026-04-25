<template>
  <div class="caf">
    <div class="caf__hd">
      <div class="caf__hd-left">
        <h2 class="caf__title">活动流</h2>
        <span class="caf__live-dot" />
        <span class="caf__live-text">实时</span>
      </div>
      <div class="caf__hd-right">
        <div class="caf__search">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
          <input class="caf__search-input" v-model="searchQuery" placeholder="搜索事件… ( / )" />
        </div>
        <div class="caf__tabs">
          <button
            v-for="t in filterTabs" :key="t.key"
            class="caf__tab" :class="{ 'caf__tab--active': activeFilter === t.key }"
            @click="setFilter(t.key)"
          >
            {{ t.label }}
            <span v-if="t.count > 0" class="caf__tab-count">{{ t.count }}</span>
          </button>
        </div>
        <button class="caf__refresh" :class="{ 'caf__refresh--spin': loading }" @click="load" title="刷新 (r)">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 12a9 9 0 1 1-2.636-6.364" /><path d="M21 3v6h-6" />
          </svg>
        </button>
      </div>
    </div>

    <!-- Event Stream -->
    <div class="caf__stream" ref="streamEl">
      <template v-if="loading && !events.length">
        <div v-for="i in 6" :key="i" class="caf__skel">
          <div class="caf__skel-dot" />
          <div class="caf__skel-body">
            <div class="caf__skel-line" :style="{ width: 40 + Math.random() * 40 + '%' }" />
            <div class="caf__skel-line caf__skel-line--short" />
          </div>
        </div>
      </template>

      <template v-else-if="filteredEvents.length">
        <template v-for="(group, gi) in groupedEvents" :key="gi">
          <div class="caf__group-label">{{ group.label }}</div>
          <div
            v-for="evt in group.items" :key="evt.id"
            class="caf__evt"
            :class="{ 'caf__evt--unread': !evt._read, 'caf__evt--error': evt._severity === 'error' }"
            @click="viewDetail(evt)"
          >
            <div class="caf__evt-indicator">
              <span class="caf__evt-dot" :class="'caf__evt-dot--' + evt._severity" />
              <span class="caf__evt-line" v-if="!evt._last" />
            </div>
            <div class="caf__evt-body">
              <div class="caf__evt-row1">
                <span class="caf__evt-action">{{ evt._actionLabel }}</span>
                <span class="caf__evt-crud" :class="'caf__evt-crud--' + evt._crudType">{{ evt._crudLabel }}</span>
                <span class="caf__evt-time">{{ evt._timeLabel }}</span>
              </div>
              <div class="caf__evt-row2">
                <span v-if="evt._actorLabel" class="caf__evt-actor">{{ evt._actorLabel }}</span>
                <span v-if="evt._targetLabel" class="caf__evt-target">{{ evt._targetLabel }}</span>
              </div>
              <div v-if="evt._humanDesc" class="caf__evt-desc">{{ evt._humanDesc }}</div>
              <div v-if="evt._advice" class="caf__evt-advice">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>
                <span>{{ evt._advice }}</span>
              </div>
            </div>
          </div>
        </template>

        <!-- Load more -->
        <div v-if="hasMore" class="caf__more">
          <button class="caf__more-btn" @click="loadMore" :disabled="loadingMore">
            {{ loadingMore ? '加载中...' : '加载更多' }}
          </button>
        </div>
      </template>

      <div v-else class="caf__empty">
        <svg width="48" height="48" viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1.5">
          <rect x="6" y="10" width="36" height="28" rx="4" />
          <path d="M6 18h36M16 10v8" />
          <circle cx="24" cy="30" r="3" />
        </svg>
        <span class="caf__empty-title">暂无活动</span>
        <span class="caf__empty-desc">当前筛选条件下无事件记录</span>
      </div>
    </div>

    <!-- Detail Drawer -->
    <Teleport to="body">
      <Transition name="caf-drawer">
        <div v-if="detailEvt" class="caf__overlay" @click.self="detailEvt = null">
          <div class="caf__drawer">
            <div class="caf__drawer-hd">
              <span class="caf__drawer-title">事件详情</span>
              <button class="caf__drawer-close" @click="detailEvt = null">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>
              </button>
            </div>
            <div class="caf__drawer-body">
              <div class="caf__detail-row"><span class="caf__detail-k">操作</span><span class="caf__detail-v">{{ detailEvt._actionLabel }}</span></div>
              <div class="caf__detail-row"><span class="caf__detail-k">类型</span><span class="caf__evt-crud" :class="'caf__evt-crud--' + detailEvt._crudType">{{ detailEvt._crudLabel }}</span></div>
              <div class="caf__detail-row"><span class="caf__detail-k">操作人</span><span class="caf__detail-v">{{ detailEvt._actorLabel || '-' }}</span></div>
              <div class="caf__detail-row"><span class="caf__detail-k">目标</span><span class="caf__detail-v">{{ detailEvt._targetLabel || '-' }}</span></div>
              <div class="caf__detail-row"><span class="caf__detail-k">时间</span><span class="caf__detail-v caf__mono">{{ detailEvt._fullTime }}</span></div>
              <div class="caf__detail-row"><span class="caf__detail-k">IP</span><span class="caf__detail-v caf__mono">{{ detailEvt.ip || '-' }}</span></div>
              <div v-if="detailEvt._humanDesc" class="caf__detail-row caf__detail-row--col">
                <span class="caf__detail-k">发生了什么</span>
                <span class="caf__detail-v">{{ detailEvt._humanDesc }}</span>
              </div>
              <div v-if="detailEvt._advice" class="caf__detail-row caf__detail-row--col">
                <span class="caf__detail-k">建议操作</span>
                <span class="caf__detail-v caf__detail-advice">{{ detailEvt._advice }}</span>
              </div>
              <div v-if="detailEvt.diff || detailEvt.payload" class="caf__detail-row caf__detail-row--col">
                <span class="caf__detail-k">变更数据</span>
                <pre class="caf__detail-json">{{ formatJson(detailEvt.diff || detailEvt.payload) }}</pre>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { auditApi } from '@/api/admin/audit'
import { tracesApi } from '@/api/admin/traces'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const loadingMore = ref(false)
const events = ref([])
const cursor = ref(null)
const hasMore = ref(false)
const detailEvt = ref(null)
const streamEl = ref(null)
const activeFilter = ref(route.query.filter || 'all')

// Auto-refresh timer
let refreshTimer = null
const REFRESH_INTERVAL = 30000

// ── Filter tabs ──
const filterTabs = computed(() => {
  const counts = { all: events.value.length, action: 0, alert: 0, system: 0, change: 0 }
  for (const e of events.value) {
    const cat = categorizeEvent(e)
    if (counts[cat] !== undefined) counts[cat]++
  }
  return [
    { key: 'all',    label: '全部',   count: 0 },
    { key: 'action', label: '待办',   count: counts.action },
    { key: 'alert',  label: '告警',   count: counts.alert },
    { key: 'system', label: '系统',   count: counts.system },
    { key: 'change', label: '变更',   count: counts.change },
  ]
})

function categorizeEvent(e) {
  const a = (e.action || '').toLowerCase()
  if (a.includes('fail') || a.includes('error') || a.includes('alert')) return 'alert'
  if (a.includes('review') || a.includes('pending') || a.includes('approve')) return 'action'
  if (a.includes('create') || a.includes('update') || a.includes('delete') || a.includes('release') || a.includes('rollback')) return 'change'
  return 'system'
}

// ── Event enrichment ──
const ACTION_LABELS = {
  // dot-notation (from audit system)
  'user.login': '用户登录', 'user.logout': '用户登出', 'user.created': '创建了用户', 'user.updated': '更新了用户信息',
  'prompt.created': '新建了提示词', 'prompt.updated': '修改了提示词', 'prompt.released': '发布了提示词',
  'policy.created': '新建了安全策略', 'policy.activated': '启用了安全策略', 'policy.updated': '修改了安全策略',
  'release.created': '创建了发布版本', 'release.activated': '激活了发布版本', 'release.rolled_back': '回滚了发布版本',
  'faq.created': '新建了FAQ知识', 'faq.disabled': '禁用了FAQ',
  'memory.disabled': '禁用了记忆条目', 'memory.expired': '记忆条目已过期',
  'role.assigned': '分配了用户角色', 'role.changed': '变更了用户角色',
  'trace.failed': '任务运行失败', 'trace.completed': '任务运行完成',
  // underscore-notation (from backend raw events)
  'create_review': '新建了人工审核', 'create_release': '创建了新版本',
  'activate_policy': '启用了安全策略', 'create_policy': '新建了安全策略',
  'release_prompt': '发布了提示词', 'create_prompt': '新建了提示词',
  'update_prompt': '修改了提示词', 'delete_prompt': '删除了提示词',
  'create_faq': '新建了FAQ知识', 'update_faq': '更新了FAQ知识', 'disable_faq': '禁用了FAQ',
  'create_agent': '创建了智能体', 'update_agent': '更新了智能体', 'delete_agent': '删除了智能体',
  'create_workflow': '创建了工作流', 'update_workflow': '更新了工作流',
  'approve_review': '通过了人工审核', 'reject_review': '驳回了人工审核',
  'login': '用户登录', 'logout': '用户登出',
  'update_role': '变更了用户角色', 'assign_role': '分配了用户角色',
  'update_settings': '更新了系统设置', 'rollback_release': '回滚了发布版本',
}

/** CRUD type → human-readable label */
const CRUD_LABELS = { C: '新建', R: '查看', U: '变更', D: '删除' }

function getCrudType(action) {
  const a = (action || '').toLowerCase()
  if (a.includes('create') || a.includes('register')) return 'C'
  if (a.includes('read') || a.includes('view') || a.includes('login') || a.includes('query')) return 'R'
  if (a.includes('update') || a.includes('edit') || a.includes('activate') || a.includes('release') || a.includes('assign') || a.includes('approve')) return 'U'
  if (a.includes('delete') || a.includes('disable') || a.includes('rollback') || a.includes('expire') || a.includes('reject')) return 'D'
  return 'R'
}

function getSeverity(event) {
  const a = (event.action || '').toLowerCase()
  if (a.includes('fail') || a.includes('error') || a.includes('reject') || a.includes('rollback')) return 'error'
  if (a.includes('alert') || a.includes('warning') || a.includes('review') || a.includes('pending')) return 'warning'
  if (a.includes('create') || a.includes('success') || a.includes('complete') || a.includes('approve')) return 'success'
  return 'neutral'
}

/** Generate human-readable description */
function getHumanDesc(raw) {
  const a = (raw.action || '').toLowerCase()
  const actor = raw.actor || '系统'
  const target = raw.target || ''
  if (a.includes('fail') || a.includes('error')) {
    const err = raw.description || '未知原因'
    return `「${target || '任务'}」执行时出错：${err}`
  }
  if (a.includes('login')) return `${actor} 登录了系统`
  if (a.includes('create_review') || a.includes('review')) return `${actor} 提交了一条需要人工审核的内容`
  if (a.includes('release') && a.includes('prompt')) return `${actor} 将提示词「${target}」发布到生产环境`
  if (a.includes('create') && a.includes('release')) return `${actor} 创建了一个新的发布版本`
  if (a.includes('activate') && a.includes('policy')) return `${actor} 启用了安全策略「${target}」`
  if (a.includes('rollback')) return `${actor} 将版本「${target}」回滚到上一版`
  if (raw.description) return raw.description
  return ''
}

/** Generate actionable advice for errors/warnings */
function getAdvice(raw) {
  const a = (raw.action || '').toLowerCase()
  const desc = (raw.description || '').toLowerCase()
  if (a.includes('fail') || a.includes('error')) {
    if (desc.includes('timeout')) return '建议：检查对应服务是否正常运行，可尝试在「系统健康」页查看服务状态，或联系开发排查超时原因'
    if (desc.includes('connect') || desc.includes('connection')) return '建议：检查网络连接或对应服务是否启动，查看「系统健康」页面确认服务在线'
    if (desc.includes('permission') || desc.includes('auth')) return '建议：检查当前操作人的权限设置，或在「安全合规」页面查看权限配置'
    return '建议：请在「智能体日志」中查看该任务详细日志，或联系开发团队排查'
  }
  if (a.includes('rollback')) return '注意：版本已回滚，请确认回滚后功能是否正常'
  if (a.includes('review') || a.includes('pending')) return '需要处理：请前往「智能体中枢」的审核队列查看并处理'
  return ''
}

/** Format actor for display */
function formatActor(raw) {
  if (!raw.actor) return ''
  if (raw.actor === 'system' || raw.actor === 'scheduler') return '系统自动'
  return `操作人：${raw.actor}`
}

/** Format target for display */
function formatTarget(raw) {
  if (!raw.target) return ''
  // Don't show raw run IDs
  if (raw.target.startsWith('run_')) return ''
  return raw.target
}

function enrichEvent(raw) {
  const ts = raw.timestamp || raw.created_at || raw.started_at
  const d = ts ? new Date(ts) : new Date()
  const crudType = getCrudType(raw.action)
  return {
    ...raw,
    _actionLabel: ACTION_LABELS[raw.action] || raw.action || '未知操作',
    _crudType: crudType,
    _crudLabel: CRUD_LABELS[crudType] || '查看',
    _severity: getSeverity(raw),
    _timeLabel: formatRelativeTime(d),
    _fullTime: formatFullTime(d),
    _ts: d.getTime(),
    _read: false,
    _last: false,
    _humanDesc: getHumanDesc(raw),
    _advice: getAdvice(raw),
    _actorLabel: formatActor(raw),
    _targetLabel: formatTarget(raw),
  }
}

// ── Time formatting ──
function formatRelativeTime(d) {
  const now = Date.now()
  const diff = now - d.getTime()
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return Math.floor(diff / 60000) + ' 分钟前'
  if (diff < 86400000) return Math.floor(diff / 3600000) + ' 小时前'
  if (diff < 172800000) return '昨天'
  if (diff < 604800000) return Math.floor(diff / 86400000) + ' 天前'
  return formatFullTime(d)
}

function formatFullTime(d) {
  if (isNaN(d)) return '-'
  const Y = d.getFullYear(), M = String(d.getMonth() + 1).padStart(2, '0')
  const D = String(d.getDate()).padStart(2, '0')
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  const ss = String(d.getSeconds()).padStart(2, '0')
  return `${Y}-${M}-${D} ${hh}:${mm}:${ss}`
}

function getTimeGroupLabel(ts) {
  const now = Date.now()
  const diff = now - ts
  if (diff < 3600000) return '最近 1 小时'
  if (diff < 86400000) return '今天早些'
  if (diff < 172800000) return '昨天'
  if (diff < 604800000) return '本周'
  return '更早'
}

// ── Filtered + Grouped ──
const filteredEvents = computed(() => {
  if (activeFilter.value === 'all') return events.value
  return events.value.filter(e => categorizeEvent(e) === activeFilter.value)
})

const groupedEvents = computed(() => {
  const groups = []
  let currentLabel = null
  let currentItems = []
  for (const evt of filteredEvents.value) {
    const label = getTimeGroupLabel(evt._ts)
    if (label !== currentLabel) {
      if (currentItems.length) {
        currentItems[currentItems.length - 1]._last = true
        groups.push({ label: currentLabel, items: currentItems })
      }
      currentLabel = label
      currentItems = []
    }
    evt._last = false
    currentItems.push(evt)
  }
  if (currentItems.length) {
    currentItems[currentItems.length - 1]._last = true
    groups.push({ label: currentLabel, items: currentItems })
  }
  return groups
})

// ── Data fetching ──
async function load() {
  loading.value = true
  try {
    const [auditRes, tracesRes] = await Promise.allSettled([
      auditApi.getLogs({ limit: 50, offset: 0 }),
      tracesApi.getList({ limit: 20, offset: 0 }),
    ])

    const allEvents = []

    // Audit events
    const auditItems = auditRes.status === 'fulfilled' ? (auditRes.value?.items || auditRes.value || []) : []
    if (Array.isArray(auditItems)) {
      for (const item of auditItems) {
        allEvents.push(enrichEvent({ ...item, id: item.id || item.audit_id || crypto.randomUUID() }))
      }
    }

    // Trace events (failed ones as alerts)
    const traceItems = tracesRes.status === 'fulfilled' ? (tracesRes.value?.items || []) : []
    for (const t of traceItems) {
      if (t.status === 'failed') {
        allEvents.push(enrichEvent({
          id: 'trace-' + t.run_id,
          action: 'trace.failed',
          actor: t.workflow_name || 'system',
          target: t.run_id?.slice(0, 16),
          description: t.error_message?.slice(0, 120),
          timestamp: t.started_at,
        }))
      }
    }

    allEvents.sort((a, b) => b._ts - a._ts)
    events.value = allEvents
    hasMore.value = auditItems.length >= 50
  } catch (e) {
    console.warn('[ActivityFeed]', e)
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  loadingMore.value = true
  try {
    const offset = events.value.filter(e => !e.id?.startsWith('trace-')).length
    const res = await auditApi.getLogs({ limit: 50, offset })
    const items = res?.items || res || []
    if (Array.isArray(items) && items.length) {
      const newEvents = items.map(item => enrichEvent({ ...item, id: item.id || item.audit_id || crypto.randomUUID() }))
      events.value.push(...newEvents)
      events.value.sort((a, b) => b._ts - a._ts)
      hasMore.value = items.length >= 50
    } else {
      hasMore.value = false
    }
  } catch (e) {
    console.warn('[ActivityFeed] loadMore', e)
  } finally {
    loadingMore.value = false
  }
}

const searchQuery = ref('')

function setFilter(key) {
  activeFilter.value = key
  router.replace({ query: { ...route.query, filter: key === 'all' ? undefined : key } })
}

function viewDetail(evt) {
  evt._read = true
  detailEvt.value = evt
}

function formatJson(data) {
  if (!data) return ''
  try {
    if (typeof data === 'string') data = JSON.parse(data)
    return JSON.stringify(data, null, 2)
  } catch { return String(data) }
}

// ── Keyboard navigation ──
const focusIdx = ref(-1)
const flatFilteredEvents = computed(() => {
  let items = filteredEvents.value
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.toLowerCase()
    items = items.filter(e =>
      (e._actionLabel || '').toLowerCase().includes(q) ||
      (e.actor || '').toLowerCase().includes(q) ||
      (e.target || '').toLowerCase().includes(q) ||
      (e.description || '').toLowerCase().includes(q)
    )
  }
  return items
})

function onKeydown(e) {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
    if (e.key === 'Escape') { e.target.blur(); return }
    return
  }
  const items = flatFilteredEvents.value
  if (e.key === 'j' || e.key === 'ArrowDown') {
    e.preventDefault()
    focusIdx.value = Math.min(focusIdx.value + 1, items.length - 1)
  } else if (e.key === 'k' || e.key === 'ArrowUp') {
    e.preventDefault()
    focusIdx.value = Math.max(focusIdx.value - 1, 0)
  } else if (e.key === 'Enter' && focusIdx.value >= 0 && focusIdx.value < items.length) {
    e.preventDefault()
    viewDetail(items[focusIdx.value])
  } else if (e.key === 'Escape') {
    if (detailEvt.value) { detailEvt.value = null; return }
    focusIdx.value = -1
  } else if (e.key === 'r') {
    e.preventDefault()
    load()
  } else if (e.key === '/') {
    e.preventDefault()
    document.querySelector('.caf__search-input')?.focus()
  }
}

// Auto-refresh
function startAutoRefresh() {
  stopAutoRefresh()
  refreshTimer = setInterval(load, REFRESH_INTERVAL)
}
function stopAutoRefresh() {
  if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null }
}

onMounted(() => {
  load()
  startAutoRefresh()
  document.addEventListener('keydown', onKeydown)
})
onUnmounted(() => {
  stopAutoRefresh()
  document.removeEventListener('keydown', onKeydown)
})
</script>

<style scoped>
.caf__hd {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--v2-space-4);
}
.caf__hd-left {
  display: flex;
  align-items: center;
  gap: var(--v2-space-2);
}
.caf__title {
  font-size: var(--v2-text-lg);
  font-weight: var(--v2-font-semibold);
  color: var(--v2-text-1);
  margin: 0;
}
.caf__live-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--v2-success);
  animation: caf-pulse 2s ease-in-out infinite;
}
.caf__live-text {
  font-size: var(--v2-text-xs);
  color: var(--v2-success-text);
  font-weight: var(--v2-font-medium);
}
@keyframes caf-pulse { 0%,100%{opacity:1} 50%{opacity:.3} }

.caf__hd-right { display: flex; align-items: center; gap: var(--v2-space-3); }

/* Search */
.caf__search {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 10px;
  height: 28px;
  background: var(--v2-bg-card);
  border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-btn);
  color: var(--v2-text-4);
  transition: border-color var(--v2-trans-fast);
}
.caf__search:focus-within { border-color: var(--v2-text-3); }
.caf__search-input {
  border: none;
  outline: none;
  background: transparent;
  color: var(--v2-text-1);
  font-size: var(--v2-text-xs);
  font-family: var(--v2-font-sans);
  width: 140px;
}
.caf__search-input::placeholder { color: var(--v2-text-4); }

/* Tabs */
.caf__tabs {
  display: flex;
  gap: 2px;
  background: var(--v2-bg-sunken);
  border-radius: var(--v2-radius-btn);
  padding: 2px;
}
.caf__tab {
  padding: 4px 12px;
  font-size: var(--v2-text-xs);
  font-weight: var(--v2-font-medium);
  color: var(--v2-text-3);
  background: transparent;
  border: none;
  border-radius: calc(var(--v2-radius-btn) - 2px);
  cursor: pointer;
  transition: var(--v2-trans-fast);
  white-space: nowrap;
  display: flex;
  align-items: center;
  gap: 4px;
}
.caf__tab:hover { color: var(--v2-text-1); }
.caf__tab--active {
  color: var(--v2-text-1);
  background: var(--v2-bg-card);
  font-weight: var(--v2-font-semibold);
}
.caf__tab-count {
  font-size: 9px;
  padding: 0 4px;
  background: var(--v2-error-bg);
  color: var(--v2-error-text);
  border-radius: var(--v2-radius-full);
  line-height: 1.4;
}

/* Refresh */
.caf__refresh {
  width: 28px; height: 28px;
  display: flex; align-items: center; justify-content: center;
  background: transparent;
  border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-btn);
  color: var(--v2-text-3);
  cursor: pointer;
  transition: var(--v2-trans-fast);
}
.caf__refresh:hover { color: var(--v2-text-1); border-color: var(--v2-border-3); }
.caf__refresh--spin svg { animation: caf-spin .8s linear infinite; }
@keyframes caf-spin { from{transform:rotate(0)} to{transform:rotate(360deg)} }

/* Stream */
.caf__stream {
  background: var(--v2-bg-card);
  border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-card);
  padding: var(--v2-space-4);
  min-height: calc(100vh - 200px);
  overflow-y: auto;
}

/* Group label */
.caf__group-label {
  font-size: 10px;
  font-weight: var(--v2-font-semibold);
  color: var(--v2-text-4);
  text-transform: uppercase;
  letter-spacing: .5px;
  padding: var(--v2-space-3) 0 var(--v2-space-2);
  border-bottom: var(--v2-border-width) solid var(--v2-border-2);
  margin-bottom: var(--v2-space-2);
}
.caf__group-label:first-child { padding-top: 0; }

/* Event item */
.caf__evt {
  display: flex;
  gap: var(--v2-space-3);
  padding: var(--v2-space-2) var(--v2-space-2);
  border-radius: var(--v2-radius-md);
  cursor: pointer;
  transition: background var(--v2-trans-fast);
}
.caf__evt:hover { background: var(--v2-bg-hover); }
.caf__evt--unread { background: rgba(0,0,0,0.02); }
.caf__evt--error { background: var(--v2-error-bg); border-radius: var(--v2-radius-md); }
.caf__evt--error:hover { background: var(--v2-error-bg); filter: brightness(0.97); }

/* Indicator (dot + connecting line) */
.caf__evt-indicator {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 12px;
  flex-shrink: 0;
  padding-top: 6px;
}
.caf__evt-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: var(--v2-gray-400);
  flex-shrink: 0;
}
.caf__evt-dot--error { background: var(--v2-error); }
.caf__evt-dot--warning { background: var(--v2-warning); }
.caf__evt-dot--success { background: var(--v2-success); }
.caf__evt-dot--neutral { background: var(--v2-gray-400); }
.caf__evt-line {
  width: var(--v2-border-width);
  flex: 1;
  background: var(--v2-border-2);
  margin-top: 4px;
  min-height: 12px;
}

/* Event body */
.caf__evt-body { flex: 1; min-width: 0; }
.caf__evt-row1 {
  display: flex;
  align-items: center;
  gap: var(--v2-space-2);
}
.caf__evt-action {
  font-size: var(--v2-text-sm);
  font-weight: var(--v2-font-medium);
  color: var(--v2-text-1);
}
.caf__evt-crud {
  font-size: 9px;
  font-weight: var(--v2-font-bold);
  font-family: var(--v2-font-mono);
  padding: 0 4px;
  border-radius: 2px;
  line-height: 1.5;
}
.caf__evt-crud--C { background: var(--v2-success-bg); color: var(--v2-success-text); }
.caf__evt-crud--R { background: var(--v2-bg-sunken); color: var(--v2-text-4); }
.caf__evt-crud--U { background: var(--v2-warning-bg); color: var(--v2-warning-text); }
.caf__evt-crud--D { background: var(--v2-error-bg); color: var(--v2-error-text); }
.caf__evt-time {
  margin-left: auto;
  font-size: var(--v2-text-xs);
  color: var(--v2-text-4);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.caf__evt-row2 {
  display: flex;
  gap: var(--v2-space-2);
  margin-top: 2px;
}
.caf__evt-actor {
  font-size: var(--v2-text-xs);
  color: var(--v2-text-3);
}
.caf__evt-target {
  font-size: var(--v2-text-xs);
  font-family: var(--v2-font-mono);
  color: var(--v2-text-4);
}
.caf__evt-desc {
  font-size: var(--v2-text-xs);
  color: var(--v2-text-3);
  margin-top: 2px;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.caf__evt-advice {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-top: 6px;
  padding: 6px 10px;
  font-size: var(--v2-text-xs);
  line-height: 1.5;
  color: var(--v2-warning-text);
  background: var(--v2-warning-bg);
  border-radius: var(--v2-radius-sm);
  border-left: 2px solid var(--v2-warning);
}
.caf__evt-advice svg {
  flex-shrink: 0;
  margin-top: 1px;
  color: var(--v2-warning);
}
.caf__evt--error .caf__evt-advice {
  color: var(--v2-error-text);
  background: var(--v2-error-bg);
  border-left-color: var(--v2-error);
}
.caf__evt--error .caf__evt-advice svg { color: var(--v2-error); }
.caf__detail-advice {
  padding: 8px 12px;
  background: var(--v2-warning-bg);
  border-radius: var(--v2-radius-sm);
  border-left: 2px solid var(--v2-warning);
  line-height: 1.5;
}

/* Load more */
.caf__more { text-align: center; padding: var(--v2-space-4) 0; }
.caf__more-btn {
  padding: 6px 24px;
  font-size: var(--v2-text-xs);
  font-weight: var(--v2-font-medium);
  color: var(--v2-text-3);
  background: var(--v2-bg-sunken);
  border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-btn);
  cursor: pointer;
  transition: var(--v2-trans-fast);
}
.caf__more-btn:hover { color: var(--v2-text-1); border-color: var(--v2-border-3); }
.caf__more-btn:disabled { opacity: .5; cursor: default; }

/* Empty */
.caf__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--v2-space-12) 0;
  color: var(--v2-gray-300);
  gap: var(--v2-space-2);
}
.caf__empty-title { font-size: var(--v2-text-md); color: var(--v2-text-2); font-weight: var(--v2-font-medium); }
.caf__empty-desc { font-size: var(--v2-text-sm); color: var(--v2-text-3); }

/* Skeleton */
.caf__skel {
  display: flex;
  gap: var(--v2-space-3);
  padding: var(--v2-space-3) var(--v2-space-2);
}
.caf__skel-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: var(--v2-bg-sunken);
  flex-shrink: 0;
  margin-top: 4px;
  animation: caf-shimmer 1.5s infinite;
}
.caf__skel-body { flex: 1; display: flex; flex-direction: column; gap: 6px; }
.caf__skel-line {
  height: 10px;
  border-radius: 3px;
  background: var(--v2-bg-sunken);
  animation: caf-shimmer 1.5s infinite;
}
.caf__skel-line--short { width: 30%; height: 8px; }
@keyframes caf-shimmer { 0%,100%{opacity:1} 50%{opacity:.4} }

/* ── Detail Drawer ── */
.caf__overlay {
  position: fixed;
  inset: 0;
  z-index: var(--v2-z-drawer);
  background: var(--v2-bg-overlay);
  display: flex;
  justify-content: flex-end;
}
.caf__drawer {
  width: 420px;
  max-width: 90vw;
  height: 100%;
  background: var(--v2-bg-elevated);
  border-left: var(--v2-border-width) solid var(--v2-border-1);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.caf__drawer-hd {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--v2-space-4) var(--v2-space-5);
  border-bottom: var(--v2-border-width) solid var(--v2-border-2);
  flex-shrink: 0;
}
.caf__drawer-title {
  font-size: var(--v2-text-md);
  font-weight: var(--v2-font-semibold);
  color: var(--v2-text-1);
}
.caf__drawer-close {
  width: 28px; height: 28px;
  display: flex; align-items: center; justify-content: center;
  background: transparent;
  border: none;
  color: var(--v2-text-3);
  cursor: pointer;
  border-radius: var(--v2-radius-sm);
  transition: var(--v2-trans-fast);
}
.caf__drawer-close:hover { color: var(--v2-text-1); background: var(--v2-bg-hover); }
.caf__drawer-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--v2-space-4) var(--v2-space-5);
  display: flex;
  flex-direction: column;
  gap: var(--v2-space-3);
}
.caf__detail-row {
  display: flex;
  align-items: center;
  gap: var(--v2-space-3);
}
.caf__detail-row--col {
  flex-direction: column;
  align-items: flex-start;
  gap: var(--v2-space-1);
}
.caf__detail-k {
  font-size: var(--v2-text-xs);
  color: var(--v2-text-4);
  min-width: 48px;
  flex-shrink: 0;
}
.caf__detail-v {
  font-size: var(--v2-text-sm);
  color: var(--v2-text-1);
}
.caf__detail-json {
  font-family: var(--v2-font-mono);
  font-size: 11px;
  color: var(--v2-text-2);
  background: var(--v2-bg-sunken);
  border-radius: var(--v2-radius-md);
  padding: var(--v2-space-3);
  margin: 0;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 400px;
  overflow-y: auto;
}
.caf__mono {
  font-family: var(--v2-font-mono);
  font-size: var(--v2-text-xs);
}

/* Drawer transition */
.caf-drawer-enter-active { transition: opacity .25s ease, transform .3s cubic-bezier(0.16,1,0.3,1); }
.caf-drawer-leave-active { transition: opacity .2s ease, transform .2s ease; }
.caf-drawer-enter-from { opacity: 0; }
.caf-drawer-enter-from .caf__drawer { transform: translateX(100%); }
.caf-drawer-leave-to { opacity: 0; }
.caf-drawer-leave-to .caf__drawer { transform: translateX(100%); }

@media (max-width: 1200px) {
  .caf__hd { flex-direction: column; align-items: flex-start; gap: var(--v2-space-2); }
}
</style>
