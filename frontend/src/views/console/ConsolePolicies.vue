<template>
  <div class="cpo">
    <div class="cpo__toolbar">
      <div class="cpo__tb-left">
        <h2 class="cpo__title">安全策略与护栏</h2>
        <div class="cpo__view-toggle">
          <button class="cpo__vt-btn" :class="{ 'cpo__vt-btn--active': viewMode === 'list' }" @click="viewMode = 'list'">策略列表</button>
          <button class="cpo__vt-btn" :class="{ 'cpo__vt-btn--active': viewMode === 'matrix' }" @click="viewMode = 'matrix'">Agent×Tool 矩阵</button>
        </div>
      </div>
      <template v-if="viewMode === 'list'">
        <div class="cpo__tb-filters">
          <V2Select v-model="filterType" :options="[{label:'输入护栏',value:'input_guard'},{label:'输出护栏',value:'output_guard'},{label:'路由护栏',value:'route_guard'},{label:'工具护栏',value:'tool_guard'}]" placeholder="类型" clearable size="sm" style="width:130px" @update:model-value="loadPolicies" />
          <V2Select v-model="filterStatus" :options="[{label:'草稿',value:'draft'},{label:'已激活',value:'active'}]" placeholder="状态" clearable size="sm" style="width:100px" @update:model-value="loadPolicies" />
          <V2Button variant="primary" size="sm" @click="loadPolicies">查询</V2Button>
        </div>
        <V2Button variant="primary" size="sm" @click="showCreate = true">新建</V2Button>
      </template>
    </div>

    <!-- ── Matrix View ──────────────────────────────────── -->
    <div v-if="viewMode === 'matrix'" class="cpo__matrix-wrap">
      <div class="cpo__matrix-header">
        <div class="cpo__matrix-desc">Agent × Tool/Service 准入矩阵 — 定义每个 Agent 允许调用的 Tool/Service 范围</div>
        <div class="cpo__matrix-legend">
          <span class="cpo__legend-item"><span class="cpo__cell cpo__cell--allow">✓</span> 允许调用</span>
          <span class="cpo__legend-item"><span class="cpo__cell cpo__cell--deny">✕</span> 禁止调用</span>
        </div>
      </div>
      <div class="cpo__matrix-scroll">
        <table class="cpo__mtx">
          <thead>
            <tr>
              <th class="cpo__mtx-corner">Agent \ Tool</th>
              <th v-for="tool in matrixData.tools" :key="tool" class="cpo__mtx-th">
                <span class="cpo__mtx-th-text">{{ tool }}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="agent in matrixData.agents" :key="agent">
              <td class="cpo__mtx-agent">{{ agent }}</td>
              <td v-for="(tool, ti) in matrixData.tools" :key="tool" class="cpo__mtx-cell" :class="matrixData.matrix[agent]?.[ti] ? 'cpo__mtx-cell--allow' : 'cpo__mtx-cell--deny'">
                {{ matrixData.matrix[agent]?.[ti] ? '✓' : '✕' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="cpo__matrix-footer">
        <div class="cpo__matrix-stats">
          <span v-for="agent in matrixData.agents" :key="agent" class="cpo__agent-stat">
            <strong>{{ agent.replace('Agent', '') }}</strong>: {{ matrixData.matrix[agent]?.filter(v => v === 1).length || 0 }}/{{ matrixData.tools.length }} tools
          </span>
        </div>
      </div>
    </div>

    <!-- ── Policy List View ────────────────────────────────── -->
    <div v-if="viewMode === 'list'" class="cpo__split">
      <!-- List -->
      <div class="cpo__list">
        <div v-for="p in filtered" :key="p.policy_id" class="cpo__item" :class="{ 'cpo__item--active': sel?.policy_id === p.policy_id, 'cpo__item--on': p.status === 'active' }" @click="viewDetail(p)">
          <div class="cpo__item-top">
            <span class="cpo__item-name">{{ p.name }}</span>
            <span class="cpo__st" :class="'cpo__st--' + p.status">{{ statusLabel(p.status) }}</span>
          </div>
          <div class="cpo__item-sub">
            <span class="cpo__type-chip">{{ typeLabel(p.policy_type) }}</span>
            <span>v{{ p.version }}</span>
            <span>{{ fmtTime(p.updated_at) }}</span>
          </div>
        </div>
        <div v-if="!filtered.length" class="cpo__nil">暂无策略记录</div>
      </div>

      <!-- Detail -->
      <div class="cpo__detail" v-if="sel">
        <div class="cpo__dh">
          <div>
            <div class="cpo__dh-name">{{ sel.name }}</div>
            <div class="cpo__dh-meta"><span class="cpo__mono">{{ sel.policy_id }}</span> · {{ sel.policy_type }} · v{{ sel.version }}</div>
          </div>
          <div class="cpo__dh-actions">
            <span class="cpo__active-indicator" :class="{ 'cpo__active-indicator--on': sel.status === 'active' }">{{ sel.status === 'active' ? '● 已激活' : '○ 草稿' }}</span>
            <button v-if="sel.status === 'draft'" class="cpo__activate-btn" @click="doActivate(sel.policy_id)">激活</button>
          </div>
        </div>

        <div class="cpo__meta-strip">
          <div class="cpo__mc"><span class="cpo__mc-k">类型</span><span class="cpo__type-chip">{{ typeLabel(sel.policy_type) }}</span></div>
          <div class="cpo__mc"><span class="cpo__mc-k">版本</span>v{{ sel.version }}</div>
          <div class="cpo__mc"><span class="cpo__mc-k">作者</span>{{ sel.created_by || '-' }}</div>
        </div>

        <!-- Rules display — structured -->
        <div class="cpo__sec">
          <div class="cpo__sec-label">规则配置</div>
          <div class="cpo__rules">
            <div v-for="(val, key) in parsedRules" :key="key" class="cpo__rule">
              <span class="cpo__rule-k">{{ key }}</span>
              <div class="cpo__rule-v">
                <template v-if="Array.isArray(val)">
                  <span v-for="(item, i) in val" :key="i" class="cpo__rule-tag">{{ item }}</span>
                </template>
                <span v-else>{{ typeof val === 'object' ? JSON.stringify(val) : val }}</span>
              </div>
            </div>
            <div v-if="!Object.keys(parsedRules).length" class="cpo__muted">暂无规则配置</div>
          </div>
        </div>

        <!-- Activation history -->
        <div class="cpo__sec">
          <div class="cpo__sec-label">变更记录</div>
          <div class="cpo__hist">
            <div class="cpo__hist-item" v-if="sel.status === 'active'">
              <span class="cpo__hist-dot cpo__hist-dot--on" />
              <span>已激活 · v{{ sel.version }} · {{ fmtTime(sel.updated_at) }}</span>
            </div>
            <div class="cpo__hist-item">
              <span class="cpo__hist-dot" />
              <span>已创建 · v1 · {{ fmtTime(sel.created_at || sel.updated_at) }}</span>
            </div>
          </div>
        </div>
      </div>
      <div class="cpo__detail cpo__detail--empty" v-else><span class="cpo__muted">← 选择一个策略</span></div>
    </div>

    <V2Drawer v-model="showCreate" title="新建策略" size="md">
      <div class="cpo__form">
        <label class="cpo__form-label">名称</label>
        <V2Input v-model="form.name" placeholder="如 fraud_input_guard" size="sm" />
        <label class="cpo__form-label">类型</label>
        <V2Select v-model="form.policy_type" :options="[{label:'输入护栏',value:'input_guard'},{label:'输出护栏',value:'output_guard'},{label:'路由护栏',value:'route_guard'},{label:'工具护栏',value:'tool_guard'}]" size="sm" />
        <label class="cpo__form-label">规则 JSON</label>
        <textarea class="cpo__textarea" v-model="form.rules_json" rows="5" placeholder='{"blocked_keywords":["xxx"]}'></textarea>
      </div>
      <template #footer>
        <V2Button variant="ghost" size="sm" @click="showCreate = false">取消</V2Button>
        <V2Button variant="primary" size="sm" @click="doCreate">创建</V2Button>
      </template>
    </V2Drawer>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { adminApi } from '@/api/admin/index'
import V2Select from '@/components/v2/V2Select.vue'
import V2Button from '@/components/v2/V2Button.vue'
import V2Input from '@/components/v2/V2Input.vue'
import V2Drawer from '@/components/v2/V2Drawer.vue'
import matrixJson from '@/mock/policy-matrix.json'

const viewMode = ref('list')
const loading = ref(false), policies = ref([]), sel = ref(null), showCreate = ref(false), filterType = ref(''), filterStatus = ref('')
const matrixData = reactive({ agents: matrixJson.agents, tools: matrixJson.tools, matrix: matrixJson.matrix })
const form = ref({ name: '', policy_type: 'input_guard', rules_json: '{}' })

const STATUS_LABELS = { draft: '草稿', active: '已激活', archived: '已归档' }
function statusLabel(s) { return STATUS_LABELS[s] || s }

const TYPE_LABELS = { input_guard: '输入护栏', output_guard: '输出护栏', route_guard: '路由护栏', tool_guard: '工具护栏' }
function typeLabel(t) { return TYPE_LABELS[t] || t }

function fmtTime(v) {
  if (!v) return ''
  const d = new Date(v); if (isNaN(d)) return String(v).slice(0, 16)
  const M = String(d.getMonth() + 1).padStart(2, '0'), D = String(d.getDate()).padStart(2, '0')
  const hh = String(d.getHours()).padStart(2, '0'), mm = String(d.getMinutes()).padStart(2, '0')
  return `${M}-${D} ${hh}:${mm}`
}

const filtered = computed(() => policies.value)

const parsedRules = computed(() => {
  const r = sel.value?.rules_json ?? sel.value?.rules; if (!r) return {}
  try { return typeof r === 'string' ? JSON.parse(r) : r } catch { return {} }
})

async function viewDetail(row) {
  try { const d = await adminApi.getPolicy(row.policy_id); sel.value = { ...row, ...(d ?? {}) } }
  catch { sel.value = row }
}

async function loadPolicies() {
  loading.value = true
  try {
    const p = {}
    if (filterType.value) p.policy_type = filterType.value
    if (filterStatus.value) p.status = filterStatus.value
    policies.value = (await adminApi.getPolicies(p))?.items ?? []
  } catch (e) {
    console.warn('[Policies]', e)
    console.warn('[Policies] load failed')
  } finally { loading.value = false }
}

async function doCreate() {
  if (!form.value.name?.trim()) { alert('请填写名称'); return }
  let rules
  try { rules = JSON.parse(form.value.rules_json || '{}') } catch { alert('规则 JSON 格式不正确'); return }
  try {
    await adminApi.createPolicy({ name: form.value.name.trim(), policy_type: form.value.policy_type, rules })
    showCreate.value = false
    form.value = { name: '', policy_type: 'input_guard', rules_json: '{}' }
    loadPolicies()
  } catch (e) { console.warn('[Policies] create failed', e) }
}

async function doActivate(id) {
  try {
    await adminApi.activatePolicy(id, {})
    loadPolicies()
    if (sel.value?.policy_id === id) viewDetail(sel.value)
  } catch (e) { console.warn('[Policies] activate failed', e) }
}

onMounted(loadPolicies)
</script>

<style scoped>
.cpo__toolbar { display: flex; align-items: center; gap: var(--v2-space-3); padding: var(--v2-space-2) var(--v2-space-3); margin-bottom: var(--v2-space-3); background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-lg); flex-wrap: wrap; }
.cpo__tb-left { display: flex; align-items: center; gap: var(--v2-space-2); margin-right: auto; }
.cpo__title { font-size: var(--v2-text-md); font-weight: var(--v2-font-semibold); color: var(--v2-text-1); margin: 0; }
.cpo__count { font-size: var(--v2-text-xs); padding: 0 5px; background: var(--v2-bg-sunken); color: var(--v2-text-3); border-radius: var(--v2-radius-sm); }
.cpo__tb-filters { display: flex; align-items: center; gap: 6px; }

.cpo__split { display: grid; grid-template-columns: 360px 1fr; gap: var(--v2-space-3); min-height: calc(100vh - 180px); }

.cpo__list { background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-lg); overflow-y: auto; }
.cpo__item { padding: var(--v2-space-3); border-bottom: 1px solid var(--v2-border-1); cursor: pointer; transition: background var(--v2-trans-fast); }
.cpo__item:hover { background: var(--v2-bg-sunken); }
.cpo__item--active { background: var(--v2-brand-bg); border-left: 3px solid var(--v2-brand-primary); }
.cpo__item--on { border-left: 3px solid var(--v2-success); }
.cpo__item--active.cpo__item--on { border-left-color: var(--v2-brand-primary); }
.cpo__item-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 2px; }
.cpo__item-name { font-size: 12px; font-weight: var(--v2-font-medium); color: var(--v2-text-1); }
.cpo__item-sub { font-size: 10px; color: var(--v2-text-4); display: flex; gap: var(--v2-space-3); align-items: center; }

