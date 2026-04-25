<template>
  <div class="cm">
    <div class="cm__toolbar">
      <div class="cm__tb-left"><h2 class="cm__title">记忆治理</h2><span class="cm__count">{{ records.length }}</span></div>
      <div class="cm__tb-filters">
        <V2Input v-model="filter.customer_id" placeholder="客户 ID" clearable size="sm" style="width:130px" @clear="load" />
        <V2Select v-model="filter.risk_level" :options="[{label:'低风险',value:'low'},{label:'中风险',value:'medium'},{label:'高风险',value:'high'}]" placeholder="风险" clearable size="sm" style="width:100px" @update:model-value="load" />
        <V2Select v-model="filter.is_active" :options="[{label:'启用',value:1},{label:'停用',value:0}]" placeholder="状态" clearable size="sm" style="width:100px" @update:model-value="load" />
        <V2Button variant="primary" size="sm" @click="load">查询</V2Button>
      </div>
    </div>

    <div class="cm__split">
      <!-- Left: memory list -->
      <div class="cm__list">
        <div v-for="m in records" :key="m.memory_id" class="cm__item" :class="{ 'cm__item--active': sel?.memory_id === m.memory_id, 'cm__item--risk': m.risk_level === 'high', 'cm__item--off': !m.is_active }" @click="selectRecord(m)">
          <div class="cm__item-top">
            <span class="cm__item-summary">{{ m.content_summary || '(无摘要)' }}</span>
            <span class="cm__risk" :class="'cm__risk--' + m.risk_level">{{ riskLabel(m.risk_level) }}</span>
          </div>
          <div class="cm__item-mid">
            <span class="cm__kind-chip">{{ m.memory_kind }}</span>
            <span v-if="m.pii_flag" class="cm__pii-badge">PII</span>
            <span class="cm__st" :class="m.is_active ? 'cm__st--on' : 'cm__st--off'">{{ m.is_active ? '启用' : '停用' }}</span>
          </div>
          <div class="cm__item-sub">
            <span>{{ m.customer_id }}</span>
            <span>{{ m.source_type || '-' }}</span>
            <span v-if="m.expires_at">过期 {{ m.expires_at }}</span>
          </div>
        </div>
        <div v-if="!records.length" class="cm__nil">暂无记忆记录</div>
        <div class="cm__pg">
          <V2Pager v-model="page" :total="total" :page-size="20" @change="load" />
        </div>
      </div>

      <!-- Right: detail panel -->
      <div class="cm__detail" v-if="sel">
        <div class="cm__dh">
          <div>
            <div class="cm__dh-customer">{{ sel.customer_id }}</div>
            <div class="cm__dh-meta"><span class="cm__mono">{{ sel.memory_id }}</span></div>
          </div>
          <div class="cm__dh-flags">
            <span class="cm__risk cm__risk--lg" :class="'cm__risk--' + sel.risk_level">{{ riskLabel(sel.risk_level) }}</span>
            <span v-if="sel.pii_flag" class="cm__pii-badge cm__pii-badge--lg">PII</span>
          </div>
        </div>

        <!-- Governance strip -->
        <div class="cm__gov">
          <div class="cm__gc"><span class="cm__gc-k">记忆类型</span><span class="cm__kind-chip">{{ sel.memory_kind }}</span></div>
          <div class="cm__gc"><span class="cm__gc-k">来源</span>{{ sel.source_type || '-' }}</div>
          <div class="cm__gc"><span class="cm__gc-k">风险等级</span><span :class="'cm__risk-text--' + sel.risk_level">{{ riskLabel(sel.risk_level) }}</span></div>
          <div class="cm__gc"><span class="cm__gc-k">隐私数据</span><span :class="sel.pii_flag ? 'cm__pii-text' : ''">{{ sel.pii_flag ? '是' : '否' }}</span></div>
          <div class="cm__gc"><span class="cm__gc-k">状态</span>{{ sel.is_active ? '启用' : '停用' }}</div>
          <div class="cm__gc"><span class="cm__gc-k">过期时间</span>{{ sel.expires_at || '永不过期' }}</div>
        </div>

        <!-- Summary -->
        <div class="cm__sec">
          <div class="cm__sec-label">内容摘要</div>
          <div class="cm__summary">{{ sel.content_summary || '(空)' }}</div>
        </div>

        <!-- Timestamps -->
        <div class="cm__sec">
          <div class="cm__sec-label">时间线</div>
          <div class="cm__timeline">
            <div class="cm__tl-item"><span class="cm__tl-dot" /> 创建 · {{ sel.created_at }}</div>
            <div class="cm__tl-item"><span class="cm__tl-dot" /> 更新 · {{ sel.updated_at }}</div>
            <div v-if="sel.expires_at" class="cm__tl-item"><span class="cm__tl-dot cm__tl-dot--warn" /> 过期 · {{ sel.expires_at }}</div>
          </div>
        </div>

        <!-- Feedback -->
        <div class="cm__sec" v-if="sel.is_active">
          <div class="cm__sec-label">反馈</div>
          <div class="cm__fb-row">
            <V2Input v-model="fbComment" size="sm" placeholder="备注（可选）" style="flex:1" />
            <button class="cm__fb-btn cm__fb-btn--ok" @click="doFeedback(sel.memory_id, 'human_review')">✓ 有用</button>
            <button class="cm__fb-btn cm__fb-btn--warn" @click="doFeedback(sel.memory_id, 'flag_pii')">✗ 不准确</button>
          </div>
        </div>

        <!-- Feedback history -->
        <div class="cm__sec">
          <div class="cm__sec-label">反馈历史</div>
          <div v-if="feedbackList.length" class="cm__fb-hist">
            <div v-for="fb in feedbackList" :key="fb.id" class="cm__fb-hist-item">
              <span class="cm__fb-type">{{ fbTypeLabel(fb.feedback_type) }}</span>
              <span class="cm__fb-reason">{{ fb.reason || '-' }}</span>
              <span class="cm__fb-by">{{ fb.operated_by }}</span>
              <span class="cm__fb-time">{{ fb.created_at }}</span>
            </div>
          </div>
          <div v-else class="cm__fb-hist-nil">暂无反馈记录</div>
        </div>

        <!-- Actions -->
        <div class="cm__actions" v-if="sel.is_active">
          <button class="cm__act-btn cm__act-btn--expire" @click="doExpire(sel.memory_id)">⏰ 强制过期</button>
          <button class="cm__act-btn cm__act-btn--disable" @click="doDisable(sel.memory_id)">⊘ 停用</button>
        </div>
      </div>
      <div class="cm__detail cm__detail--empty" v-else><span class="cm__muted">← 请选择一条记忆记录</span></div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { adminApi } from '@/api/admin/index'
