<template>
  <div class="crl">
    <div class="crl__toolbar">
      <div class="crl__tb-left"><h2 class="crl__title">发布中心</h2><span class="crl__count">{{ releases.length }}</span></div>
      <div class="crl__tb-right">
        <V2Button variant="primary" size="sm" @click="openCreateDialog">新建发布</V2Button>
        <V2Button variant="ghost" size="sm" :loading="loading" @click="loadReleases">刷新</V2Button>
      </div>
    </div>

    <div class="crl__split">
      <!-- List -->
      <div class="crl__list">
        <div v-for="r in releases" :key="r.release_id" class="crl__item" :class="{ 'crl__item--active': sel?.release_id === r.release_id, 'crl__item--rb': r.status === 'rolled_back' }" @click="selectRelease(r)">
          <div class="crl__item-top">
            <span class="crl__item-name">{{ r.name }}</span>
            <span class="crl__st" :class="'crl__st--' + r.status">{{ releaseStatusLabel(r.status) }}</span>
          </div>
          <div class="crl__item-mid">
            <span class="crl__ver-badge">v{{ r.version }}</span>
            <span class="crl__type-chip">{{ typeLabel(r.release_type) }}</span>
          </div>
          <div class="crl__item-sub">{{ r.release_id?.slice(0, 12) }} · {{ r.released_by || '-' }} · {{ r.created_at }}</div>
        </div>
        <div v-if="!releases.length" class="crl__nil">暂无发布记录</div>
      </div>

      <!-- Detail -->
      <div class="crl__detail" v-if="sel">
        <div class="crl__dh">
          <div>
            <div class="crl__dh-name">{{ sel.name }}</div>
            <div class="crl__dh-meta"><span class="crl__mono">{{ sel.release_id }}</span></div>
          </div>
          <div class="crl__dh-right">
            <span class="crl__ver-badge crl__ver-badge--lg">v{{ sel.version }}</span>
            <span class="crl__st" :class="'crl__st--' + sel.status">{{ releaseStatusLabel(sel.status) }}</span>
          </div>
        </div>

        <!-- Scope strip -->
        <div class="crl__scope">
          <div class="crl__sc"><span class="crl__sc-k">类型</span>{{ typeLabel(sel.release_type) }}</div>
          <div class="crl__sc"><span class="crl__sc-k">发布人</span>{{ sel.released_by || '-' }}</div>
          <div class="crl__sc"><span class="crl__sc-k">时间</span>{{ sel.created_at }}</div>
        </div>

        <!-- Affected items — hierarchical -->
        <div class="crl__sec" v-if="selItems.length">
          <div class="crl__sec-label">变更项 <span class="crl__sec-count">{{ selItems.length }}</span></div>
          <div class="crl__items">
            <div v-for="(it, i) in selItems" :key="i" class="crl__aitem">
              <div class="crl__aitem-icon" :class="'crl__aitem-icon--' + it.item_type">{{ typeIcon(it.item_type) }}</div>
              <div class="crl__aitem-body">
                <div class="crl__aitem-name">{{ it.item_name || it.item_id }}</div>
                <div class="crl__aitem-type">{{ itemTypeLabel(it.item_type) }}</div>
              </div>
              <div class="crl__aitem-ver">
                <span class="crl__ver-from">v{{ it.from_version }}</span>
                <span class="crl__ver-arrow">→</span>
                <span class="crl__ver-to">v{{ it.to_version }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Note -->
        <div v-if="sel.note" class="crl__sec">
          <div class="crl__sec-label">备注</div>
          <div class="crl__note-card">{{ sel.note }}</div>
        </div>

        <!-- Rollbacks -->
        <div v-if="selRollbacks.length" class="crl__sec">
          <div class="crl__sec-label">回滚记录 <span class="crl__sec-count">{{ selRollbacks.length }}</span></div>
          <div v-for="(rb, i) in selRollbacks" :key="i" class="crl__rollback-card">
            <div>回滚至 v{{ rb.target_version }} · {{ rb.rollback_by }} · {{ rb.executed_at }}</div>
            <div v-if="rb.reason" class="crl__rb-reason">{{ rb.reason }}</div>
          </div>
        </div>

        <!-- Rollback action -->
        <div v-if="sel.status === 'released'" class="crl__actions">
          <button class="crl__rb-btn" @click="openRollback(sel.release_id)">↩ 回滚</button>
        </div>
      </div>
      <div class="crl__detail crl__detail--empty" v-else><span class="crl__muted">← 选择一个发布版本查看详情</span></div>
    </div>

    <V2Drawer v-model="rbDialog.visible" title="回滚发布" size="sm">
      <div class="crl__form">
        <label class="crl__form-label">目标版本</label>
        <V2Input v-model="rbDialog.target_version" placeholder="如 1" size="sm" />
        <label class="crl__form-label">回滚原因</label>
        <textarea class="crl__textarea" v-model="rbDialog.reason" rows="2" placeholder="请输入回滚原因"></textarea>
      </div>
      <template #footer>
        <V2Button variant="ghost" size="sm" @click="rbDialog.visible = false">取消</V2Button>
        <V2Button variant="danger" size="sm" @click="doRollback">确认回滚</V2Button>
      </template>
    </V2Drawer>

    <!-- 新建发布抽屉 -->
    <V2Drawer v-model="createDialog.visible" title="新建发布" size="md">
      <div class="crl__form">
        <label class="crl__form-label">发布名称</label>
        <V2Input v-model="createDialog.name" placeholder="如：v2.1 Prompt 优化" size="sm" />
        <label class="crl__form-label">发布类型</label>
        <V2Select v-model="createDialog.release_type" :options="[{label:'提示词',value:'prompt'},{label:'策略',value:'policy'},{label:'工作流',value:'workflow'},{label:'智能体',value:'agent'},{label:'综合',value:'mixed'}]" placeholder="选择类型" size="sm" />
        <label class="crl__form-label">版本号</label>
        <V2Input v-model="createDialog.version" placeholder="如 2" size="sm" />
        <label class="crl__form-label">备注</label>
        <textarea class="crl__textarea" v-model="createDialog.note" rows="2" placeholder="本次发布说明（可选）"></textarea>

        <label class="crl__form-label">变更项</label>
        <div class="crl__create-items">
          <div v-for="(it, i) in createDialog.items" :key="i" class="crl__create-item">
            <V2Select v-model="it.item_type" :options="[{label:'提示词',value:'prompt'},{label:'策略',value:'policy'},{label:'工作流',value:'workflow'},{label:'智能体',value:'agent'}]" placeholder="类型" size="sm" style="width:90px" />
            <V2Input v-model="it.item_name" placeholder="名称" size="sm" style="flex:1" />
            <V2Input v-model="it.from_version" placeholder="原版本" size="sm" style="width:70px" />
            <span class="crl__create-arrow">→</span>
            <V2Input v-model="it.to_version" placeholder="新版本" size="sm" style="width:70px" />
            <V2Button variant="ghost" size="sm" @click="createDialog.items.splice(i, 1)" :disabled="createDialog.items.length <= 1">删除</V2Button>
          </div>
          <V2Button variant="ghost" size="sm" @click="addCreateItem">+ 添加变更项</V2Button>
        </div>
      </div>
      <template #footer>
        <V2Button variant="ghost" size="sm" @click="createDialog.visible = false">取消</V2Button>
        <V2Button variant="primary" size="sm" @click="doCreate" :disabled="!createDialog.name.trim() || !createDialog.version.trim()">确认发布</V2Button>
      </template>
    </V2Drawer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { adminApi } from '@/api/admin/index'
import V2Button from '@/components/v2/V2Button.vue'
import V2Input from '@/components/v2/V2Input.vue'
import V2Select from '@/components/v2/V2Select.vue'
import V2Drawer from '@/components/v2/V2Drawer.vue'

const loading = ref(false), releases = ref([]), sel = ref(null)
const rbDialog = ref({ visible: false, releaseId: '', target_version: '', reason: '' })

const selItems = computed(() => { const it = sel.value?.items ?? sel.value?.release_items; return Array.isArray(it) ? it : [] })
const selRollbacks = computed(() => { const rb = sel.value?.rollbacks; return Array.isArray(rb) ? rb : [] })
const typeIcon = (t) => ({ prompt: 'P', policy: 'G', workflow: 'W', agent: 'A' }[t] || '•')
const typeLabel = (t) => ({ prompt: '提示词', policy: '策略', workflow: '工作流', agent: '智能体', mixed: '综合' }[t] || t)
const releaseStatusLabel = (s) => ({ released: '已发布', rolled_back: '已回滚', pending: '待发布', draft: '草稿' }[s] || s)
const itemTypeLabel = (t) => ({ prompt: '提示词', policy: '策略', workflow: '工作流', agent: '智能体' }[t] || t)

async function selectRelease(row) { try { const d = await adminApi.getRelease(row.release_id); sel.value = { ...row, ...(d ?? {}) } } catch { sel.value = row } }
async function loadReleases() { loading.value = true; try { releases.value = (await adminApi.getReleases())?.items ?? [] } catch (e) { console.warn('[Releases]', e) } finally { loading.value = false } }
function openRollback(id) { rbDialog.value = { visible: true, releaseId: id, target_version: '', reason: '' } }
async function doRollback() {
  try {
    await adminApi.rollbackRelease(rbDialog.value.releaseId, { target_version: rbDialog.value.target_version, reason: rbDialog.value.reason })
    console.log('[Releases] rollback success')
    rbDialog.value.visible = false
    loadReleases()
    if (sel.value?.release_id === rbDialog.value.releaseId) selectRelease(sel.value)
  } catch (e) { console.warn('[Releases] rollback failed', e) }
}

// ── 新建发布 ──
const emptyItem = () => ({ item_type: 'prompt', item_id: '', item_name: '', from_version: '', to_version: '' })
const createDialog = ref({ visible: false, name: '', release_type: 'prompt', version: '', note: '', items: [emptyItem()] })

function openCreateDialog() {
  createDialog.value = { visible: true, name: '', release_type: 'prompt', version: '', note: '', items: [emptyItem()] }
}
function addCreateItem() { createDialog.value.items.push(emptyItem()) }

async function doCreate() {
  const d = createDialog.value
  const items = d.items
    .filter(it => it.item_name.trim())
    .map(it => ({
      item_type: it.item_type,
      item_id: it.item_id || (it.item_type + '-' + Date.now().toString(36)),
      item_name: it.item_name.trim(),
      from_version: it.from_version || null,
      to_version: it.to_version || d.version,
    }))
  if (!items.length) { console.warn('[Releases] no items'); return }
  try {
    await adminApi.createRelease({
      name: d.name.trim(),
      release_type: d.release_type,
      version: d.version.trim(),
      items,
      note: d.note || null,
    })
    console.log('[Releases] create success')
    createDialog.value.visible = false
    loadReleases()
  } catch (e) { console.warn('[Releases] create failed', e) }
}

onMounted(loadReleases)
</script>

<style scoped>
.crl__toolbar { display: flex; align-items: center; gap: var(--v2-space-3); padding: var(--v2-space-2) var(--v2-space-3); margin-bottom: var(--v2-space-3); background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-lg); }
.crl__tb-left { display: flex; align-items: center; gap: var(--v2-space-2); flex: 1; }
.crl__title { font-size: var(--v2-text-md); font-weight: var(--v2-font-semibold); color: var(--v2-text-1); margin: 0; }
.crl__count { font-size: var(--v2-text-xs); padding: 0 5px; background: var(--v2-bg-sunken); color: var(--v2-text-3); border-radius: var(--v2-radius-sm); }