.cpo__st { font-size: 10px; font-weight: var(--v2-font-medium); padding: 1px 5px; border-radius: 3px; }
.cpo__st--active { background: var(--v2-success-bg); color: var(--v2-success-text); }
.cpo__st--draft { background: var(--v2-warning-bg); color: var(--v2-warning-text); }

.cpo__type-chip { font-size: 9px; padding: 0 5px; background: var(--v2-ai-purple-bg); color: var(--v2-ai-purple); border-radius: 3px; font-weight: var(--v2-font-medium); }

.cpo__detail { background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-lg); padding: var(--v2-space-4); overflow-y: auto; display: flex; flex-direction: column; gap: var(--v2-space-3); }
.cpo__detail--empty { align-items: center; justify-content: center; }

.cpo__dh { display: flex; justify-content: space-between; align-items: flex-start; padding-bottom: var(--v2-space-3); border-bottom: 1px solid var(--v2-border-2); }
.cpo__dh-name { font-size: var(--v2-text-md); font-weight: var(--v2-font-semibold); color: var(--v2-text-1); }
.cpo__dh-meta { font-size: 10px; color: var(--v2-text-4); margin-top: 2px; }
.cpo__dh-actions { display: flex; align-items: center; gap: var(--v2-space-2); }
.cpo__active-indicator { font-size: 11px; font-weight: var(--v2-font-medium); color: var(--v2-text-4); }
.cpo__active-indicator--on { color: var(--v2-success); }
.cpo__activate-btn { padding: 4px 12px; background: var(--v2-success-bg); color: var(--v2-success-text); border: 1px solid rgba(34,197,94,.2); border-radius: var(--v2-radius-md); font-size: 11px; font-weight: var(--v2-font-semibold); cursor: pointer; } .cpo__activate-btn:hover { background: var(--v2-success); color: #fff; }

.cpo__meta-strip { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
.cpo__mc { padding: 6px 8px; background: var(--v2-bg-sunken); border-radius: var(--v2-radius-md); font-size: 12px; color: var(--v2-text-1); }
.cpo__mc-k { display: block; font-size: 9px; color: var(--v2-text-4); text-transform: uppercase; letter-spacing: .3px; }

.cpo__sec { } .cpo__sec-label { font-size: 10px; font-weight: var(--v2-font-semibold); color: var(--v2-text-4); text-transform: uppercase; letter-spacing: .5px; margin-bottom: 4px; }

/* Structured rules */
.cpo__rules { display: flex; flex-direction: column; gap: 6px; }
.cpo__rule { padding: 8px 10px; background: var(--v2-bg-sunken); border-radius: var(--v2-radius-md); }
.cpo__rule-k { display: block; font-size: 9px; color: var(--v2-text-4); text-transform: uppercase; letter-spacing: .3px; margin-bottom: 3px; font-weight: var(--v2-font-semibold); }
.cpo__rule-v { font-size: 11px; color: var(--v2-text-1); display: flex; flex-wrap: wrap; gap: 3px; }
.cpo__rule-tag { font-size: 10px; padding: 1px 6px; background: var(--v2-error-bg); color: var(--v2-error-text); border-radius: 3px; }

/* Activation history */
.cpo__hist { display: flex; flex-direction: column; gap: 6px; }
.cpo__hist-item { display: flex; align-items: center; gap: 8px; font-size: 11px; color: var(--v2-text-2); }
.cpo__hist-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--v2-gray-300); flex-shrink: 0; }
.cpo__hist-dot--on { background: var(--v2-success); box-shadow: 0 0 0 2px var(--v2-success-bg); }