import V2Input from '@/components/v2/V2Input.vue'
import V2Select from '@/components/v2/V2Select.vue'
import V2Button from '@/components/v2/V2Button.vue'
import V2Pager from '@/components/v2/V2Pager.vue'

const records = ref([]), loading = ref(false), total = ref(0), page = ref(1)
const sel = ref(null), fbComment = ref(''), feedbackList = ref([])
const filter = ref({ customer_id: '', risk_level: '', is_active: '' })

const _RISK = { low: '低风险', medium: '中风险', high: '高风险' }
function riskLabel(v) { return _RISK[v] || v || '-' }

const _FB_TYPES = { disable: '停用', expire: '过期', flag_pii: '标记隐私', human_review: '人工审核', auto: '自动' }
function fbTypeLabel(v) { return _FB_TYPES[v] || v || '-' }

async function load() {
  loading.value = true
  try {
    const p = { limit: 20, offset: (page.value - 1) * 20 }
    if (filter.value.customer_id) p.customer_id = filter.value.customer_id
    if (filter.value.risk_level) p.risk_level = filter.value.risk_level
    if (filter.value.is_active !== '') p.is_active = filter.value.is_active
    const r = await adminApi.getMemoryRecords(p)
    records.value = r?.items ?? (Array.isArray(r) ? r : [])
    total.value = r?.total ?? records.value.length
  } catch { records.value = [] }
  finally { loading.value = false }
}

async function selectRecord(m) {
  sel.value = m
  feedbackList.value = []
  try { feedbackList.value = await adminApi.getMemoryFeedback(m.memory_id) ?? [] } catch { /* ignore */ }
}

async function doExpire(id) {
  if (!confirm('确定要强制过期该记忆记录吗？')) return
  try { await adminApi.expireMemory(id); sel.value = null; await load() } catch (e) { console.warn('[Memory] expire failed', e) }
}