.crl__split { display: grid; grid-template-columns: 380px 1fr; gap: var(--v2-space-3); min-height: calc(100vh - 180px); }

.crl__list { background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-lg); overflow-y: auto; }
.crl__item { padding: var(--v2-space-3); border-bottom: 1px solid var(--v2-border-1); cursor: pointer; transition: background var(--v2-trans-fast); }
.crl__item:hover { background: var(--v2-bg-sunken); }
.crl__item--active { background: var(--v2-brand-bg); border-left: 3px solid var(--v2-brand-primary); }
.crl__item--rb { opacity: .6; }
.crl__item-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 3px; }
.crl__item-name { font-size: 12px; font-weight: var(--v2-font-medium); color: var(--v2-text-1); }
.crl__item-mid { display: flex; gap: 6px; align-items: center; margin-bottom: 2px; }
.crl__item-sub { font-size: 10px; color: var(--v2-text-4); font-family: var(--v2-font-mono); }

.crl__st { font-size: 10px; font-weight: var(--v2-font-medium); padding: 1px 5px; border-radius: 3px; }
.crl__st--released { background: var(--v2-success-bg); color: var(--v2-success-text); }
.crl__st--rolled_back { background: var(--v2-error-bg); color: var(--v2-error-text); }
.crl__st--pending { background: var(--v2-warning-bg); color: var(--v2-warning-text); }

