<template>
  <div class="ck">
    <div class="ck__toolbar">
      <div class="ck__tb-left"><h2 class="ck__title">知识库管理</h2><span class="ck__count">{{ filteredFaqs.length }}</span></div>
      <div class="ck__tb-filters">
        <V2Input v-model="filter.keyword" placeholder="搜索…" clearable size="sm" style="width:160px" @clear="load" />
        <V2Select v-model="filter.is_active" :options="[{label:'已启用',value:1},{label:'已禁用',value:0}]" placeholder="状态" clearable size="sm" style="width:90px" @update:model-value="load" />
        <V2Button variant="primary" size="sm" @click="load">查询</V2Button>
      </div>
      <V2Button variant="primary" size="sm" @click="showCreate = true">新建</V2Button>
    </div>

    <div class="ck__body">
      <!-- Left: group sidebar -->
      <div class="ck__groups">
        <div class="ck__grp" :class="{ 'ck__grp--active': filter.group_name === '' }" @click="filter.group_name = ''; load()">
          <span>全部分组</span><span class="ck__grp-count">{{ allTotal }}</span>
        </div>
        <div v-for="g in groups" :key="g" class="ck__grp" :class="{ 'ck__grp--active': filter.group_name === g }" @click="filter.group_name = g; load()">
          <span>{{ groupLabel(g) }}</span><span class="ck__grp-count">{{ groupCounts[g] || 0 }}</span>
        </div>
      </div>

      <!-- Middle: FAQ list -->
      <div class="ck__list">
        <div v-for="f in filteredFaqs" :key="f.doc_id" class="ck__item" :class="{ 'ck__item--active': sel?.doc_id === f.doc_id, 'ck__item--off': !f.is_active }" @click="selectRow(f)">
          <div class="ck__item-top">
            <span class="ck__item-title">{{ f.title }}</span>
            <span class="ck__st" :class="f.is_active ? 'ck__st--on' : 'ck__st--off'">{{ f.is_active ? '已启用' : '已禁用' }}</span>
          </div>
          <div class="ck__item-sub">
            <span class="ck__grp-chip">{{ groupLabel(f.group_name) }}</span>
            <span v-if="f.source">{{ f.source }}</span>
            <span>{{ f.updated_at || f.created_at }}</span>
          </div>
        </div>
        <div v-if="!filteredFaqs.length" class="ck__nil">暂无文档</div>
        <div class="ck__pg">
          <V2Pager v-model="page" :total="total" :page-size="20" @change="load" />
        </div>
      </div>

      <!-- Right: detail -->
      <div class="ck__detail" v-if="sel">
        <div class="ck__dh">
          <div class="ck__dh-title">{{ sel.title }}</div>
          <span class="ck__st" :class="sel.is_active ? 'ck__st--on' : 'ck__st--off'">{{ sel.is_active ? '已启用' : '已禁用' }}</span>
        </div>

        <!-- Metadata cards -->
        <div class="ck__meta">
          <div class="ck__mc"><span class="ck__mc-k">ID</span><span class="ck__mono">{{ sel.doc_id }}</span></div>
          <div class="ck__mc"><span class="ck__mc-k">分组</span><span class="ck__grp-chip">{{ groupLabel(sel.group_name) }}</span></div>
          <div class="ck__mc"><span class="ck__mc-k">来源</span>{{ sel.source || '-' }}</div>
          <div class="ck__mc"><span class="ck__mc-k">作者</span>{{ sel.created_by || '-' }}</div>
          <div class="ck__mc"><span class="ck__mc-k">创建时间</span>{{ fmtTime(sel.created_at) }}</div>
          <div class="ck__mc"><span class="ck__mc-k">更新时间</span>{{ fmtTime(sel.updated_at) }}</div>
        </div>

        <!-- Content -->
        <div class="ck__sec">
          <div class="ck__sec-label">内容</div>
          <div class="ck__content-area">{{ sel.content || '(空)' }}</div>
        </div>

        <!-- Actions -->
        <div class="ck__actions" v-if="sel.is_active">
          <button class="ck__disable-btn" @click="doDisable(sel.doc_id)">禁用</button>
        </div>
      </div>
      <div class="ck__detail ck__detail--empty" v-else><span class="ck__muted">← 选择一个文档</span></div>
    </div>

    <!-- Create FAQ -->
    <V2Drawer v-model="showCreate" title="新建 FAQ 文档" size="md">
      <div class="ck__form">
        <label class="ck__form-label">分组</label>
        <V2Select v-model="form.group_name" :options="groups.map(g => ({label: groupLabel(g), value: g}))" size="sm" />
        <label class="ck__form-label">标题</label>
        <V2Input v-model="form.title" size="sm" />
        <label class="ck__form-label">内容</label>
        <textarea class="ck__textarea" v-model="form.content" rows="5"></textarea>
        <label class="ck__form-label">来源</label>
        <V2Input v-model="form.source" placeholder="手动录入 / 批量导入" size="sm" />
      </div>
      <template #footer>
        <V2Button variant="ghost" size="sm" @click="showCreate = false">取消</V2Button>
        <V2Button variant="primary" size="sm" :loading="saving" @click="doCreate">创建</V2Button>
      </template>
    </V2Drawer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { adminApi } from '@/api/admin/index'
