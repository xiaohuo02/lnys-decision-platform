<template>
  <div class="al">
    <!-- ── Header ── -->
    <div class="al__hd">
      <div class="al__hd-left">
        <h2 class="al__title">智能体日志</h2>
      </div>
      <div class="al__hd-right">
        <!-- 搜索框 -->
        <div class="al__search">
          <svg class="al__search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
          <input class="al__search-input" v-model="keyword" placeholder="搜索关键词 / run_id / 工作流名" @input="onKeywordInput" />
          <button v-if="keyword" class="al__search-clear" @click="keyword = ''; onKeywordInput()">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>
          </button>
        </div>
        <!-- 导出 -->
        <div class="al__export-wrap" v-click-outside="() => showExport = false">
          <button class="al__btn al__btn--ghost" @click="showExport = !showExport">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            <span>导出</span>
          </button>
          <div v-if="showExport" class="al__export-menu">
            <button @click="doExport('csv')">导出 CSV</button>
            <button @click="doExport('json')">导出 JSON</button>
          </div>
        </div>
        <!-- 刷新 -->
        <button class="al__refresh" :class="{ 'al__refresh--spin': loading }" @click="loadTraces" title="刷新 (R)">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.636-6.364"/><path d="M21 3v6h-6"/></svg>
        </button>
      </div>
    </div>

    <!-- ── Stats Cards ── -->
    <div class="al__stats">
      <div class="al__stat">
        <div class="al__stat-val">{{ stats.total ?? '-' }}</div>
        <div class="al__stat-label">总运行</div>
      </div>
      <div class="al__stat al__stat--ok">
        <div class="al__stat-val">{{ stats.completed ?? '-' }}</div>
        <div class="al__stat-label">成功</div>
      </div>
      <div class="al__stat al__stat--err">
        <div class="al__stat-val">{{ stats.failed ?? '-' }}</div>
        <div class="al__stat-label">失败</div>
      </div>
      <div class="al__stat">
        <div class="al__stat-val">{{ stats.avg_latency != null ? (stats.avg_latency / 1000).toFixed(1) + 's' : '-' }}</div>
        <div class="al__stat-label">平均耗时</div>
      </div>
    </div>

    <!-- ── Filters ── -->
    <div class="al__filters">
      <V2Select v-model="filter.triggered_by" :options="userOpts" placeholder="发起人" clearable size="sm" @change="onFilterChange" style="min-width:120px" />
      <V2Select v-model="filter.workflow_name" :options="workflowOpts" placeholder="功能模块" clearable size="sm" @change="onFilterChange" style="min-width:120px" />
      <V2Select v-model="filter.status" :options="STATUS_OPTS" placeholder="状态" clearable size="sm" @change="onFilterChange" style="min-width:100px" />
      <input type="date" class="al__date" v-model="filter.start_date" @change="onFilterChange" title="起始日期" />
      <input type="date" class="al__date" v-model="filter.end_date" @change="onFilterChange" title="截止日期" />
      <label class="al__toggle">
        <input type="checkbox" v-model="filter.hideSystem" @change="onFilterChange" />
        <span class="al__toggle-track"><span class="al__toggle-thumb" /></span>
        <span class="al__toggle-label">隐藏系统任务</span>
      </label>
      <span class="al__count">共 {{ total }} 条记录</span>
    </div>

    <!-- ── Table ── -->
    <div class="al__table-wrap">
      <div v-if="loading && !traces.length" class="al__loading"><span class="al__spinner" /></div>
      <table v-else-if="traces.length" class="al__table">
        <thead>
          <tr>
            <th class="al__th al__th--time al__th--sort" @click="toggleSort('started_at')">
              时间 <span class="al__sort-arrow" v-if="sortBy === 'started_at'">{{ sortDir === 'desc' ? '↓' : '↑' }}</span>
            </th>
            <th class="al__th al__th--user">发起人</th>
            <th class="al__th al__th--wf">功能</th>
            <th class="al__th al__th--input">做了什么</th>
            <th class="al__th al__th--output">结果摘要</th>
            <th class="al__th al__th--st">状态</th>
            <th class="al__th al__th--dur al__th--sort" @click="toggleSort('latency_ms')">
              耗时 <span class="al__sort-arrow" v-if="sortBy === 'latency_ms'">{{ sortDir === 'desc' ? '↓' : '↑' }}</span>
            </th>
            <th class="al__th al__th--cost al__th--sort" @click="toggleSort('total_tokens')">
              AI 消耗 <span class="al__sort-arrow" v-if="sortBy === 'total_tokens'">{{ sortDir === 'desc' ? '↓' : '↑' }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in traces" :key="row.run_id"
            class="al__row"
            :class="{ 'al__row--err': row.status === 'failed', 'al__row--warn': row.status === 'paused' }"
            @click="openDetail(row)"
          >
            <td class="al__td al__td--time" :title="fmtFull(row.started_at)">{{ fmtRelative(row.started_at) }}</td>
            <td class="al__td al__td--user">
              <span v-if="row.triggered_by && row.triggered_by !== 'scheduler'" class="al__user-badge">👤 {{ userDisplayName(row.triggered_by) }}</span>
              <span v-else class="al__user-sys">{{ row.triggered_by === 'scheduler' ? '⏱ 定时任务' : '🤖 系统自动' }}</span>
            </td>
            <td class="al__td"><span class="al__wf-tag" :class="'al__wf--' + getWfColor(row.workflow_name)">{{ wfLabel(row.workflow_name) }}</span></td>
            <td class="al__td al__td--input" :title="row.input_summary">{{ row.input_summary || '-' }}</td>
            <td class="al__td al__td--output" :title="row.output_summary">{{ row.output_summary || (row.error_message ? '⚠ ' + row.error_message : '-') }}</td>
            <td class="al__td"><span class="al__st" :class="'al__st--' + row.status">{{ statusLabel(row.status) }}</span></td>
            <td class="al__td al__td--r al__mono">{{ fmtDuration(row.latency_ms) }}</td>
            <td class="al__td al__td--r al__td--cost-cell">
              <span class="al__cost-text">{{ fmtCost(row) }}</span>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="al__empty">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" stroke-linecap="round"><rect x="3" y="3" width="18" height="18" rx="3"/><path d="M9 9h6M9 13h4"/></svg>
        <span>暂无智能体使用记录</span>
      </div>
    </div>

    <!-- ── Pager ── -->
    <div class="al__footer">
      <V2Pager v-model="page" :total="total" :page-size="pageSize" @change="loadTraces" />
    </div>

    <!-- ── Detail Drawer ── -->
    <Teleport to="body">
      <Transition name="al-drawer">
        <div v-if="detail" class="al__overlay" @click.self="detail = null">
          <div class="al__drawer">
            <!-- drawer header -->
            <div class="al__drawer-hd">
              <div class="al__drawer-title-wrap">
                <span class="al__wf-tag" :class="'al__wf--' + getWfColor(detail.workflow_name)">{{ wfLabel(detail.workflow_name) }}</span>
                <span class="al__st" :class="'al__st--' + detail.status">{{ statusLabel(detail.status) }}</span>
              </div>
              <button class="al__drawer-close" @click="detail = null">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>
              </button>
            </div>

            <!-- drawer body -->
            <div class="al__drawer-body">
              <!-- 基本信息 -->
              <div class="al__section">
                <h4 class="al__section-title">基本信息</h4>
                <div class="al__kv">
                  <span class="al__k">执行编号</span>
                  <span class="al__v al__mono al__copyable" @click="copyText(detail.run_id)" title="点击复制">{{ detail.run_id }}</span>
                </div>
                <div class="al__kv"><span class="al__k">发起人</span><span class="al__v">{{ userDisplayName(detail.triggered_by) }}</span></div>
                <div class="al__kv"><span class="al__k">开始时间</span><span class="al__v al__mono">{{ fmtFull(detail.started_at) }}</span></div>
                <div class="al__kv"><span class="al__k">结束时间</span><span class="al__v al__mono">{{ fmtFull(detail.ended_at) }}</span></div>
                <div class="al__kv"><span class="al__k">耗时</span><span class="al__v">{{ fmtDuration(detail.latency_ms) }}</span></div>
                <div class="al__kv"><span class="al__k">AI 消耗</span><span class="al__v">{{ fmtCostDetail(detail) }}</span></div>
                <div class="al__kv" v-if="detail.thread_id">
                  <span class="al__k">会话线程</span>
                  <span class="al__v al__mono" style="font-size:11px">{{ detail.thread_id }}</span>
                </div>
              </div>

              <!-- 用户请求 -->
              <div class="al__section" v-if="detail.input_summary">
                <h4 class="al__section-title">用户请求 / 输入</h4>
                <div class="al__bubble al__bubble--user">{{ detail.input_summary }}</div>
              </div>

              <!-- AI 执行过程 -->
              <div class="al__section" v-if="detailSteps.length">
                <h4 class="al__section-title">执行过程 <span class="al__step-count">{{ detailSteps.length }} 步</span></h4>
                <div class="al__steps">
                  <div v-for="(s, i) in detailSteps" :key="s.step_id" class="al__step" :class="{ 'al__step--err': s.status === 'failed' }">
                    <div class="al__step-line">
                      <div class="al__step-dot" :class="'al__step-dot--' + s.status" />
                      <div class="al__step-connector" v-if="i < detailSteps.length - 1" />
                    </div>
                    <div class="al__step-body">
                      <div class="al__step-header" @click="toggleStep(s.step_id)">
                        <div class="al__step-name">{{ stepLabel(s) }}</div>
                        <div class="al__step-meta">
                          <span v-if="s.model_name" class="al__step-model">{{ s.model_name }}</span>
                          <span class="al__st al__st--sm" :class="'al__st--' + s.status">{{ statusLabel(s.status) }}</span>
                          <svg class="al__step-chevron" :class="{ 'al__step-chevron--open': expandedSteps.has(s.step_id) }" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>
                        </div>
                      </div>
                      <Transition name="al-expand">
                        <div v-if="expandedSteps.has(s.step_id)" class="al__step-detail">
                          <div v-if="s.input_summary" class="al__step-block">
                            <div class="al__step-block-label">输入</div>
                            <pre class="al__step-pre">{{ s.input_summary }}</pre>
                          </div>
                          <div v-if="s.output_summary" class="al__step-block">
                            <div class="al__step-block-label">输出</div>
                            <pre class="al__step-pre">{{ s.output_summary }}</pre>
                          </div>
                          <div v-if="s.error_message" class="al__step-block al__step-block--err">
                            <div class="al__step-block-label">错误</div>
                            <pre class="al__step-pre">{{ s.error_message }}</pre>
                          </div>
                          <div class="al__step-kv-row" v-if="s.tool_name || s.agent_name || s.cost_amount || s.latency_ms || (s.token_usage && s.token_usage.total_tokens)">
                            <span v-if="s.agent_name" class="al__step-tag">智能体：{{ s.agent_name }}</span>
                            <span v-if="s.tool_name" class="al__step-tag">工具：{{ s.tool_name }}</span>
                            <span v-if="s.latency_ms" class="al__step-tag">耗时：{{ fmtDuration(s.latency_ms) }}</span>
                            <span v-if="s.token_usage && s.token_usage.total_tokens" class="al__step-tag">{{ fmtTokens(s.token_usage.total_tokens) }} 词元</span>
                            <span v-if="s.cost_amount" class="al__step-tag">¥{{ Number(s.cost_amount).toFixed(4) }}</span>
                            <span v-if="s.retry_count" class="al__step-tag">重试 {{ s.retry_count }}次</span>
                          </div>
                        </div>
                      </Transition>
                    </div>
                  </div>
                </div>
              </div>

              <!-- 瀑布图 -->
              <div class="al__section" v-if="waterfallBars.length">
                <h4 class="al__section-title">执行瀑布图</h4>
                <div class="al__waterfall">
                  <div v-for="bar in waterfallBars" :key="bar.step_id" class="al__wf-row">
                    <div class="al__wf-label" :title="bar.label">{{ bar.label }}</div>
                    <div class="al__wf-track">
                      <div
                        class="al__wf-bar"
                        :class="'al__wf-bar--' + bar.status"
                        :style="{ left: (bar.offsetMs / waterfallTotalMs * 100) + '%', width: Math.max(0.5, bar.durMs / waterfallTotalMs * 100) + '%' }"
                        :title="bar.label + ' ' + fmtDuration(bar.durMs)"
                      >
                        <span class="al__wf-bar-label">{{ fmtDuration(bar.durMs) }}</span>
                      </div>
                    </div>
                  </div>
                  <div class="al__wf-axis">
                    <span>0</span>
                    <span>{{ fmtDuration(Math.round(waterfallTotalMs / 2)) }}</span>
                    <span>{{ fmtDuration(waterfallTotalMs) }}</span>
                  </div>
                </div>
              </div>

              <!-- 最终结果 -->
              <div class="al__section" v-if="detail.output_summary">
                <h4 class="al__section-title">最终结果 / 输出</h4>
                <div class="al__bubble al__bubble--ai">{{ detail.output_summary }}</div>
              </div>

              <!-- 失败建议 -->
              <div class="al__section" v-if="detail.status === 'failed'">
                <h4 class="al__section-title" style="color:var(--v2-error)">问题与建议</h4>
                <div class="al__advice-card">
                  <div class="al__advice-err">{{ detail.error_message || '未知错误' }}</div>
                  <div class="al__advice-text">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>
                    <span>{{ getAdvice(detail) }}</span>
                  </div>
                </div>
              </div>

              <!-- 等待审核建议 -->
              <div class="al__section" v-if="detail.status === 'paused'">
                <h4 class="al__section-title" style="color:var(--v2-warning)">等待处理</h4>
                <div class="al__advice-card al__advice-card--warn">
                  <div class="al__advice-text">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>
                    <span>此任务需要人工审核确认后才能继续执行，请前往「智能体中枢」的审核队列处理</span>
                  </div>
                </div>
              </div>

              <!-- 跳转到完整瀑布图 -->
              <div class="al__section" v-if="detail.run_id && detailSteps.length">
                <button class="al__waterfall-btn" @click="goToWaterfall(detail.run_id)">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="4"/><rect x="3" y="14" width="7" height="4"/><rect x="14" y="11" width="7" height="7"/></svg>
                  <span>查看完整执行瀑布图</span>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                </button>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { tracesApi } from '@/api/admin/traces'
import { fmtRelative, fmtFull as _fmtFull } from '@/utils/time'
import V2Select from '@/components/v2/V2Select.vue'
import V2Pager from '@/components/v2/V2Pager.vue'

const route = useRoute()
const router = useRouter()

// ── click-outside directive (inline) ──
const vClickOutside = {
  mounted(el, binding) {
    el._clickOutside = (e) => { if (!el.contains(e.target)) binding.value() }
    document.addEventListener('click', el._clickOutside)
  },
  unmounted(el) { document.removeEventListener('click', el._clickOutside) },
}

// ── Workflow name → Chinese mapping ──
const WORKFLOW_MAP = {
  business_overview: '经营分析',
  risk_review: '风控审查',
  openclaw_session: '智能客服',
  openclaw: '智能客服',
  copilot_ops: '运维助手',
  copilot_biz: '运营助手',
  patrol_ops: '运维巡检',
  patrol_biz: '运营巡检',
  patrol_memory: '记忆调和',
  sentiment_analysis: '舆情分析',
  customer_analysis: '客户洞察',
  inventory_optimization: '库存优化',
  fraud_detection: '欺诈检测',
  association_analysis: '关联分析',
  sales_forecast: '销售预测',
}
const WF_COLORS = {
  business_overview: 'blue', risk_review: 'red', openclaw_session: 'green', openclaw: 'green',
  copilot_ops: 'purple', copilot_biz: 'purple',
  patrol_ops: 'gray', patrol_biz: 'gray', patrol_memory: 'gray',
  sentiment_analysis: 'orange', customer_analysis: 'teal', inventory_optimization: 'cyan',
  fraud_detection: 'red', association_analysis: 'indigo', sales_forecast: 'blue',
}
function wfLabel(name) { return WORKFLOW_MAP[name] || name || '未知功能' }
function getWfColor(name) { return WF_COLORS[name] || 'gray' }

// ── Step type label ──
const STEP_LABELS = {
  service_call: '服务调用', agent_call: '智能体推理', tool_call: '工具调用',
  llm_call: '大模型调用', hitl: '人工审核', handoff: '转交', guardrail: '安全检查',
}
function stepLabel(s) {
  const typeName = STEP_LABELS[s.step_type] || s.step_type
  return `${typeName}：${s.step_name || s.agent_name || '-'}`
}

const STATUS_OPTS = [
  { label: '✅ 成功', value: 'completed' },
  { label: '❌ 失败', value: 'failed' },
  { label: '⏸ 等待审核', value: 'paused' },
  { label: '⏳ 进行中', value: 'running' },
]

function statusLabel(s) {
  const m = { completed: '成功', failed: '失败', paused: '等待审核', running: '进行中', pending: '排队中', cancelled: '已取消', ok: '正常', anomaly: '异常' }
  return m[s] || s || '-'
}

// ── State ──
const loading = ref(false)
const traces = ref([])
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const userList = ref([])
const wfList = ref([])
const keyword = ref('')
const sortBy = ref('started_at')
const sortDir = ref('desc')
const showExport = ref(false)
const filter = reactive({ workflow_name: '', status: '', triggered_by: '', hideSystem: false, start_date: '', end_date: '' })
const detail = ref(null)
const detailSteps = ref([])
const detailLoading = ref(false)
const expandedSteps = reactive(new Set())
const stats = reactive({ total: null, completed: null, failed: null, active: null, avg_latency: null })

const userOpts = computed(() => {
  const opts = [{ label: '🤖 系统/定时任务', value: '__system__' }]
  for (const u of userList.value) {
    const uname = typeof u === 'object' ? u.username : u
    const dname = typeof u === 'object' ? u.display_name : u
    if (uname === 'scheduler') continue
    opts.push({ label: `👤 ${dname}`, value: uname })
  }
  return opts
})

const workflowOpts = computed(() => {
  const seen = new Set()
  const opts = []
  for (const wf of wfList.value) {
    if (!wf || seen.has(wf)) continue
    seen.add(wf)
    opts.push({ label: WORKFLOW_MAP[wf] || wf, value: wf })
  }
  return opts
})

// ── Time formatting (imported from @/utils/time, UTC-safe) ──
const fmtFull = _fmtFull
function fmtDuration(ms) {
  if (ms == null) return '-'
  if (ms < 1000) return ms + 'ms'
  return (ms / 1000).toFixed(1) + '秒'
}
function fmtTokens(n) {
  if (n == null || n === 0) return ''
  if (n >= 10000) return (n / 10000).toFixed(1) + '万'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}
function fmtCost(row) {
  const t = row.total_tokens, c = row.total_cost
  if ((!t || t === 0) && (!c || c === 0)) return '无 AI 调用'
  const tokenStr = fmtTokens(t)
  const costStr = c != null && c > 0 ? `¥${Number(c).toFixed(2)}` : ''
  return [tokenStr, costStr].filter(Boolean).join(' · ') || '-'
}
function fmtCostDetail(row) {
  const t = row.total_tokens, c = row.total_cost
  if ((!t || t === 0) && (!c || c === 0)) return '本次执行未使用 AI 模型'
  const tokenStr = fmtTokens(t) ? fmtTokens(t) + ' 词元' : ''
  const costStr = c != null && c > 0 ? `¥${Number(c).toFixed(4)}` : ''
  return [tokenStr, costStr].filter(Boolean).join(' · ') || '-'
}

// ── Error advice ──
function getAdvice(row) {
  const err = (row.error_message || '').toLowerCase()
  if (err.includes('timeout')) return '建议：对应服务可能响应超时，请在「系统健康」页查看服务状态，或联系开发排查'
  if (err.includes('connect')) return '建议：网络连接异常，请检查服务是否正常运行'
  if (err.includes('permission') || err.includes('auth')) return '建议：权限不足，请在「安全合规」页检查相关配置'
  if (err.includes('hitl') || err.includes('人工')) return '建议：此任务需要人工审核，请前往审核队列处理'
  return '建议：请联系开发团队查看详细日志排查问题'
}

// ── Clipboard ──
function copyText(text) {
  navigator.clipboard?.writeText(text)
}

// ── Build query params ──
function buildParams(extra = {}) {
  const p = { ...extra }
  if (filter.workflow_name) p.workflow_name = filter.workflow_name
  if (filter.status) p.status = filter.status
  if (filter.triggered_by) p.triggered_by = filter.triggered_by
  if (filter.hideSystem) p.hide_system = true
  if (filter.start_date) p.start_date = filter.start_date
  if (filter.end_date) p.end_date = filter.end_date
  if (keyword.value) p.keyword = keyword.value
  if (sortBy.value !== 'started_at') p.sort_by = sortBy.value
  if (sortDir.value !== 'desc') p.sort_dir = sortDir.value
  return p
}

// ── Data loading ──
async function loadTraces() {
  loading.value = true
  try {
    const p = buildParams({ limit: pageSize.value, offset: (page.value - 1) * pageSize.value })
    const data = await tracesApi.getList(p)
    traces.value = data?.items ?? []
    total.value = data?.total ?? traces.value.length
    if (data?.users) userList.value = data.users
    if (data?.workflows) wfList.value = data.workflows
  } catch (e) {
    console.warn('[AgentLog]', e)
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  try {
    const p = {}
    if (filter.start_date) p.start_date = filter.start_date
    if (filter.end_date) p.end_date = filter.end_date
    const data = await tracesApi.getStats(p)
    if (data?.overview) Object.assign(stats, data.overview)
  } catch (e) {
    console.warn('[AgentLog] stats', e)
  }
}

function onFilterChange() {
  page.value = 1
  loadTraces()
  loadStats()
}

let _keywordTimer = null
function onKeywordInput() {
  clearTimeout(_keywordTimer)
  _keywordTimer = setTimeout(() => { page.value = 1; loadTraces() }, 350)
}

function toggleSort(col) {
  if (sortBy.value === col) {
    sortDir.value = sortDir.value === 'desc' ? 'asc' : 'desc'
  } else {
    sortBy.value = col
    sortDir.value = 'desc'
  }
  loadTraces()
}

// ── Export ──
async function doExport(fmt) {
  showExport.value = false
  try {
    const p = buildParams({ fmt })
    const resp = await tracesApi.exportDownload(p)
    const blob = new Blob([resp], { type: fmt === 'json' ? 'application/json' : 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `traces_export.${fmt}`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch (e) {
    console.warn('[AgentLog] export', e)
  }
}

// ── Detail ──
async function openDetail(row) {
  detail.value = row
  detailSteps.value = []
  expandedSteps.clear()
  detailLoading.value = true
  try {
    const data = await tracesApi.getDetail(row.run_id)
    if (data?.steps) detailSteps.value = data.steps
    if (data?.run) detail.value = { ...row, ...data.run }
    buildWaterfall()
  } catch (e) {
    console.warn('[AgentLog] detail', e)
  } finally {
    detailLoading.value = false
  }
}

function toggleStep(stepId) {
  if (expandedSteps.has(stepId)) expandedSteps.delete(stepId)
  else expandedSteps.add(stepId)
}

// ── Waterfall data ──
const waterfallBars = ref([])
const waterfallTotalMs = ref(0)
function buildWaterfall() {
  if (!detailSteps.value.length || !detail.value) { waterfallBars.value = []; return }
  const runStart = detail.value.started_at ? new Date(detail.value.started_at).getTime() : null
  if (!runStart) { waterfallBars.value = []; return }
  let maxEnd = 0
  const bars = detailSteps.value.map(s => {
    const sa = s.started_at ? new Date(s.started_at).getTime() : runStart
    const ea = s.ended_at ? new Date(s.ended_at).getTime() : sa
    const offsetMs = Math.max(0, sa - runStart)
    const durMs = Math.max(1, ea - sa)
    if (offsetMs + durMs > maxEnd) maxEnd = offsetMs + durMs
    return {
      step_id: s.step_id,
      label: (STEP_LABELS[s.step_type] || s.step_type) + '：' + (s.step_name || s.agent_name || '-'),
      offsetMs, durMs, status: s.status,
    }
  })
  waterfallTotalMs.value = maxEnd || 1
  waterfallBars.value = bars
}

// ── User display name helper ──
function userDisplayName(triggeredBy) {
  if (!triggeredBy || triggeredBy === 'scheduler') return triggeredBy === 'scheduler' ? '⏱ 定时任务' : '🤖 系统自动'
  const found = userList.value.find(u => (typeof u === 'object' ? u.username : u) === triggeredBy)
  if (found && typeof found === 'object' && found.display_name) return found.display_name
  return triggeredBy
}

// ── Navigate to waterfall page ──
function goToWaterfall(runId) {
  detail.value = null
  router.push({ name: 'ConsoleTraceDetail', params: { runId } })
}

// ── Keyboard ──
function onKeydown(e) {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
    if (e.key === 'Escape') e.target.blur()
    return
  }
  if (e.key === 'Escape' && detail.value) { detail.value = null; return }
  if (e.key === 'r') { e.preventDefault(); loadTraces() }
}

onMounted(() => {
  if (route.query.status) filter.status = route.query.status
  if (route.query.workflow_name) filter.workflow_name = route.query.workflow_name
  loadTraces()
  loadStats()
  document.addEventListener('keydown', onKeydown)
})
onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
})
</script>

<style scoped>
/* ── Header ── */
.al__hd { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--v2-space-3); }
.al__hd-left { display: flex; align-items: baseline; gap: var(--v2-space-2); }
.al__title { font-size: var(--v2-text-lg); font-weight: var(--v2-font-semibold); color: var(--v2-text-1); margin: 0; }
.al__hd-right { display: flex; align-items: center; gap: var(--v2-space-2); }

/* Search */
.al__search {
  position: relative; display: flex; align-items: center;
  background: var(--v2-bg-card); border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-btn); padding: 0 8px; height: 30px; min-width: 220px;
  transition: border-color var(--v2-trans-fast);
}
.al__search:focus-within { border-color: var(--v2-text-3); }
.al__search-icon { color: var(--v2-text-4); flex-shrink: 0; }
.al__search-input {
  flex: 1; border: none; background: transparent; outline: none;
  font-size: var(--v2-text-xs); color: var(--v2-text-1); padding: 0 6px; height: 100%;
}
.al__search-input::placeholder { color: var(--v2-text-4); }
.al__search-clear {
  width: 16px; height: 16px; display: flex; align-items: center; justify-content: center;
  background: var(--v2-bg-sunken); border: none; border-radius: 50%;
  color: var(--v2-text-4); cursor: pointer; flex-shrink: 0;
}
.al__search-clear:hover { color: var(--v2-text-1); }