.crl__ver-badge { font-size: 10px; padding: 1px 6px; background: var(--v2-brand-bg); color: var(--v2-brand-primary); border-radius: 3px; font-family: var(--v2-font-mono); font-weight: var(--v2-font-semibold); }
.crl__ver-badge--lg { font-size: 12px; padding: 2px 8px; }
.crl__type-chip { font-size: 9px; padding: 0 5px; background: var(--v2-bg-sunken); color: var(--v2-text-3); border-radius: 3px; }

.crl__detail { background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-lg); padding: var(--v2-space-4); overflow-y: auto; display: flex; flex-direction: column; gap: var(--v2-space-3); }
.crl__detail--empty { align-items: center; justify-content: center; }

.crl__dh { display: flex; justify-content: space-between; align-items: flex-start; padding-bottom: var(--v2-space-3); border-bottom: 1px solid var(--v2-border-2); }
.crl__dh-name { font-size: var(--v2-text-md); font-weight: var(--v2-font-semibold); color: var(--v2-text-1); }
.crl__dh-meta { font-size: 10px; color: var(--v2-text-4); margin-top: 2px; }
.crl__dh-right { display: flex; align-items: center; gap: 6px; }

.crl__scope { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
.crl__sc { padding: 6px 8px; background: var(--v2-bg-sunken); border-radius: var(--v2-radius-md); font-size: 12px; color: var(--v2-text-1); }
.crl__sc-k { display: block; font-size: 9px; color: var(--v2-text-4); text-transform: uppercase; letter-spacing: .3px; }

.crl__sec { } .crl__sec-label { font-size: 10px; font-weight: var(--v2-font-semibold); color: var(--v2-text-4); text-transform: uppercase; letter-spacing: .5px; margin-bottom: 6px; display: flex; align-items: center; gap: 6px; }
.crl__sec-count { font-size: 9px; padding: 0 4px; background: var(--v2-bg-sunken); border-radius: 3px; }

/* Hierarchical items */
.crl__items { display: flex; flex-direction: column; gap: 4px; }
.crl__aitem { display: flex; align-items: center; gap: 8px; padding: 8px 10px; background: var(--v2-bg-sunken); border-radius: var(--v2-radius-md); }
.crl__aitem-icon { width: 24px; height: 24px; border-radius: var(--v2-radius-sm); display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: var(--v2-font-bold); color: #fff; flex-shrink: 0; }
.crl__aitem-icon--prompt { background: var(--v2-brand-primary); }
.crl__aitem-icon--policy { background: var(--v2-ai-purple); }
.crl__aitem-icon--workflow { background: var(--v2-warning); }
.crl__aitem-icon--agent { background: var(--v2-success); }
.crl__aitem-body { flex: 1; min-width: 0; }
.crl__aitem-name { font-size: 12px; font-weight: var(--v2-font-medium); color: var(--v2-text-1); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.crl__aitem-type { font-size: 10px; color: var(--v2-text-4); }
.crl__aitem-ver { display: flex; align-items: center; gap: 3px; font-family: var(--v2-font-mono); font-size: 10px; flex-shrink: 0; }
.crl__ver-from { color: var(--v2-text-4); }
.crl__ver-arrow { color: var(--v2-text-4); }
.crl__ver-to { color: var(--v2-brand-primary); font-weight: var(--v2-font-semibold); }

.crl__note-card { padding: 8px 10px; background: var(--v2-bg-sunken); border-radius: var(--v2-radius-md); font-size: 12px; color: var(--v2-text-2); line-height: 1.5; }
.crl__rollback-card { padding: 8px 10px; background: var(--v2-error-bg); border: 1px solid rgba(239,68,68,.15); border-radius: var(--v2-radius-md); font-size: 12px; color: var(--v2-error-text); margin-bottom: 4px; }
.crl__rb-reason { font-size: 11px; color: var(--v2-text-3); margin-top: 2px; }

/* Form styles */
.crl__form { display: flex; flex-direction: column; gap: 10px; }
.crl__form-label { font-size: var(--v2-text-xs); font-weight: var(--v2-font-semibold); color: var(--v2-text-3); text-transform: uppercase; letter-spacing: .4px; }
.crl__textarea { width: 100%; padding: 8px 10px; font-size: var(--v2-text-sm); border: 1px solid var(--v2-border-1); border-radius: var(--v2-radius-md); background: var(--v2-bg-card); color: var(--v2-text-1); resize: vertical; font-family: inherit; }
.crl__textarea:focus { outline: none; border-color: var(--v2-brand-primary); box-shadow: 0 0 0 2px color-mix(in srgb, var(--v2-brand-primary) 15%, transparent); }

/* Create drawer items */
.crl__create-items { display: flex; flex-direction: column; gap: 8px; width: 100%; }
.crl__create-item { display: flex; align-items: center; gap: 6px; }
.crl__create-arrow { color: var(--v2-text-4); font-size: 12px; flex-shrink: 0; }

.crl__actions { margin-top: auto; padding-top: var(--v2-space-3); border-top: 1px solid var(--v2-border-2); }
.crl__rb-btn { width: 100%; padding: 8px 0; background: var(--v2-error-bg); color: var(--v2-error-text); border: 1px solid rgba(239,68,68,.15); border-radius: var(--v2-radius-md); font-size: 12px; font-weight: var(--v2-font-semibold); cursor: pointer; } .crl__rb-btn:hover { background: var(--v2-error); color: #fff; }

.crl__mono { font-family: var(--v2-font-mono); font-size: 10px; color: var(--v2-text-3); }
.crl__muted { font-size: 12px; color: var(--v2-text-4); }
.crl__nil { padding: var(--v2-space-8); text-align: center; font-size: 12px; color: var(--v2-text-4); }

@media (max-width: 1200px) { .crl__split { grid-template-columns: 1fr; } }
</style>
