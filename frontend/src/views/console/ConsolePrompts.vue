<template>
  <div class="cp">
    <header class="cp-hd">
      <div class="cp-hd__left">
        <h2 class="cp__title">提示词工坊</h2>
        <span class="cp__sub">版本控制与差异分析</span>
      </div>
      <V2Button variant="primary" size="sm" @click="createPrompt">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
        创建提示词
      </V2Button>
    </header>

    <div class="cp-layout">
      <!-- ── Left: Prompt List ── -->
      <div class="cp-sidebar">
        <div class="cp-sidebar__hd">
          <div class="cp-search">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
            <input type="text" class="cp-search__input" placeholder="搜索提示词… ( / )" v-model="searchQuery" />
          </div>
        </div>
        <div class="cp-list">
          <div v-if="loading" class="cp-list-loading"><span class="cp__spinner" /></div>
          <div
            v-else
            v-for="p in filteredPrompts" :key="p.id"
            class="cp-item"
            :class="{ 'cp-item--active': selectedPrompt?.id === p.id }"
            @click="selectPrompt(p)"
          >
            <div class="cp-item__hd">
              <span class="cp-name">{{ p.agent_name }} / {{ p.name }}</span>
              <V2Badge :variant="p.status === 'active' ? 'success' : 'neutral'" :label="'v' + p.version.toFixed(1)" />
            </div>
            <div class="cp-item__desc">{{ p.description }}</div>
          </div>
          <div v-if="!loading && !filteredPrompts.length" class="cp-list-empty">无匹配提示词</div>
        </div>
      </div>

      <!-- ── Right: Prompt Editor & Diff Viewer ── -->
      <div class="cp-editor" v-if="selectedPrompt">
        <div class="cp-editor__hd">
          <div class="cp-editor__info">
            <span class="cp-editor__id">{{ selectedPrompt.id?.substring(0, 8) }}</span>
            <span class="cp-editor__name">{{ selectedPrompt.name }}</span>
          </div>
          <V2Segment v-model="viewMode" :options="VIEW_OPTS" size="sm" />
        </div>

        <!-- Mode: Editor -->
        <div class="cp-editor__bd" v-if="viewMode === 'edit'">
          <div class="cp-field">
            <label class="cp-field__label">系统指令</label>
            <textarea class="cp-textarea" v-model="editTemplate" spellcheck="false"></textarea>
          </div>

          <div class="cp-field">
            <label class="cp-field__label">变量（自动检测）</label>
            <div class="cp-vars">
              <span class="cp-var" v-for="v in detectedVariables" :key="v" v-text="wrapVar(v)"></span>
              <span v-if="!detectedVariables.length" class="cp-vars-empty">未检测到变量</span>
            </div>
          </div>
        </div>

        <!-- Mode: Diff Viewer -->
        <div class="cp-editor__bd" v-if="viewMode === 'diff'">
          <div class="cp-diff-header">
            <span class="cp-diff-label">对比:</span>
            <V2Badge variant="neutral" :label="'v' + (selectedPrompt.version - 1).toFixed(1)" />
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
            <V2Badge variant="success" :label="'v' + selectedPrompt.version.toFixed(1)" />
          </div>

          <div class="cp-diff-viewer">
            <div v-for="(line, idx) in diffLines" :key="idx" class="diff-line" :class="'diff-line--' + line.type">
              <div class="diff-num">{{ idx + 1 }}</div>
              <div class="diff-content" v-html="line.content"></div>
            </div>
          </div>
          <div class="cp-diff-note">*Char-level diff engine</div>
        </div>

        <!-- Footer Actions -->
        <div class="cp-editor__ft">
          <V2Button variant="ghost" size="sm">取消</V2Button>
          <V2Button variant="primary" size="sm">提交 v{{ (selectedPrompt.version + 1).toFixed(1) }}</V2Button>
        </div>
      </div>

      <!-- Empty State -->
      <div class="cp-editor cp-editor--empty" v-else>
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" stroke-linecap="round" class="cp-empty-icon"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6"/><path d="M16 13H8"/><path d="M16 17H8"/><path d="M10 9H8"/></svg>
        <span class="cp-empty-text">选择一个提示词进行编辑</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { adminApi } from '@/api/admin/index'
import V2Button from '@/components/v2/V2Button.vue'
import V2Badge from '@/components/v2/V2Badge.vue'
import V2Segment from '@/components/v2/V2Segment.vue'

const VIEW_OPTS = [
  { label: '编辑器', value: 'edit' },
  { label: '差异历史', value: 'diff' },
]

const loading = ref(false)
const prompts = ref([])
const searchQuery = ref('')
const selectedPrompt = ref(null)
const viewMode = ref('edit')
const editTemplate = ref('')

const filteredPrompts = computed(() => {
  if (!searchQuery.value) return prompts.value
  const q = searchQuery.value.toLowerCase()
  return prompts.value.filter(p => p.name.toLowerCase().includes(q) || (p.agent_name || '').toLowerCase().includes(q))
})