.cpo__form { display: flex; flex-direction: column; gap: 10px; }
.cpo__form-label { font-size: var(--v2-text-xs); font-weight: var(--v2-font-semibold); color: var(--v2-text-3); text-transform: uppercase; letter-spacing: .4px; }
.cpo__textarea { width: 100%; padding: 8px 10px; font-size: var(--v2-text-sm); border: 1px solid var(--v2-border-1); border-radius: var(--v2-radius-md); background: var(--v2-bg-card); color: var(--v2-text-1); resize: vertical; font-family: var(--v2-font-mono); }
.cpo__textarea:focus { outline: none; border-color: var(--v2-brand-primary); box-shadow: 0 0 0 2px color-mix(in srgb, var(--v2-brand-primary) 15%, transparent); }

.cpo__mono { font-family: var(--v2-font-mono); font-size: 10px; color: var(--v2-text-3); }
.cpo__muted { font-size: 11px; color: var(--v2-text-4); }
.cpo__nil { padding: var(--v2-space-8); text-align: center; font-size: 12px; color: var(--v2-text-4); }

/* View toggle */
.cpo__view-toggle { display: flex; gap: 2px; background: var(--v2-bg-sunken); border-radius: var(--v2-radius-md); padding: 2px; margin-left: var(--v2-space-3); }
.cpo__vt-btn { padding: 3px 12px; border: none; background: transparent; color: var(--v2-text-3); font-size: var(--v2-text-xs); border-radius: var(--v2-radius-sm); cursor: pointer; transition: all var(--v2-trans-fast); font-weight: var(--v2-font-medium); }
.cpo__vt-btn:hover { color: var(--v2-text-1); }
.cpo__vt-btn--active { background: var(--v2-bg-card); color: var(--v2-text-1); box-shadow: 0 1px 2px rgba(0,0,0,.06); }