/* Export */
.al__export-wrap { position: relative; }
.al__btn {
  display: flex; align-items: center; gap: 4px; height: 28px; padding: 0 10px;
  font-size: var(--v2-text-xs); border-radius: var(--v2-radius-btn); cursor: pointer;
  border: var(--v2-border-width) solid var(--v2-border-2); background: transparent;
  color: var(--v2-text-3); transition: var(--v2-trans-fast);
}
.al__btn:hover { color: var(--v2-text-1); border-color: var(--v2-border-3); }
.al__export-menu {
  position: absolute; right: 0; top: calc(100% + 4px); z-index: 10;
  background: var(--v2-bg-elevated); border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-md); box-shadow: 0 4px 12px rgba(0,0,0,.1);
  overflow: hidden; min-width: 120px;
}
.al__export-menu button {
  display: block; width: 100%; text-align: left; padding: 8px 14px;
  font-size: var(--v2-text-xs); color: var(--v2-text-2); background: transparent;
  border: none; cursor: pointer; transition: background var(--v2-trans-fast);
}
.al__export-menu button:hover { background: var(--v2-bg-hover); color: var(--v2-text-1); }

/* Refresh */
.al__refresh {
  width: 28px; height: 28px; display: flex; align-items: center; justify-content: center;
  background: transparent; border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-btn); color: var(--v2-text-3); cursor: pointer; transition: var(--v2-trans-fast);
}
.al__refresh:hover { color: var(--v2-text-1); border-color: var(--v2-border-3); }
.al__refresh--spin svg { animation: al-spin .8s linear infinite; }
@keyframes al-spin { from{transform:rotate(0)} to{transform:rotate(360deg)} }

