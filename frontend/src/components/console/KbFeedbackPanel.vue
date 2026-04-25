<template>
  <div class="kbfb">
    <!-- 顶部：4 张关键卡片 -->
    <div class="kbfb__cards">
      <div class="kbfb__card">
        <div class="kbfb__card-num">{{ stats.total ?? 0 }}</div>
        <div class="kbfb__card-label">总反馈（{{ stats.window_days ?? days }} 天）</div>
      </div>
      <div class="kbfb__card kbfb__card--pos">
        <div class="kbfb__card-num">{{ stats.positive ?? 0 }}</div>
        <div class="kbfb__card-label">👍 正向</div>
      </div>
      <div class="kbfb__card kbfb__card--neg">
        <div class="kbfb__card-num">{{ stats.negative ?? 0 }}</div>
        <div class="kbfb__card-label">👎 负向</div>
      </div>
      <div class="kbfb__card kbfb__card--rate" :class="rateBadgeClass">
        <div class="kbfb__card-num">{{ negRatePct }}</div>
        <div class="kbfb__card-label">负向率（目标 ≤ 10%）</div>
      </div>
    </div>

    <!-- 聚合：分库 / 分原因 / 分来源 -->
    <div class="kbfb__breakdowns">
      <div class="kbfb__bd">
        <div class="kbfb__bd-h">按知识库</div>
        <div v-if="!stats.by_kb?.length" class="kbfb__bd-nil">暂无数据</div>
        <div v-else class="kbfb__bd-list">
          <div v-for="row in stats.by_kb" :key="String(row.kb_id)" class="kbfb__bd-row">
            <span class="kbfb__bd-name" :title="row.kb_name">{{ row.kb_name || '(unknown)' }}</span>
            <span class="kbfb__bd-bar"><span class="kbfb__bd-bar-fg" :style="{ width: barPct(row.negative, row.total) }"></span></span>
            <span class="kbfb__bd-num">{{ row.negative }}/{{ row.total }}</span>
          </div>
        </div>
      </div>

      <div class="kbfb__bd">
        <div class="kbfb__bd-h">按负向原因（rating=-1）</div>
        <div v-if="!stats.by_reason?.length" class="kbfb__bd-nil">暂无负向反馈</div>
        <div v-else class="kbfb__bd-list">
          <div v-for="row in stats.by_reason" :key="row.rating_reason" class="kbfb__bd-row">
            <span class="kbfb__bd-name">{{ REASON_LABEL[row.rating_reason] || row.rating_reason }}</span>
            <span class="kbfb__bd-bar"><span class="kbfb__bd-bar-fg kbfb__bd-bar-fg--neg" :style="{ width: barPct(row.count, maxReason) }"></span></span>
            <span class="kbfb__bd-num">{{ row.count }}</span>
          </div>
        </div>
      </div>

      <div class="kbfb__bd">
        <div class="kbfb__bd-h">按来源</div>
        <div v-if="!stats.by_source?.length" class="kbfb__bd-nil">暂无数据</div>
        <div v-else class="kbfb__bd-list">
          <div v-for="row in stats.by_source" :key="row.source" class="kbfb__bd-row">
            <span class="kbfb__bd-name">{{ SOURCE_LABEL[row.source] || row.source }}</span>
            <span class="kbfb__bd-bar"><span class="kbfb__bd-bar-fg" :style="{ width: barPct(row.negative, row.total) }"></span></span>
            <span class="kbfb__bd-num">{{ row.negative }}/{{ row.total }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 列表过滤器 + 表格 -->
    <div class="kbfb__filter">
      <span class="kbfb__filter-label">窗口</span>
      <el-select v-model="days" size="small" style="width:90px" @change="reload">
        <el-option label="7 天" :value="7" />
        <el-option label="30 天" :value="30" />
        <el-option label="90 天" :value="90" />
      </el-select>
      <span class="kbfb__filter-label">评分</span>
      <el-select v-model="filter.rating" size="small" style="width:100px" clearable placeholder="全部" @change="reloadList">
        <el-option label="👍 正向" :value="1" />
        <el-option label="👎 负向" :value="-1" />
        <el-option label="中性 0" :value="0" />
      </el-select>
      <span class="kbfb__filter-label">来源</span>
      <el-select v-model="filter.source" size="small" style="width:140px" clearable placeholder="全部" @change="reloadList">
        <el-option v-for="(label, val) in SOURCE_LABEL" :key="val" :label="label" :value="val" />
      </el-select>
      <el-button size="small" @click="reload" :loading="loading">刷新</el-button>
    </div>

    <el-table :data="items" size="small" stripe v-loading="loading" :empty-text="loading ? '加载中…' : '暂无反馈'">
      <el-table-column label="评分" width="76">
        <template #default="{ row }">
          <span class="kbfb__rating" :class="ratingClass(row.rating)">{{ ratingIcon(row.rating) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="原因" width="110">
        <template #default="{ row }">
          <span v-if="row.rating_reason" class="kbfb__reason-chip">{{ REASON_LABEL[row.rating_reason] || row.rating_reason }}</span>
          <span v-else class="kbfb__muted">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="query" label="Query" min-width="220">
        <template #default="{ row }">
          <div class="kbfb__query" :title="row.query">{{ row.query }}</div>
          <div v-if="row.free_text" class="kbfb__free" :title="row.free_text">备注：{{ row.free_text }}</div>
        </template>
      </el-table-column>
      <el-table-column label="kb_id" width="120">
        <template #default="{ row }">
          <span v-if="row.kb_id" class="kbfb__mono" :title="row.kb_id">{{ row.kb_id.slice(0, 8) }}…</span>
          <span v-else class="kbfb__muted">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="user_id" label="用户" width="110" />
      <el-table-column label="trace" width="120">
        <template #default="{ row }">
          <span v-if="row.trace_id" class="kbfb__mono" :title="row.trace_id">{{ row.trace_id.slice(0, 10) }}…</span>
          <span v-else class="kbfb__muted">-</span>
        </template>
      </el-table-column>
      <el-table-column label="来源" width="110">
        <template #default="{ row }">{{ SOURCE_LABEL[row.source] || row.source }}</template>
      </el-table-column>
      <el-table-column prop="created_at" label="时间" width="160">
        <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
      </el-table-column>
    </el-table>

    <div class="kbfb__pager" v-if="total > limit">
      <el-pagination
        size="small"
        layout="prev, pager, next, total"
        :total="total"
        :page-size="limit"
        :current-page="page"
        @current-change="onPageChange"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { knowledgeV2Api } from '@/api/admin/knowledgeV2'

const REASON_LABEL = {
  inaccurate:  '不准确',
  irrelevant:  '不相关',
  outdated:    '已过期',
  incomplete:  '不完整',
  other:       '其它',
  '(none)':    '未填写',
}
const SOURCE_LABEL = {
  biz_kb:           '业务前台',
  admin_kb:         'Console 检索',
  copilot_biz_rag:  'Copilot RAG',
  api_external:     '外部 API',
}

const days   = ref(7)
const filter = ref({ rating: '', source: '' })
const stats  = ref({})
const items  = ref([])
const total  = ref(0)
const limit  = 50
const page   = ref(1)
const loading = ref(false)

const negRatePct = computed(() => {
  const r = Number(stats.value.negative_rate || 0)
  return `${(r * 100).toFixed(1)}%`
})
const rateBadgeClass = computed(() => {
  const r = Number(stats.value.negative_rate || 0)
  if (r > 0.2)  return 'kbfb__card--rate-bad'
  if (r > 0.1)  return 'kbfb__card--rate-warn'
  return 'kbfb__card--rate-ok'
})
const maxReason = computed(() => {
  const arr = stats.value.by_reason || []
  return arr.reduce((m, x) => Math.max(m, x.count || 0), 0) || 1
})

function barPct(part, whole) {
  const w = Number(whole || 0)
  if (!w) return '0%'
  const p = Math.max(0, Math.min(1, Number(part || 0) / w))
  return `${(p * 100).toFixed(0)}%`
}
function ratingIcon(r) {
  return r === 1 ? '👍' : r === -1 ? '👎' : '·'
}
function ratingClass(r) {
  return r === 1 ? 'kbfb__rating--pos' : r === -1 ? 'kbfb__rating--neg' : 'kbfb__rating--neu'
}
function fmtTime(v) {
  if (!v) return '-'
  const d = new Date(v)
  if (isNaN(d)) return String(v).slice(0, 16)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

async function loadStats() {
  try {
    stats.value = await knowledgeV2Api.getFeedbackStats({ days: days.value }) ?? {}
  } catch (err) {
    console.warn('[KbFeedbackPanel] stats failed', err)
    stats.value = {}
  }
}
async function loadList() {
  loading.value = true
  try {
    const params = { days: days.value, limit, offset: (page.value - 1) * limit }
    if (filter.value.rating !== '' && filter.value.rating != null) params.rating = filter.value.rating
    if (filter.value.source) params.source = filter.value.source
    const r = await knowledgeV2Api.listFeedback(params)
    items.value = r?.items ?? []
    total.value = r?.total ?? items.value.length
  } catch (err) {
    console.warn('[KbFeedbackPanel] list failed', err)
    items.value = []
    total.value = 0
    ElMessage.warning('反馈列表加载失败')
  } finally {
    loading.value = false
  }
}
async function reload() {
  page.value = 1
  await Promise.all([loadStats(), loadList()])
}
async function reloadList() {
  page.value = 1
  await loadList()
}
function onPageChange(p) {
  page.value = p
  loadList()
}

onMounted(reload)
</script>

<style scoped>
.kbfb { display: flex; flex-direction: column; gap: var(--v2-space-3); }

.kbfb__cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--v2-space-3); }
.kbfb__card { padding: var(--v2-space-4) var(--v2-space-3); background: var(--v2-bg-sunken); border: 1px solid var(--v2-border-1); border-radius: var(--v2-radius-md); text-align: center; }
.kbfb__card-num { font-size: 28px; font-weight: var(--v2-font-bold); color: var(--v2-text-1); line-height: 1.1; }
.kbfb__card-label { margin-top: 4px; font-size: 11px; color: var(--v2-text-3); }
.kbfb__card--pos .kbfb__card-num { color: #16a34a; }
.kbfb__card--neg .kbfb__card-num { color: #dc2626; }
.kbfb__card--rate-ok   .kbfb__card-num { color: #16a34a; }
.kbfb__card--rate-warn .kbfb__card-num { color: #d97706; }
.kbfb__card--rate-bad  .kbfb__card-num { color: #dc2626; }

.kbfb__breakdowns { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--v2-space-3); }
.kbfb__bd { background: var(--v2-bg-sunken); border: 1px solid var(--v2-border-1); border-radius: var(--v2-radius-md); padding: var(--v2-space-3); }
.kbfb__bd-h { font-size: 11px; font-weight: var(--v2-font-semibold); color: var(--v2-text-3); text-transform: uppercase; letter-spacing: .4px; margin-bottom: var(--v2-space-2); }
.kbfb__bd-list { display: flex; flex-direction: column; gap: 6px; }
.kbfb__bd-nil { font-size: 12px; color: var(--v2-text-4); padding: var(--v2-space-2) 0; }
.kbfb__bd-row { display: grid; grid-template-columns: 1fr 80px 60px; gap: 8px; align-items: center; font-size: 12px; }
.kbfb__bd-name { color: var(--v2-text-1); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kbfb__bd-bar  { width: 100%; height: 6px; background: var(--v2-bg-card); border-radius: 3px; overflow: hidden; }
.kbfb__bd-bar-fg { display: block; height: 100%; background: var(--v2-brand-primary); }
.kbfb__bd-bar-fg--neg { background: #f87171; }
.kbfb__bd-num { font-size: 11px; color: var(--v2-text-3); text-align: right; font-variant-numeric: tabular-nums; }

.kbfb__filter { display: flex; align-items: center; gap: 8px; padding: var(--v2-space-2) var(--v2-space-3); background: var(--v2-bg-sunken); border: 1px solid var(--v2-border-1); border-radius: var(--v2-radius-md); flex-wrap: wrap; }
.kbfb__filter-label { font-size: 11px; color: var(--v2-text-3); }

.kbfb__rating { font-size: 16px; }
.kbfb__rating--pos { color: #16a34a; }
.kbfb__rating--neg { color: #dc2626; }
.kbfb__rating--neu { color: var(--v2-text-4); }

.kbfb__reason-chip { font-size: 10px; padding: 1px 6px; background: #fee2e2; color: #991b1b; border-radius: 3px; }
.kbfb__query { font-size: 12px; color: var(--v2-text-1); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kbfb__free  { margin-top: 2px; font-size: 11px; color: var(--v2-text-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kbfb__mono  { font-family: var(--v2-font-mono); font-size: 11px; color: var(--v2-text-3); }
.kbfb__muted { font-size: 11px; color: var(--v2-text-4); }

.kbfb__pager { display: flex; justify-content: flex-end; padding-top: var(--v2-space-2); }

@media (max-width: 1100px) {
  .kbfb__cards { grid-template-columns: repeat(2, 1fr); }
  .kbfb__breakdowns { grid-template-columns: 1fr; }
}
</style>