const detectedVariables = computed(() => {
  if (!editTemplate.value) return []
  const matches = editTemplate.value.match(/\{\{([^}]+)\}\}/g)
  if (!matches) return []
  return [...new Set(matches.map(m => m.replace(/\{|\}/g, '').trim()))]
})

function wrapVar(v) { return `{{${v}}}` }

function selectPrompt(p) {
  selectedPrompt.value = p
  editTemplate.value = p.template || ''
  viewMode.value = 'edit'
}

function createPrompt() {
  const newP = { id: crypto.randomUUID(), agent_name: 'new_agent', name: 'Untitled', version: 1.0, status: 'draft', description: '新提示词', template: '' }
  prompts.value.unshift(newP)
  selectPrompt(newP)
}

const diffLines = computed(() => {
  return [
    { type: 'normal', content: 'You are an expert fraud detection agent.' },
    { type: 'removed', content: '<span class="del">Analyze the transaction and return a score.</span>' },
    { type: 'added', content: '<span class="add">Analyze the transaction, considering <span class="add-char">IP velocity</span>, and return a score.</span>' },
    { type: 'normal', content: 'Transaction Data: {{payload}}' },
    { type: 'added', content: '<span class="add">User History: {{user_history}}</span>' },
  ]
})

async function loadPrompts() {
  loading.value = true
  try {
    const data = await adminApi.getPrompts({ limit: 100, offset: 0 })
    const items = data?.items ?? data ?? []
    if (Array.isArray(items) && items.length) {
      prompts.value = items
    } else {
      // Fallback mock data for demo
      prompts.value = [
        { id: 'p-1', agent_name: 'fraud_agent', name: 'Transaction Scoring', version: 2.0, status: 'active', description: 'Core fraud evaluation prompt', template: 'You are an expert fraud detection agent.\nAnalyze the transaction, considering IP velocity, and return a score.\nTransaction Data: {{payload}}\nUser History: {{user_history}}' },
        { id: 'p-2', agent_name: 'customer_agent', name: 'RFM Summary', version: 1.0, status: 'active', description: 'Summarize customer RFM clusters', template: 'Summarize the following customer segments: {{rfm_data}}' },
        { id: 'p-3', agent_name: 'forecast_agent', name: 'Anomaly Detection', version: 3.1, status: 'draft', description: 'Detect sales anomalies', template: 'Identify anomalies in this time series: {{time_series}}' },
      ]
    }
    if (prompts.value.length) selectPrompt(prompts.value[0])
  } catch (e) {
    console.warn('[Prompts]', e)
    prompts.value = [
      { id: 'p-1', agent_name: 'fraud_agent', name: 'Transaction Scoring', version: 2.0, status: 'active', description: 'Core fraud evaluation prompt', template: 'You are an expert fraud detection agent.\nAnalyze the transaction, considering IP velocity, and return a score.\nTransaction Data: {{payload}}\nUser History: {{user_history}}' },
      { id: 'p-2', agent_name: 'customer_agent', name: 'RFM Summary', version: 1.0, status: 'active', description: 'Summarize customer RFM clusters', template: 'Summarize the following customer segments: {{rfm_data}}' },
      { id: 'p-3', agent_name: 'forecast_agent', name: 'Anomaly Detection', version: 3.1, status: 'draft', description: 'Detect sales anomalies', template: 'Identify anomalies in this time series: {{time_series}}' },
    ]
    if (prompts.value.length) selectPrompt(prompts.value[0])
  } finally {
    loading.value = false
  }
}

onMounted(loadPrompts)
</script>

<style scoped>
.cp {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 120px);
  gap: var(--v2-space-4);
}

/* ── Header ── */
.cp-hd {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-shrink: 0;
}
.cp-hd__left { display: flex; align-items: baseline; gap: var(--v2-space-2); }
.cp__title { font-size: var(--v2-text-lg); font-weight: var(--v2-font-semibold); color: var(--v2-text-1); margin: 0; }
.cp__sub { font-size: var(--v2-text-xs); color: var(--v2-text-4); }

/* ── Layout ── */
.cp-layout {
  flex: 1;
  display: grid;
  grid-template-columns: 300px 1fr;
  gap: var(--v2-space-3);
  min-height: 0;
}

/* ── Sidebar ── */
.cp-sidebar {
  display: flex;
  flex-direction: column;
  background: var(--v2-bg-card);
  border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-lg);
  overflow: hidden;
}
.cp-sidebar__hd {
  padding: 10px;
  border-bottom: var(--v2-border-width) solid var(--v2-border-1);
}
.cp-search {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 10px;
  height: 28px;
  background: var(--v2-bg-sunken);
  border-radius: var(--v2-radius-btn);
  color: var(--v2-text-4);
}
.cp-search__input {
  flex: 1;
  border: none;
  background: transparent;
  color: var(--v2-text-1);
  font-size: var(--v2-text-xs);
  font-family: var(--v2-font-sans);
  outline: none;
}
.cp-search__input::placeholder { color: var(--v2-text-4); }