/* ── Stats ── */
.al__stats { display: flex; gap: var(--v2-space-3); margin-bottom: var(--v2-space-3); }
.al__stat {
  flex: 1; padding: 12px 16px; border-radius: var(--v2-radius-md);
  background: var(--v2-bg-card); border: var(--v2-border-width) solid var(--v2-border-1);
}
.al__stat-val {
  font-size: var(--v2-text-xl); font-weight: var(--v2-font-bold); color: var(--v2-text-1);
  font-variant-numeric: tabular-nums;
}
.al__stat-label { font-size: var(--v2-text-xs); color: var(--v2-text-4); margin-top: 2px; }
.al__stat--ok .al__stat-val { color: #15803d; }
.al__stat--err .al__stat-val { color: #b91c1c; }

/* ── Filters ── */
.al__filters {
  display: flex; align-items: center; gap: var(--v2-space-2); margin-bottom: var(--v2-space-3);
  flex-wrap: wrap;
}
.al__date {
  height: 28px; padding: 0 8px; font-size: var(--v2-text-xs); color: var(--v2-text-2);
  background: var(--v2-bg-card); border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-btn); outline: none; cursor: pointer;
}
.al__date:focus { border-color: var(--v2-text-3); }
.al__toggle { display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: var(--v2-text-xs); color: var(--v2-text-3); user-select: none; }
.al__toggle input { display: none; }
.al__toggle-track {
  width: 32px; height: 18px; border-radius: 9px; background: var(--v2-border-2);
  position: relative; transition: background .2s;
}
.al__toggle input:checked ~ .al__toggle-track { background: var(--v2-text-1); }
.al__toggle-thumb {
  position: absolute; top: 2px; left: 2px; width: 14px; height: 14px;
  border-radius: 50%; background: white; transition: transform .2s;
}
.al__toggle input:checked ~ .al__toggle-track .al__toggle-thumb { transform: translateX(14px); }
.al__toggle-label { white-space: nowrap; }
.al__count { margin-left: auto; font-size: var(--v2-text-xs); color: var(--v2-text-4); font-variant-numeric: tabular-nums; }

/* ── Table ── */
.al__table-wrap {
  background: var(--v2-bg-card); border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-lg); overflow: hidden;
}
.al__table { width: 100%; border-collapse: collapse; font-size: var(--v2-text-sm); }
.al__th {
  text-align: left; padding: 10px 12px; font-size: var(--v2-text-xs); font-weight: var(--v2-font-semibold);
  color: var(--v2-text-4); border-bottom: var(--v2-border-width) solid var(--v2-border-2);
  white-space: nowrap;
}
.al__th--sort { cursor: pointer; user-select: none; }
.al__th--sort:hover { color: var(--v2-text-2); }
.al__sort-arrow { font-size: 10px; margin-left: 2px; }
.al__th--time { width: 100px; } .al__th--user { width: 110px; } .al__th--wf { width: 90px; }
.al__th--input { width: 22%; } .al__th--output { width: 26%; }
.al__th--st { width: 80px; } .al__th--dur { width: 60px; text-align: right; }
.al__th--cost { width: 100px; text-align: right; }

