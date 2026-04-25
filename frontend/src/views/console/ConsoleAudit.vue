<template>
  <div class="ca">
    <!-- Toolbar -->
    <div class="ca__toolbar">
      <div class="ca__tb-left"><h2 class="ca__title">审计事件流</h2><span class="ca__count">{{ logs.length }}</span></div>
      <div class="ca__tb-filters">
        <V2Input v-model="filter.operator" placeholder="操作人" clearable size="sm" style="width:110px" @clear="loadAudit" />
        <V2Input v-model="filter.action" placeholder="操作类型" clearable size="sm" style="width:130px" @clear="loadAudit" />
        <V2Input v-model="filter.target_type" placeholder="对象类型" clearable size="sm" style="width:110px" @clear="loadAudit" />
        <V2Button variant="primary" size="sm" @click="loadAudit">查询</V2Button>
        <V2Button variant="ghost" size="sm" @click="filter.operator=''; filter.action=''; filter.target_type=''; loadAudit()">清空</V2Button>
      </div>
      <V2Button variant="ghost" size="sm" :loading="loading" @click="loadAudit">刷新</V2Button>
    </div>

    <div class="ca__split">
      <!-- Left: event stream -->
      <div class="ca__stream">
        <div v-for="log in logs" :key="log.id" class="ca__evt" :class="{ 'ca__evt--active': sel?.id === log.id }" @click="viewDetail(log)">
          <div class="ca__evt-dot" />
          <div class="ca__evt-body">
            <div class="ca__evt-top">
              <span class="ca__evt-action">{{ actionLabel(log.action) }}</span>
              <span class="ca__evt-time">{{ fmtTime(log.created_at) }}</span>
            </div>
            <div class="ca__evt-sub">
              <span class="ca__evt-op">{{ log.operator }}</span>
              <span>→</span>
              <span class="ca__evt-target">{{ log.target_type }}</span>
              <span class="ca__mono">{{ log.target_id?.slice(0, 12) }}</span>
            </div>
          </div>
        </div>
        <div v-if="!logs.length" class="ca__nil">暂无审计事件</div>
      </div>

      <!-- Right: detail + compare panel -->
      <div class="ca__detail" v-if="sel">
        <!-- Header -->
        <div class="ca__dh">
          <div class="ca__dh-action">{{ actionLabel(sel.action) }}</div>
          <div class="ca__dh-meta">#{{ sel.id }} · {{ sel.operator }} · {{ fmtTime(sel.created_at) }}</div>
        </div>

        <!-- Metadata -->
        <div class="ca__meta">
          <div class="ca__mk"><span>操作人</span><span>{{ sel.operator }}</span></div>
          <div class="ca__mk"><span>操作类型</span><span>{{ actionLabel(sel.action) }}</span></div>
          <div class="ca__mk"><span>对象类型</span><span>{{ targetLabel(sel.target_type) }}</span></div>
          <div class="ca__mk"><span>对象 ID</span><span class="ca__mono">{{ sel.target_id }}</span></div>
          <div class="ca__mk"><span>IP 地址</span><span>{{ sel.ip_address || '-' }}</span></div>
        </div>

        <!-- Compare panel: Before / After -->
        <div v-if="sel.before_json || sel.after_json" class="ca__compare">
          <div class="ca__compare-hd">
            <div class="ca__compare-col ca__compare-col--before">变更前</div>
            <div class="ca__compare-col ca__compare-col--after">变更后</div>
          </div>
          <div class="ca__compare-body">
            <div class="ca__compare-pane ca__compare-pane--before">{{ sel.before_json ? fmtJson(sel.before_json) : '(无)' }}</div>
            <div class="ca__compare-pane ca__compare-pane--after">{{ sel.after_json ? fmtJson(sel.after_json) : '(无)' }}</div>
          </div>
        </div>
        <div v-else class="ca__no-diff">本次操作未记录状态变更</div>
      </div>
      <div class="ca__detail ca__detail--empty" v-else><span class="ca__muted">← 选择一条审计事件查看详情</span></div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { adminApi } from '@/api/admin/index'
import V2Input from '@/components/v2/V2Input.vue'
import V2Button from '@/components/v2/V2Button.vue'

const loading = ref(false), logs = ref([]), sel = ref(null)
const filter = reactive({ operator: '', action: '', target_type: '' })

const ACTION_LABELS = {
  create_policy: '创建策略', activate_policy: '激活策略',
  create_prompt: '创建 Prompt', release_prompt: '发布 Prompt',
  create_release: '创建发布', rollback_release: '回滚发布',
  approve_review: '审批通过', reject_review: '审批拒绝',
  create_faq: '创建 FAQ', disable_faq: '停用 FAQ',
}
function actionLabel(a) { return ACTION_LABELS[a] || a }

const TARGET_LABELS = { policy: '策略', prompt: 'Prompt', release: '发布', review: '审核', faq: 'FAQ', agent: 'Agent' }
function targetLabel(t) { return TARGET_LABELS[t] || t }

function fmtTime(v) {
  if (!v) return ''
  const d = new Date(v); if (isNaN(d)) return String(v).slice(0, 16)
  const M = String(d.getMonth() + 1).padStart(2, '0'), D = String(d.getDate()).padStart(2, '0')
  const hh = String(d.getHours()).padStart(2, '0'), mm = String(d.getMinutes()).padStart(2, '0')
  return `${M}-${D} ${hh}:${mm}`
}