import V2Input from '@/components/v2/V2Input.vue'
import V2Select from '@/components/v2/V2Select.vue'
import V2Button from '@/components/v2/V2Button.vue'
import V2Drawer from '@/components/v2/V2Drawer.vue'
import V2Pager from '@/components/v2/V2Pager.vue'

const faqs = ref([]), loading = ref(false), total = ref(0), page = ref(1), sel = ref(null), showCreate = ref(false), saving = ref(false)
const filter = ref({ keyword: '', group_name: '', is_active: '' })
const form = ref({ group_name: 'general', title: '', content: '', source: '' })
const groups = ['order', 'refund', 'shipping', 'account', 'general']
const GROUP_LABELS = { order: '订单', refund: '退款', shipping: '物流', account: '账户', general: '通用' }
function groupLabel(g) { return GROUP_LABELS[g] || g }
function fmtTime(v) {
  if (!v) return '-'; const d = new Date(v); if (isNaN(d)) return String(v).slice(0, 16)
  const M = String(d.getMonth() + 1).padStart(2, '0'), D = String(d.getDate()).padStart(2, '0')
  const hh = String(d.getHours()).padStart(2, '0'), mm = String(d.getMinutes()).padStart(2, '0')
  return `${M}-${D} ${hh}:${mm}`
}

const groupCounts = ref({}), allTotal = ref(0)
function refreshCounts(list) { const c = {}; for (const f of list) { c[f.group_name] = (c[f.group_name] || 0) + 1 }; groupCounts.value = c; allTotal.value = list.length }

const filteredFaqs = computed(() => {
  let list = faqs.value
  if (filter.value.keyword) { const kw = filter.value.keyword.toLowerCase(); list = list.filter(f => (f.title || '').toLowerCase().includes(kw) || (f.content || '').toLowerCase().includes(kw)) }
  return list
})

async function selectRow(row) { if (!row) { sel.value = null; return }; try { sel.value = (await adminApi.getFAQ(row.doc_id)) ?? row } catch { sel.value = row } }
async function loadCounts() { try { const r = await adminApi.getFAQs({ limit: 1000 }); refreshCounts(r?.items ?? []) } catch {} }
async function load() { loading.value = true; try { const p = { limit: 20, offset: (page.value - 1) * 20 }; if (filter.value.group_name) p.group_name = filter.value.group_name; if (filter.value.is_active !== '') p.is_active = filter.value.is_active; const r = await adminApi.getFAQs(p); faqs.value = r?.items ?? (Array.isArray(r) ? r : []); total.value = r?.total ?? faqs.value.length; if (!filter.value.group_name) refreshCounts(faqs.value) } catch { faqs.value = [] } finally { loading.value = false } }
async function doDisable(id) { if (!confirm('确定禁用该文档？')) return; try { await adminApi.disableFAQ(id); load(); loadCounts() } catch (e) { console.warn('[Knowledge] disable failed', e) } }
async function doCreate() { saving.value = true; try { await adminApi.createFAQ(form.value); showCreate.value = false; form.value = { group_name: 'general', title: '', content: '', source: '' }; load(); loadCounts() } catch (e) { console.warn('[Knowledge] create failed', e) } finally { saving.value = false } }

onMounted(load)
</script>

<style scoped>
.ck__toolbar { display: flex; align-items: center; gap: var(--v2-space-3); padding: var(--v2-space-2) var(--v2-space-3); margin-bottom: var(--v2-space-3); background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-lg); flex-wrap: wrap; }
.ck__tb-left { display: flex; align-items: center; gap: var(--v2-space-2); margin-right: auto; }
.ck__title { font-size: var(--v2-text-md); font-weight: var(--v2-font-semibold); color: var(--v2-text-1); margin: 0; }
.ck__count { font-size: var(--v2-text-xs); padding: 0 5px; background: var(--v2-bg-sunken); color: var(--v2-text-3); border-radius: var(--v2-radius-sm); }
.ck__tb-filters { display: flex; align-items: center; gap: 6px; }

.ck__body { display: grid; grid-template-columns: 140px 360px 1fr; gap: var(--v2-space-3); min-height: calc(100vh - 180px); }