.al__td {
  padding: 10px 12px; border-bottom: var(--v2-border-width) solid var(--v2-border-1);
  color: var(--v2-text-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 0;
}
.al__td--time { color: var(--v2-text-3); font-size: var(--v2-text-xs); }
.al__td--r { text-align: right; }
.al__td--input, .al__td--output { color: var(--v2-text-2); }
.al__td--cost-cell { text-align: right; white-space: nowrap; }

.al__row { cursor: pointer; transition: background var(--v2-trans-fast); }
.al__row:hover { background: var(--v2-bg-hover); }
.al__row--err { background: var(--v2-error-bg); }
.al__row--err:hover { background: var(--v2-error-bg); filter: brightness(0.97); }
.al__row--warn { background: var(--v2-warning-bg); }
.al__row--warn:hover { background: var(--v2-warning-bg); filter: brightness(0.97); }

/* User badge */
.al__user-badge {
  display: inline-block; padding: 1px 8px; border-radius: var(--v2-radius-full);
  background: var(--v2-bg-sunken); color: var(--v2-text-1); font-size: var(--v2-text-xs);
  font-weight: var(--v2-font-medium);
}
.al__user-sys { font-size: var(--v2-text-xs); color: var(--v2-text-4); }

/* Workflow tag */
.al__wf-tag {
  display: inline-block; padding: 2px 8px; border-radius: var(--v2-radius-full);
  font-size: 11px; font-weight: var(--v2-font-medium); white-space: nowrap;
}
.al__wf--blue { background: #dbeafe; color: #1d4ed8; }
.al__wf--red { background: #fee2e2; color: #b91c1c; }
.al__wf--green { background: #dcfce7; color: #15803d; }
.al__wf--purple { background: #f3e8ff; color: #7c3aed; }
.al__wf--gray { background: var(--v2-bg-sunken); color: var(--v2-text-3); }
.al__wf--orange { background: #ffedd5; color: #c2410c; }
.al__wf--teal { background: #ccfbf1; color: #0f766e; }
.al__wf--cyan { background: #cffafe; color: #0e7490; }
.al__wf--indigo { background: #e0e7ff; color: #4338ca; }

/* Status */
.al__st {
  display: inline-block; padding: 2px 8px; border-radius: var(--v2-radius-full);
  font-size: 11px; font-weight: var(--v2-font-medium); white-space: nowrap;
}
.al__st--sm { font-size: 10px; padding: 1px 6px; }
.al__st--completed, .al__st--ok { background: #dcfce7; color: #15803d; }
.al__st--failed { background: #fee2e2; color: #b91c1c; }
.al__st--anomaly { background: #fef3c7; color: #92400e; }
.al__st--paused { background: #fef3c7; color: #92400e; }
.al__st--running { background: #dbeafe; color: #1d4ed8; }
.al__st--pending { background: var(--v2-bg-sunken); color: var(--v2-text-4); }
.al__st--cancelled { background: var(--v2-bg-sunken); color: var(--v2-text-4); }

/* Token / cost in table */
.al__cost-text { font-size: var(--v2-text-xs); color: var(--v2-text-3); font-variant-numeric: tabular-nums; }
.al__mono { font-family: var(--v2-font-mono); font-size: 11px; color: var(--v2-text-3); }
.al__copyable { cursor: pointer; }
.al__copyable:hover { color: var(--v2-text-1); text-decoration: underline; }

/* Empty */
.al__empty {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: var(--v2-space-12) 0; color: var(--v2-text-4); gap: var(--v2-space-2); font-size: var(--v2-text-sm);
}
/* Loading */
.al__loading { display: flex; align-items: center; justify-content: center; padding: var(--v2-space-8) 0; }
.al__spinner {
  width: 20px; height: 20px; border: 2px solid var(--v2-border-2); border-top-color: var(--v2-text-3);
  border-radius: 50%; animation: al-spin .6s linear infinite;
}
/* Footer */
.al__footer { display: flex; justify-content: flex-end; margin-top: var(--v2-space-3); }

/* ══════════ Detail Drawer ══════════ */
.al__overlay {
  position: fixed; inset: 0; z-index: var(--v2-z-drawer, 1000);
  background: rgba(0,0,0,.3); display: flex; justify-content: flex-end;
}
.al__drawer {
  width: 560px; max-width: 92vw; height: 100%; background: var(--v2-bg-elevated);
  border-left: var(--v2-border-width) solid var(--v2-border-1);
  display: flex; flex-direction: column; overflow: hidden;
}
.al__drawer-hd {
  display: flex; align-items: center; justify-content: space-between;
  padding: var(--v2-space-4) var(--v2-space-5); border-bottom: var(--v2-border-width) solid var(--v2-border-2); flex-shrink: 0;
}
.al__drawer-title-wrap { display: flex; align-items: center; gap: var(--v2-space-2); }
.al__drawer-close {
  width: 28px; height: 28px; display: flex; align-items: center; justify-content: center;
  background: transparent; border: none; color: var(--v2-text-3); cursor: pointer;
  border-radius: var(--v2-radius-sm); transition: var(--v2-trans-fast);
}
.al__drawer-close:hover { color: var(--v2-text-1); background: var(--v2-bg-hover); }
.al__drawer-body {
  flex: 1; overflow-y: auto; padding: var(--v2-space-4) var(--v2-space-5);
  display: flex; flex-direction: column; gap: var(--v2-space-5);
}

/* Section */
.al__section { display: flex; flex-direction: column; gap: var(--v2-space-2); }
.al__section-title {
  font-size: var(--v2-text-xs); font-weight: var(--v2-font-semibold); color: var(--v2-text-4);
  text-transform: uppercase; letter-spacing: .5px; margin: 0;
}
.al__kv { display: flex; align-items: center; gap: var(--v2-space-3); }
.al__k { font-size: var(--v2-text-xs); color: var(--v2-text-4); min-width: 64px; flex-shrink: 0; }
.al__v { font-size: var(--v2-text-sm); color: var(--v2-text-1); word-break: break-all; }

/* Bubbles */
.al__bubble {
  padding: 10px 14px; border-radius: var(--v2-radius-md); font-size: var(--v2-text-sm);
  line-height: 1.6; white-space: pre-wrap; word-break: break-word;
}
.al__bubble--user { background: var(--v2-bg-sunken); color: var(--v2-text-1); border-left: 3px solid var(--v2-text-3); }
.al__bubble--ai { background: #f0f9ff; color: var(--v2-text-1); border-left: 3px solid #3b82f6; }

/* ── Steps (timeline) ── */
.al__step-count { font-weight: normal; color: var(--v2-text-4); margin-left: 4px; }
.al__steps { display: flex; flex-direction: column; gap: 0; padding-left: 4px; }
.al__step { display: flex; gap: 12px; }
.al__step--err .al__step-body { background: var(--v2-error-bg); border-radius: var(--v2-radius-sm); padding: 6px 8px; margin: -4px -8px; }

/* Timeline line + dot */
.al__step-line { display: flex; flex-direction: column; align-items: center; width: 16px; flex-shrink: 0; }
.al__step-dot {
  width: 10px; height: 10px; border-radius: 50%; border: 2px solid var(--v2-border-3);
  background: var(--v2-bg-card); flex-shrink: 0; margin-top: 5px;
}
.al__step-dot--completed, .al__step-dot--ok { border-color: #15803d; background: #dcfce7; }
.al__step-dot--failed { border-color: #b91c1c; background: #fee2e2; }
.al__step-dot--anomaly { border-color: #92400e; background: #fef3c7; }
.al__step-dot--running { border-color: #1d4ed8; background: #dbeafe; }
.al__step-connector { width: 2px; flex: 1; background: var(--v2-border-2); min-height: 12px; }

.al__step-body { flex: 1; min-width: 0; padding-bottom: 12px; }
.al__step-header { display: flex; align-items: center; justify-content: space-between; cursor: pointer; gap: 8px; }
.al__step-header:hover .al__step-name { color: var(--v2-text-1); }
.al__step-name { font-size: var(--v2-text-sm); font-weight: var(--v2-font-medium); color: var(--v2-text-2); transition: color var(--v2-trans-fast); }
.al__step-meta { display: flex; align-items: center; gap: var(--v2-space-1); flex-shrink: 0; }
.al__step-model {
  font-size: 10px; font-family: var(--v2-font-mono); color: var(--v2-text-4);
  padding: 1px 5px; background: var(--v2-bg-sunken); border-radius: 3px;
}
.al__step-chevron { color: var(--v2-text-4); transition: transform .2s; }
.al__step-chevron--open { transform: rotate(180deg); }

/* Step detail (expandable) */
.al__step-detail { margin-top: 8px; display: flex; flex-direction: column; gap: 6px; }
.al__step-block {
  background: var(--v2-bg-sunken); border-radius: var(--v2-radius-sm); padding: 8px 10px;
}
.al__step-block--err { background: var(--v2-error-bg); }
.al__step-block-label {
  font-size: 10px; font-weight: var(--v2-font-semibold); color: var(--v2-text-4);
  text-transform: uppercase; letter-spacing: .5px; margin-bottom: 4px;
}
.al__step-pre {
  font-size: 12px; font-family: var(--v2-font-mono); color: var(--v2-text-2);
  white-space: pre-wrap; word-break: break-word; line-height: 1.5; margin: 0;
}
.al__step-block--err .al__step-pre { color: var(--v2-error); }
.al__step-kv-row { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }
.al__step-tag {
  font-size: 10px; font-family: var(--v2-font-mono); color: var(--v2-text-4);
  padding: 1px 6px; background: var(--v2-bg-sunken); border-radius: 3px;
}

/* Expand transition */
.al-expand-enter-active { transition: all .2s ease; overflow: hidden; }
.al-expand-leave-active { transition: all .15s ease; overflow: hidden; }
.al-expand-enter-from, .al-expand-leave-to { opacity: 0; max-height: 0; }
.al-expand-enter-to, .al-expand-leave-from { opacity: 1; max-height: 500px; }

/* Advice */
.al__advice-card {
  padding: 12px 14px; border-radius: var(--v2-radius-md); background: var(--v2-error-bg);
  border-left: 3px solid var(--v2-error); display: flex; flex-direction: column; gap: 8px;
}
.al__advice-card--warn { background: var(--v2-warning-bg); border-left-color: var(--v2-warning); }
.al__advice-err { font-size: var(--v2-text-sm); color: var(--v2-error-text); font-family: var(--v2-font-mono); font-size: 12px; }
.al__advice-text {
  display: flex; align-items: flex-start; gap: 6px; font-size: var(--v2-text-sm);
  color: var(--v2-text-2); line-height: 1.5;
}
.al__advice-text svg { flex-shrink: 0; margin-top: 2px; color: var(--v2-warning); }
.al__advice-card:not(.al__advice-card--warn) .al__advice-text svg { color: var(--v2-error); }

/* Drawer transition */
.al-drawer-enter-active { transition: opacity .25s ease, transform .3s cubic-bezier(0.16,1,0.3,1); }
.al-drawer-leave-active { transition: opacity .2s ease, transform .2s ease; }
.al-drawer-enter-from { opacity: 0; }
.al-drawer-enter-from .al__drawer { transform: translateX(100%); }
.al-drawer-leave-to { opacity: 0; }
.al-drawer-leave-to .al__drawer { transform: translateX(100%); }

/* ── Waterfall ── */
.al__waterfall-btn {
  display: flex; align-items: center; gap: 8px; width: 100%;
  padding: 10px 14px; border-radius: var(--v2-radius-btn);
  border: var(--v2-border-width) solid var(--v2-border-2);
  background: var(--v2-bg-card); color: var(--v2-text-2);
  font-size: var(--v2-text-sm); cursor: pointer;
  transition: all var(--v2-trans-fast);
}
.al__waterfall-btn:hover {
  border-color: var(--v2-text-3); color: var(--v2-text-1); background: var(--v2-bg-hover);
}
.al__waterfall-btn svg:last-child { margin-left: auto; color: var(--v2-text-4); }

.al__waterfall {
  background: var(--v2-bg-sunken); border-radius: var(--v2-radius-md); padding: 12px;
  display: flex; flex-direction: column; gap: 6px;
}
.al__wf-row { display: flex; align-items: center; gap: 8px; min-height: 22px; }
.al__wf-label {
  width: 120px; flex-shrink: 0; font-size: 10px; color: var(--v2-text-3);
  text-overflow: ellipsis; overflow: hidden; white-space: nowrap; text-align: right;
}
.al__wf-track {
  flex: 1; height: 16px; position: relative; background: var(--v2-bg-card);
  border-radius: 3px; overflow: hidden;
}
.al__wf-bar {
  position: absolute; top: 1px; height: 14px; border-radius: 2px;
  min-width: 2px; display: flex; align-items: center; justify-content: center;
  transition: width .3s ease, left .3s ease;
}
.al__wf-bar--completed { background: #86efac; }
.al__wf-bar--failed    { background: #fca5a5; }
.al__wf-bar--running   { background: #93c5fd; }
.al__wf-bar--paused    { background: #fde68a; }
.al__wf-bar--pending   { background: var(--v2-border-2); }
.al__wf-bar-label {
  font-size: 9px; color: var(--v2-text-1); white-space: nowrap;
  font-family: var(--v2-font-mono); font-weight: var(--v2-font-medium);
  padding: 0 3px;
}
.al__wf-axis {
  display: flex; justify-content: space-between; padding-left: 128px;
  font-size: 9px; color: var(--v2-text-4); font-family: var(--v2-font-mono);
  margin-top: 2px;
}

/* Responsive */
@media (max-width: 1200px) {
  .al__filters { gap: var(--v2-space-1); }
  .al__th--output, .al__th--cost { display: none; }
  .al__td--output, .al__td--cost-cell { display: none; }
  .al__stats { flex-wrap: wrap; }
  .al__stat { min-width: calc(50% - var(--v2-space-2)); }
  .al__search { min-width: 160px; }
  .al__wf-label { width: 80px; }
  .al__wf-axis { padding-left: 88px; }
}
</style>