function fmtJson(v) { if (!v) return ''; try { return JSON.stringify(typeof v === 'string' ? JSON.parse(v) : v, null, 2) } catch { return String(v) } }

async function viewDetail(row) {
  try { const d = await adminApi.getAuditLog(row.id); sel.value = { ...row, ...(d ?? {}) } }
  catch { sel.value = row }
}

async function loadAudit() {
  loading.value = true
  try {
    const p = {}
    if (filter.operator) p.operator = filter.operator
    if (filter.action) p.action = filter.action
    if (filter.target_type) p.target_type = filter.target_type
    logs.value = (await adminApi.getAuditLogs(p))?.items ?? []
  } catch (e) {
    console.warn('[Audit]', e)
    console.warn('[Audit] load failed')
  } finally { loading.value = false }
}

onMounted(loadAudit)
</script>

<style scoped>
.ca__toolbar { display: flex; align-items: center; gap: var(--v2-space-3); padding: var(--v2-space-2) var(--v2-space-3); margin-bottom: var(--v2-space-3); background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-lg); flex-wrap: wrap; }
.ca__tb-left { display: flex; align-items: center; gap: var(--v2-space-2); margin-right: auto; }
.ca__title { font-size: var(--v2-text-md); font-weight: var(--v2-font-semibold); color: var(--v2-text-1); margin: 0; }
.ca__count { font-size: var(--v2-text-xs); padding: 0 5px; background: var(--v2-bg-sunken); color: var(--v2-text-3); border-radius: var(--v2-radius-sm); }
.ca__tb-filters { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }

.ca__split { display: grid; grid-template-columns: 400px 1fr; gap: var(--v2-space-3); min-height: calc(100vh - 180px); }

/* Event stream */
.ca__stream { background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-lg); overflow-y: auto; }
.ca__evt { display: flex; gap: 10px; padding: 10px var(--v2-space-3); border-bottom: 1px solid var(--v2-border-1); cursor: pointer; transition: background var(--v2-trans-fast); }
.ca__evt:hover { background: var(--v2-bg-sunken); }
.ca__evt--active { background: var(--v2-brand-bg); border-left: 3px solid var(--v2-brand-primary); }
.ca__evt-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--v2-gray-300); flex-shrink: 0; margin-top: 5px; }
.ca__evt-body { flex: 1; min-width: 0; }
.ca__evt-top { display: flex; justify-content: space-between; align-items: center; }
.ca__evt-action { font-size: 12px; font-weight: var(--v2-font-medium); color: var(--v2-text-1); }
.ca__evt-time { font-size: 10px; color: var(--v2-text-4); }
.ca__evt-sub { font-size: 10px; color: var(--v2-text-4); display: flex; gap: 4px; align-items: center; margin-top: 1px; }
.ca__evt-op { color: var(--v2-text-2); }
.ca__evt-target { color: var(--v2-ai-purple); font-weight: var(--v2-font-medium); }

/* Detail */
.ca__detail { background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-lg); padding: var(--v2-space-4); overflow-y: auto; display: flex; flex-direction: column; gap: var(--v2-space-3); }
.ca__detail--empty { align-items: center; justify-content: center; }

.ca__dh { padding-bottom: var(--v2-space-3); border-bottom: 1px solid var(--v2-border-2); }
.ca__dh-action { font-size: var(--v2-text-md); font-weight: var(--v2-font-semibold); color: var(--v2-text-1); }
.ca__dh-meta { font-size: 10px; color: var(--v2-text-4); margin-top: 2px; }

.ca__meta { display: flex; flex-direction: column; gap: 4px; }
.ca__mk { display: flex; justify-content: space-between; font-size: 11px; padding: 2px 0; }
.ca__mk > span:first-child { color: var(--v2-text-4); } .ca__mk > span:last-child { color: var(--v2-text-1); }

/* Compare panel */
.ca__compare { border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-md); overflow: hidden; flex: 1; display: flex; flex-direction: column; }
.ca__compare-hd { display: grid; grid-template-columns: 1fr 1fr; border-bottom: 1px solid var(--v2-border-2); }
.ca__compare-col { padding: 4px 10px; font-size: 10px; font-weight: var(--v2-font-semibold); text-transform: uppercase; letter-spacing: .4px; }
.ca__compare-col--before { background: var(--v2-error-bg); color: var(--v2-error-text); }
.ca__compare-col--after { background: var(--v2-success-bg); color: var(--v2-success-text); }
.ca__compare-body { display: grid; grid-template-columns: 1fr 1fr; flex: 1; }
.ca__compare-pane { font-family: var(--v2-font-mono); font-size: 10px; padding: 8px 10px; white-space: pre-wrap; word-break: break-all; line-height: 1.5; overflow-y: auto; max-height: 300px; }
.ca__compare-pane--before { background: rgba(239,68,68,.02); color: var(--v2-text-3); border-right: 1px solid var(--v2-border-2); }
.ca__compare-pane--after { background: rgba(34,197,94,.02); color: var(--v2-text-1); }

.ca__no-diff { font-size: 11px; color: var(--v2-text-4); padding: var(--v2-space-4); text-align: center; }
.ca__mono { font-family: var(--v2-font-mono); font-size: 10px; color: var(--v2-text-3); }
.ca__muted { font-size: 12px; color: var(--v2-text-4); }
.ca__nil { padding: var(--v2-space-8); text-align: center; font-size: 12px; color: var(--v2-text-4); }

@media (max-width: 1200px) { .ca__split { grid-template-columns: 1fr; } }
</style>