/* Group sidebar */
.ck__groups { background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-lg); overflow-y: auto; }
.ck__grp { display: flex; justify-content: space-between; align-items: center; padding: 8px 10px; font-size: 11px; color: var(--v2-text-2); cursor: pointer; border-bottom: 1px solid var(--v2-border-1); transition: background var(--v2-trans-fast); }
.ck__grp:hover { background: var(--v2-bg-sunken); }
.ck__grp--active { background: var(--v2-brand-bg); color: var(--v2-brand-primary); font-weight: var(--v2-font-semibold); border-left: 3px solid var(--v2-brand-primary); }
.ck__grp-count { font-size: 9px; padding: 0 4px; background: var(--v2-bg-sunken); color: var(--v2-text-4); border-radius: 3px; }
.ck__grp-chip { font-size: 9px; padding: 0 5px; background: var(--v2-ai-purple-bg); color: var(--v2-ai-purple); border-radius: 3px; font-weight: var(--v2-font-medium); }

/* FAQ list */
.ck__list { background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-lg); overflow-y: auto; display: flex; flex-direction: column; }
.ck__item { padding: var(--v2-space-3); border-bottom: 1px solid var(--v2-border-1); cursor: pointer; transition: background var(--v2-trans-fast); }
.ck__item:hover { background: var(--v2-bg-sunken); }
.ck__item--active { background: var(--v2-brand-bg); border-left: 3px solid var(--v2-brand-primary); }
.ck__item--off { opacity: .55; }
.ck__item-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 2px; }
.ck__item-title { font-size: 12px; font-weight: var(--v2-font-medium); color: var(--v2-text-1); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; margin-right: 6px; }
.ck__item-sub { font-size: 10px; color: var(--v2-text-4); display: flex; gap: var(--v2-space-3); align-items: center; }

.ck__st { font-size: 10px; font-weight: var(--v2-font-medium); padding: 1px 5px; border-radius: 3px; flex-shrink: 0; }
.ck__st--on { background: var(--v2-success-bg); color: var(--v2-success-text); }
.ck__st--off { background: var(--v2-bg-sunken); color: var(--v2-text-4); }

.ck__pg { margin-top: auto; padding: 8px var(--v2-space-3); border-top: 1px solid var(--v2-border-1); display: flex; justify-content: flex-end; }

/* Detail */
.ck__detail { background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-lg); padding: var(--v2-space-4); overflow-y: auto; display: flex; flex-direction: column; gap: var(--v2-space-3); }
.ck__detail--empty { align-items: center; justify-content: center; }

.ck__dh { display: flex; justify-content: space-between; align-items: center; padding-bottom: var(--v2-space-3); border-bottom: 1px solid var(--v2-border-2); }
.ck__dh-title { font-size: var(--v2-text-md); font-weight: var(--v2-font-semibold); color: var(--v2-text-1); }

.ck__meta { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
.ck__mc { padding: 6px 8px; background: var(--v2-bg-sunken); border-radius: var(--v2-radius-md); font-size: 12px; color: var(--v2-text-1); }
.ck__mc-k { display: block; font-size: 9px; color: var(--v2-text-4); text-transform: uppercase; letter-spacing: .3px; }

.ck__sec { } .ck__sec-label { font-size: 10px; font-weight: var(--v2-font-semibold); color: var(--v2-text-4); text-transform: uppercase; letter-spacing: .5px; margin-bottom: 4px; }
.ck__content-area { font-size: 13px; color: var(--v2-text-1); line-height: 1.7; padding: var(--v2-space-3); background: var(--v2-bg-sunken); border-radius: var(--v2-radius-md); white-space: pre-wrap; word-break: break-all; max-height: 300px; overflow-y: auto; }

.ck__actions { margin-top: auto; padding-top: var(--v2-space-3); border-top: 1px solid var(--v2-border-2); }
.ck__disable-btn { width: 100%; padding: 8px 0; background: var(--v2-error-bg); color: var(--v2-error-text); border: 1px solid rgba(239,68,68,.15); border-radius: var(--v2-radius-md); font-size: 12px; font-weight: var(--v2-font-semibold); cursor: pointer; } .ck__disable-btn:hover { background: var(--v2-error); color: #fff; }

.ck__form { display: flex; flex-direction: column; gap: 10px; }
.ck__form-label { font-size: var(--v2-text-xs); font-weight: var(--v2-font-semibold); color: var(--v2-text-3); text-transform: uppercase; letter-spacing: .4px; }
.ck__textarea { width: 100%; padding: 8px 10px; font-size: var(--v2-text-sm); border: 1px solid var(--v2-border-1); border-radius: var(--v2-radius-md); background: var(--v2-bg-card); color: var(--v2-text-1); resize: vertical; font-family: inherit; }
.ck__textarea:focus { outline: none; border-color: var(--v2-brand-primary); box-shadow: 0 0 0 2px color-mix(in srgb, var(--v2-brand-primary) 15%, transparent); }

.ck__mono { font-family: var(--v2-font-mono); font-size: 10px; color: var(--v2-text-3); }
.ck__muted { font-size: 12px; color: var(--v2-text-4); }
.ck__nil { padding: var(--v2-space-8); text-align: center; font-size: 12px; color: var(--v2-text-4); }

@media (max-width: 1200px) { .ck__body { grid-template-columns: 1fr; } .ck__groups { display: none; } }
</style>