.cp-list { flex: 1; overflow-y: auto; padding: 6px; }
.cp-list-loading { display: flex; align-items: center; justify-content: center; padding: var(--v2-space-8) 0; }
.cp-list-empty { text-align: center; padding: var(--v2-space-6) 0; color: var(--v2-text-4); font-size: var(--v2-text-sm); }
.cp__spinner {
  width: 18px; height: 18px;
  border: 2px solid var(--v2-border-2);
  border-top-color: var(--v2-text-3);
  border-radius: 50%;
  animation: cp-spin .6s linear infinite;
}
@keyframes cp-spin { from{transform:rotate(0)} to{transform:rotate(360deg)} }

.cp-item {
  padding: 10px 12px;
  border-radius: var(--v2-radius-md);
  cursor: pointer;
  margin-bottom: 2px;
  transition: background var(--v2-trans-fast);
}
.cp-item:hover { background: var(--v2-bg-hover); }
.cp-item--active { background: var(--v2-bg-sunken); }
.cp-item__hd {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 3px;
}
.cp-name {
  font-size: 12px;
  font-weight: var(--v2-font-semibold);
  color: var(--v2-text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 180px;
}
.cp-item__desc {
  font-size: 11px;
  color: var(--v2-text-4);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── Editor ── */
.cp-editor {
  display: flex;
  flex-direction: column;
  background: var(--v2-bg-card);
  border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-lg);
  overflow: hidden;
}
.cp-editor--empty {
  align-items: center;
  justify-content: center;
  gap: 12px;
}
.cp-empty-icon { color: var(--v2-text-4); }
.cp-empty-text { font-size: var(--v2-text-sm); color: var(--v2-text-4); }

.cp-editor__hd {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--v2-space-3) var(--v2-space-4);
  border-bottom: var(--v2-border-width) solid var(--v2-border-1);
}
.cp-editor__info { display: flex; align-items: baseline; gap: var(--v2-space-2); }
.cp-editor__id { font-family: var(--v2-font-mono); font-size: 10px; color: var(--v2-text-4); }
.cp-editor__name { font-size: var(--v2-text-md); font-weight: var(--v2-font-semibold); color: var(--v2-text-1); }

.cp-editor__bd {
  flex: 1;
  overflow-y: auto;
  padding: var(--v2-space-4);
  display: flex;
  flex-direction: column;
  gap: var(--v2-space-4);
}

.cp-field { display: flex; flex-direction: column; gap: 8px; }
.cp-field__label {
  font-size: 10px;
  font-weight: var(--v2-font-semibold);
  color: var(--v2-text-4);
  text-transform: uppercase;
  letter-spacing: .05em;
}

.cp-textarea {
  width: 100%;
  height: 280px;
  padding: 14px;
  background: var(--v2-bg-sunken);
  border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-md);
  color: var(--v2-text-1);
  font-family: var(--v2-font-mono);
  font-size: 13px;
  line-height: 1.6;
  resize: vertical;
  outline: none;
  transition: border-color var(--v2-trans-fast);
}
.cp-textarea:focus { border-color: var(--v2-text-3); }

/* Variables */
.cp-vars { display: flex; flex-wrap: wrap; gap: 6px; }
.cp-var {
  padding: 3px 8px;
  background: var(--v2-bg-sunken);
  color: var(--v2-text-2);
  border-radius: var(--v2-radius-sm);
  font-family: var(--v2-font-mono);
  font-size: 11px;
}
.cp-vars-empty { font-size: 11px; color: var(--v2-text-4); }

/* Diff */
.cp-diff-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--v2-bg-sunken);
  border-radius: var(--v2-radius-md);
  margin-bottom: var(--v2-space-3);
}
.cp-diff-label { font-size: 10px; color: var(--v2-text-4); font-weight: var(--v2-font-semibold); text-transform: uppercase; }

.cp-diff-viewer {
  border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-md);
  overflow: hidden;
  font-family: var(--v2-font-mono);
  font-size: 12px;
  line-height: 1.6;
}
.diff-line { display: flex; }
.diff-num {
  width: 36px;
  flex-shrink: 0;
  text-align: right;
  padding: 3px 6px;
  color: var(--v2-text-4);
  border-right: var(--v2-border-width) solid var(--v2-border-1);
  user-select: none;
  font-size: 10px;
}
.diff-content {
  padding: 3px 12px;
  flex: 1;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--v2-text-1);
}

.diff-line--added { background: rgba(34,197,94,0.08); }
.diff-line--added .diff-num { color: var(--v2-success); }
.diff-line--removed { background: rgba(239,68,68,0.08); }
.diff-line--removed .diff-num { color: var(--v2-error); }
.diff-line--removed .diff-content { color: var(--v2-text-3); text-decoration: line-through; }

:deep(.add) { background: rgba(34,197,94,0.15); }
:deep(.del) { background: rgba(239,68,68,0.15); }
:deep(.add-char) { background: rgba(34,197,94,0.3); font-weight: 600; }

.cp-diff-note { font-size: 10px; color: var(--v2-text-4); text-align: right; margin-top: 8px; }

.cp-editor__ft {
  padding: var(--v2-space-3) var(--v2-space-4);
  border-top: var(--v2-border-width) solid var(--v2-border-1);
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

/* ── Responsive ── */
@media (max-width: 1200px) {
  .cp-layout { grid-template-columns: 1fr; }
}
</style>