async function doDisable(id) {
  if (!confirm('确定要停用该记忆记录吗？此操作不可逆。')) return
  try { await adminApi.disableMemory(id); sel.value = null; await load() } catch (e) { console.warn('[Memory] disable failed', e) }
}

async function doFeedback(id, fbType) {
  try {
    await adminApi.feedbackMemory(id, { feedback_type: fbType, reason: fbComment.value || null })
    fbComment.value = ''
    feedbackList.value = await adminApi.getMemoryFeedback(id) ?? []
  } catch (e) { console.warn('[Memory] feedback failed', e) }
}

onMounted(load)
</script>

<style scoped>
.cm__toolbar { display: flex; align-items: center; gap: var(--v2-space-3); padding: var(--v2-space-2) var(--v2-space-3); margin-bottom: var(--v2-space-3); background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-lg); flex-wrap: wrap; }
.cm__tb-left { display: flex; align-items: center; gap: var(--v2-space-2); margin-right: auto; }
.cm__title { font-size: var(--v2-text-md); font-weight: var(--v2-font-semibold); color: var(--v2-text-1); margin: 0; }
.cm__count { font-size: var(--v2-text-xs); padding: 0 5px; background: var(--v2-bg-sunken); color: var(--v2-text-3); border-radius: var(--v2-radius-sm); }
.cm__tb-filters { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }

.cm__split { display: grid; grid-template-columns: 420px 1fr; gap: var(--v2-space-3); min-height: calc(100vh - 180px); }

/* Memory list */
.cm__list { background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-lg); overflow-y: auto; display: flex; flex-direction: column; }
.cm__item { padding: var(--v2-space-3); border-bottom: 1px solid var(--v2-border-1); cursor: pointer; transition: background var(--v2-trans-fast); }
.cm__item:hover { background: var(--v2-bg-sunken); }
.cm__item--active { background: var(--v2-brand-bg); border-left: 3px solid var(--v2-brand-primary); }
.cm__item--risk { border-left: 3px solid var(--v2-error); }
.cm__item--active.cm__item--risk { border-left-color: var(--v2-brand-primary); }
.cm__item--off { opacity: .5; }
.cm__item-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 2px; }
.cm__item-summary { font-size: 12px; color: var(--v2-text-1); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-right: 6px; }
.cm__item-mid { display: flex; gap: 4px; align-items: center; margin-bottom: 2px; }
.cm__item-sub { font-size: 10px; color: var(--v2-text-4); display: flex; gap: var(--v2-space-3); }

.cm__risk { font-size: 9px; font-weight: var(--v2-font-semibold); padding: 1px 5px; border-radius: 3px; text-transform: uppercase; }
.cm__risk--high { background: var(--v2-error-bg); color: var(--v2-error-text); }
.cm__risk--medium { background: var(--v2-warning-bg); color: var(--v2-warning-text); }
.cm__risk--low { background: var(--v2-success-bg); color: var(--v2-success-text); }
.cm__risk--lg { font-size: 10px; padding: 2px 7px; }
.cm__risk-text--high { color: var(--v2-error); font-weight: var(--v2-font-semibold); }
.cm__risk-text--medium { color: var(--v2-warning); font-weight: var(--v2-font-semibold); }
.cm__risk-text--low { color: var(--v2-success); }

.cm__pii-badge { font-size: 8px; font-weight: var(--v2-font-bold); padding: 1px 4px; background: var(--v2-error); color: #fff; border-radius: 2px; letter-spacing: .5px; }
.cm__pii-badge--lg { font-size: 9px; padding: 2px 6px; }
.cm__pii-text { color: var(--v2-error); font-weight: var(--v2-font-semibold); }

.cm__kind-chip { font-size: 9px; padding: 0 5px; background: var(--v2-ai-purple-bg); color: var(--v2-ai-purple); border-radius: 3px; font-weight: var(--v2-font-medium); }
.cm__st { font-size: 9px; padding: 1px 4px; border-radius: 3px; }
.cm__st--on { background: var(--v2-success-bg); color: var(--v2-success-text); }
.cm__st--off { background: var(--v2-bg-sunken); color: var(--v2-text-4); }

.cm__pg { margin-top: auto; padding: 8px var(--v2-space-3); border-top: 1px solid var(--v2-border-1); display: flex; justify-content: flex-end; }

/* Detail */
.cm__detail { background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-lg); padding: var(--v2-space-4); overflow-y: auto; display: flex; flex-direction: column; gap: var(--v2-space-3); }
.cm__detail--empty { align-items: center; justify-content: center; }