/* Matrix view */
.cpo__matrix-wrap { background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-lg); overflow: hidden; }
.cpo__matrix-header { padding: var(--v2-space-4); border-bottom: 1px solid var(--v2-border-2); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: var(--v2-space-2); }
.cpo__matrix-desc { font-size: var(--v2-text-sm); color: var(--v2-text-2); }
.cpo__matrix-legend { display: flex; gap: var(--v2-space-4); }
.cpo__legend-item { display: flex; align-items: center; gap: 4px; font-size: var(--v2-text-xs); color: var(--v2-text-3); }
.cpo__cell { display: inline-flex; align-items: center; justify-content: center; width: 20px; height: 20px; border-radius: 3px; font-size: 10px; font-weight: var(--v2-font-bold); }
.cpo__cell--allow { background: var(--v2-success-bg); color: var(--v2-success-text); }
.cpo__cell--deny { background: var(--v2-bg-sunken); color: var(--v2-text-4); }
.cpo__matrix-scroll { overflow-x: auto; }
.cpo__mtx { width: 100%; border-collapse: collapse; font-size: 11px; }
.cpo__mtx-corner { position: sticky; left: 0; z-index: 2; background: var(--v2-bg-sunken); padding: 8px 12px; font-size: 9px; font-weight: var(--v2-font-semibold); color: var(--v2-text-4); text-transform: uppercase; letter-spacing: .4px; text-align: left; border-bottom: 1px solid var(--v2-border-2); border-right: 1px solid var(--v2-border-2); min-width: 180px; }
.cpo__mtx-th { padding: 6px 4px; background: var(--v2-bg-sunken); border-bottom: 1px solid var(--v2-border-2); border-right: 1px solid var(--v2-border-1); text-align: center; min-width: 60px; }
.cpo__mtx-th-text { display: block; font-size: 9px; font-weight: var(--v2-font-semibold); color: var(--v2-text-3); writing-mode: vertical-lr; text-orientation: mixed; white-space: nowrap; transform: rotate(180deg); height: 110px; line-height: 1.3; }
.cpo__mtx-agent { position: sticky; left: 0; z-index: 1; background: var(--v2-bg-card); padding: 8px 12px; font-size: 11px; font-weight: var(--v2-font-medium); color: var(--v2-text-1); border-bottom: 1px solid var(--v2-border-1); border-right: 1px solid var(--v2-border-2); white-space: nowrap; }
.cpo__mtx-cell { text-align: center; padding: 6px 4px; border-bottom: 1px solid var(--v2-border-1); border-right: 1px solid var(--v2-border-1); font-weight: var(--v2-font-bold); font-size: 12px; transition: background var(--v2-trans-fast); }
.cpo__mtx-cell--allow { color: var(--v2-success); background: rgba(34,197,94,.06); }
.cpo__mtx-cell--deny { color: var(--v2-text-4); }
.cpo__mtx-cell:hover { background: var(--v2-brand-bg); }
.cpo__matrix-footer { padding: var(--v2-space-3) var(--v2-space-4); border-top: 1px solid var(--v2-border-2); background: var(--v2-bg-sunken); }
.cpo__matrix-stats { display: flex; flex-wrap: wrap; gap: var(--v2-space-4); font-size: var(--v2-text-xs); color: var(--v2-text-2); }
.cpo__agent-stat strong { color: var(--v2-text-1); }

@media (max-width: 1200px) { .cpo__split { grid-template-columns: 1fr; } }
</style>