.cm__dh { display: flex; justify-content: space-between; align-items: flex-start; padding-bottom: var(--v2-space-3); border-bottom: 1px solid var(--v2-border-2); }
.cm__dh-customer { font-size: var(--v2-text-md); font-weight: var(--v2-font-semibold); color: var(--v2-text-1); }
.cm__dh-meta { font-size: 10px; color: var(--v2-text-4); margin-top: 2px; }
.cm__dh-flags { display: flex; align-items: center; gap: 6px; }

/* Governance strip */
.cm__gov { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
.cm__gc { padding: 6px 8px; background: var(--v2-bg-sunken); border-radius: var(--v2-radius-md); font-size: 12px; color: var(--v2-text-1); }
.cm__gc-k { display: block; font-size: 9px; color: var(--v2-text-4); text-transform: uppercase; letter-spacing: .3px; }

.cm__sec { } .cm__sec-label { font-size: 10px; font-weight: var(--v2-font-semibold); color: var(--v2-text-4); text-transform: uppercase; letter-spacing: .5px; margin-bottom: 4px; }
.cm__summary { font-size: 13px; color: var(--v2-text-1); line-height: 1.6; padding: var(--v2-space-3); background: var(--v2-bg-sunken); border-radius: var(--v2-radius-md); white-space: pre-wrap; max-height: 160px; overflow-y: auto; }

/* Timeline */
.cm__timeline { display: flex; flex-direction: column; gap: 6px; }
.cm__tl-item { display: flex; align-items: center; gap: 8px; font-size: 11px; color: var(--v2-text-2); }
.cm__tl-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--v2-gray-300); flex-shrink: 0; }
.cm__tl-dot--warn { background: var(--v2-warning); box-shadow: 0 0 0 2px var(--v2-warning-bg); }

/* Feedback */
.cm__fb-row { display: flex; gap: 6px; align-items: center; }
.cm__fb-btn { padding: 4px 10px; border: none; border-radius: var(--v2-radius-md); font-size: 11px; font-weight: var(--v2-font-semibold); cursor: pointer; }
.cm__fb-btn--ok { background: var(--v2-success-bg); color: var(--v2-success-text); } .cm__fb-btn--ok:hover { background: var(--v2-success); color: #fff; }
.cm__fb-btn--warn { background: var(--v2-warning-bg); color: var(--v2-warning-text); } .cm__fb-btn--warn:hover { background: var(--v2-warning); color: #fff; }
.cm__fb-hist { display: flex; flex-direction: column; gap: 4px; }
.cm__fb-hist-item { display: flex; align-items: center; gap: 8px; font-size: 11px; padding: 4px 6px; background: var(--v2-bg-sunken); border-radius: var(--v2-radius-sm); }
.cm__fb-type { font-weight: var(--v2-font-semibold); color: var(--v2-brand-primary); min-width: 56px; }
.cm__fb-reason { flex: 1; color: var(--v2-text-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cm__fb-by { color: var(--v2-text-3); font-size: 10px; }
.cm__fb-time { color: var(--v2-text-4); font-size: 10px; white-space: nowrap; }
.cm__fb-hist-nil { font-size: 11px; color: var(--v2-text-4); padding: 4px 0; }

/* Actions */
.cm__actions { margin-top: auto; display: flex; gap: 6px; padding-top: var(--v2-space-3); border-top: 1px solid var(--v2-border-2); }
.cm__act-btn { flex: 1; padding: 8px 0; border-radius: var(--v2-radius-md); font-size: 12px; font-weight: var(--v2-font-semibold); cursor: pointer; border: none; }
.cm__act-btn--expire { background: var(--v2-warning-bg); color: var(--v2-warning-text); } .cm__act-btn--expire:hover { background: var(--v2-warning); color: #fff; }
.cm__act-btn--disable { background: var(--v2-error-bg); color: var(--v2-error-text); } .cm__act-btn--disable:hover { background: var(--v2-error); color: #fff; }

.cm__mono { font-family: var(--v2-font-mono); font-size: 10px; color: var(--v2-text-3); }
.cm__muted { font-size: 12px; color: var(--v2-text-4); }
.cm__nil { padding: var(--v2-space-8); text-align: center; font-size: 12px; color: var(--v2-text-4); }

@media (max-width: 1200px) { .cm__split { grid-template-columns: 1fr; } }
</style>
