<template>
  <div class="ct">
    <!-- Toolbar -->
    <div class="ct__toolbar">
      <div class="ct__tb-left"><h2 class="ct__title">团队权限管理</h2><span class="ct__count">{{ users.length }}</span></div>
      <div class="ct__tb-filters">
        <V2Input v-model="filter.keyword" placeholder="搜索用户…" clearable size="sm" style="width:160px" @clear="load" @enter="load" />
        <V2Select v-model="filter.is_active" :options="[{label:'已启用',value:1},{label:'已禁用',value:0}]" placeholder="状态" clearable size="sm" style="width:90px" @update:model-value="load" />
        <V2Button variant="primary" size="sm" @click="load">查询</V2Button>
      </div>
      <V2Button variant="primary" size="sm" @click="showCreate = true">新建用户</V2Button>
    </div>

    <div class="ct__body">
      <!-- Left: role sidebar -->
      <div class="ct__sidebar">
        <div class="ct__sb-title">角色列表</div>
        <div v-for="r in dbRoles" :key="r.role_name" class="ct__role-card" :class="{ 'ct__role-card--active': filter.role === r.role_name }" @click="toggleRoleFilter(r.role_name)">
          <div class="ct__role-name">{{ r.description || r.role_name }}</div>
          <span class="ct__role-count">{{ roleCounts[r.role_name] || 0 }}</span>
        </div>
      </div>

      <!-- Middle: user list -->
      <div class="ct__list">
        <div v-for="u in filteredUsers" :key="u.user_id" class="ct__item" :class="{ 'ct__item--active': sel?.user_id === u.user_id, 'ct__item--off': !u.is_active }" @click="sel = u">
          <div class="ct__item-top">
            <span class="ct__item-name">{{ u.display_name || u.username }}</span>
            <span class="ct__st" :class="u.is_active ? 'ct__st--on' : 'ct__st--off'">{{ u.is_active ? '已启用' : '已禁用' }}</span>
          </div>
          <div class="ct__item-sub">
            <span class="ct__item-user">@{{ u.username }}</span>
            <span v-for="r in u.roles" :key="r" class="ct__role-chip">{{ roleLabel(r) }}</span>
          </div>
        </div>
        <div v-if="!filteredUsers.length" class="ct__nil">暂无用户</div>
      </div>

      <!-- Right: detail panel -->
      <div class="ct__detail" v-if="sel">
        <div class="ct__dh">
          <div class="ct__dh-title">{{ sel.display_name || sel.username }}</div>
          <span class="ct__st" :class="sel.is_active ? 'ct__st--on' : 'ct__st--off'">{{ sel.is_active ? '已启用' : '已禁用' }}</span>
        </div>

        <div class="ct__meta">
          <div class="ct__mc"><span class="ct__mc-k">用户名</span><span class="ct__mono">{{ sel.username }}</span></div>
          <div class="ct__mc"><span class="ct__mc-k">显示名</span>{{ sel.display_name || '-' }}</div>
          <div class="ct__mc"><span class="ct__mc-k">邮箱</span>{{ sel.email || '-' }}</div>
          <div class="ct__mc"><span class="ct__mc-k">角色</span>
            <span v-for="r in sel.roles" :key="r" class="ct__role-chip">{{ roleLabel(r) }}</span>
            <span v-if="!sel.roles?.length">-</span>
          </div>
          <div class="ct__mc"><span class="ct__mc-k">创建时间</span>{{ fmtTime(sel.created_at) }}</div>
          <div class="ct__mc"><span class="ct__mc-k">更新时间</span>{{ fmtTime(sel.updated_at) }}</div>
        </div>

        <!-- Role assignment -->
        <div class="ct__sec">
          <div class="ct__sec-label">分配角色</div>
          <div style="display:flex;gap:8px;align-items:center">
            <V2Select v-model="assignRole" :options="dbRoles.map(r => ({label: r.description || r.role_name, value: r.role_name}))" placeholder="选择角色" size="sm" style="width:200px" />
            <V2Button variant="primary" size="sm" @click="doAssignRole" :disabled="!assignRole">确认分配</V2Button>
          </div>
        </div>

        <!-- Actions -->
        <div class="ct__actions">
          <V2Button v-if="sel.is_active" variant="danger" size="sm" @click="doDisable(sel.user_id)">禁用账号</V2Button>
          <V2Button v-else variant="primary" size="sm" @click="doEnable(sel.user_id)">启用账号</V2Button>
        </div>
      </div>
      <div class="ct__detail ct__detail--empty" v-else><span class="ct__muted">← 选择一个用户</span></div>
    </div>

    <!-- Create drawer -->
    <V2Drawer v-model="showCreate" title="新建用户" size="sm">
      <div class="ct__form">
        <label class="ct__form-label">用户名</label>
        <V2Input v-model="form.username" size="sm" />
        <label class="ct__form-label">显示名</label>
        <V2Input v-model="form.display_name" size="sm" />
        <label class="ct__form-label">邮箱</label>
        <V2Input v-model="form.email" size="sm" />
        <label class="ct__form-label">密码</label>
        <V2Input v-model="form.password" type="password" size="sm" />
        <label class="ct__form-label">角色</label>
        <V2Select v-model="form.role_name" :options="dbRoles.map(r => ({label: r.description || r.role_name, value: r.role_name}))" placeholder="选择角色" size="sm" />
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
import { teamApi } from '@/api/admin/team'
import V2Input from '@/components/v2/V2Input.vue'
import V2Select from '@/components/v2/V2Select.vue'
import V2Button from '@/components/v2/V2Button.vue'
import V2Drawer from '@/components/v2/V2Drawer.vue'

const users = ref([]), loading = ref(false), sel = ref(null), showCreate = ref(false), saving = ref(false)
const dbRoles = ref([])
const filter = ref({ keyword: '', is_active: '', role: '' })
const form = ref({ username: '', display_name: '', email: '', password: '', role_name: '' })
const assignRole = ref('')

const ROLE_LABELS = {
  platform_admin: '平台管理员', ml_engineer: '算法工程师', ops_analyst: '运营分析师',
  customer_service_manager: '客服主管', risk_reviewer: '风控审核员', auditor: '审计员',
  super_admin: '超级管理员', business_admin: '业务管理员', service_agent: '客服专员',
}
function roleLabel(r) { return ROLE_LABELS[r] || r }
function fmtTime(v) {
  if (!v) return '-'; const d = new Date(v); if (isNaN(d)) return String(v).slice(0, 16)
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
}

const roleCounts = computed(() => {
  const c = {}; for (const u of users.value) { for (const r of (u.roles || [])) { c[r] = (c[r] || 0) + 1 } }; return c
})
const filteredUsers = computed(() => {
  let list = users.value
  if (filter.value.keyword) {
    const kw = filter.value.keyword.toLowerCase()
    list = list.filter(u => (u.username || '').toLowerCase().includes(kw) || (u.display_name || '').toLowerCase().includes(kw) || (u.email || '').toLowerCase().includes(kw))
  }
  if (filter.value.role) { list = list.filter(u => (u.roles || []).includes(filter.value.role)) }
  return list
})

function toggleRoleFilter(rn) { filter.value.role = filter.value.role === rn ? '' : rn }

async function load() {
  loading.value = true
  try {
    const p = {}
    if (filter.value.is_active !== '') p.is_active = filter.value.is_active
    if (filter.value.keyword) p.keyword = filter.value.keyword
    const r = await teamApi.getUsers(p)
    users.value = r?.items ?? (Array.isArray(r) ? r : [])
  } catch { users.value = [] } finally { loading.value = false }
}
async function loadRoles() {
  try { const r = await teamApi.getRoles(); dbRoles.value = r?.items ?? [] } catch {}
}
async function doCreate() {
  if (!form.value.username || !form.value.password) { alert('请填写用户名和密码'); return }
  saving.value = true
  try {
    await teamApi.createUser(form.value)
    showCreate.value = false; form.value = { username: '', display_name: '', email: '', password: '', role_name: '' }
    load()
  } catch (e) { console.warn('[Team] create failed', e) } finally { saving.value = false }
}
async function doAssignRole() {
  if (!sel.value || !assignRole.value) return
  try {
    await teamApi.assignRole(sel.value.user_id, { role_name: assignRole.value })
    assignRole.value = ''; load()
  } catch (e) { console.warn('[Team] assign role failed', e) }
}
async function doDisable(id) {
  if (!confirm('确定禁用该用户？')) return
  try { await teamApi.disableUser(id); sel.value = null; load() } catch (e) { console.warn('[Team] disable failed', e) }
}
async function doEnable(id) {
  try { await teamApi.enableUser(id); sel.value = null; load() } catch (e) { console.warn('[Team] enable failed', e) }
}

onMounted(() => { load(); loadRoles() })
</script>

<style scoped>
.ct__toolbar { display: flex; align-items: center; gap: var(--v2-space-3); padding: var(--v2-space-2) var(--v2-space-3); margin-bottom: var(--v2-space-3); background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-lg); flex-wrap: wrap; }
.ct__tb-left { display: flex; align-items: center; gap: var(--v2-space-2); margin-right: auto; }
.ct__title { font-size: var(--v2-text-md); font-weight: var(--v2-font-semibold); color: var(--v2-text-1); margin: 0; }
.ct__count { font-size: var(--v2-text-xs); padding: 0 5px; background: var(--v2-bg-sunken); color: var(--v2-text-3); border-radius: var(--v2-radius-sm); }
.ct__tb-filters { display: flex; align-items: center; gap: 6px; }

.ct__body { display: flex; gap: var(--v2-space-3); min-height: 500px; }
.ct__sidebar { width: 200px; flex-shrink: 0; display: flex; flex-direction: column; gap: 6px; }
.ct__sb-title { font-size: var(--v2-text-xs); font-weight: var(--v2-font-semibold); color: var(--v2-text-3); text-transform: uppercase; letter-spacing: .5px; margin-bottom: 4px; }
.ct__role-card { display: flex; align-items: center; justify-content: space-between; padding: 8px 10px; background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-md); cursor: pointer; transition: all .15s; }
.ct__role-card:hover { border-color: var(--v2-brand-primary); }
.ct__role-card--active { border-color: var(--v2-brand-primary); background: color-mix(in srgb, var(--v2-brand-primary) 6%, transparent); }
.ct__role-name { font-size: var(--v2-text-sm); color: var(--v2-text-1); }
.ct__role-count { font-size: var(--v2-text-xs); padding: 0 5px; background: var(--v2-bg-sunken); color: var(--v2-text-3); border-radius: var(--v2-radius-sm); }

.ct__list { flex: 1; min-width: 260px; display: flex; flex-direction: column; gap: 6px; overflow-y: auto; max-height: 600px; }
.ct__item { padding: 10px 12px; background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-md); cursor: pointer; transition: all .15s; }
.ct__item:hover { border-color: var(--v2-brand-primary); }
.ct__item--active { border-color: var(--v2-brand-primary); background: color-mix(in srgb, var(--v2-brand-primary) 6%, transparent); }
.ct__item--off { opacity: .55; }
.ct__item-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.ct__item-name { font-size: var(--v2-text-sm); font-weight: var(--v2-font-semibold); color: var(--v2-text-1); }
.ct__item-sub { display: flex; align-items: center; gap: 6px; font-size: var(--v2-text-xs); color: var(--v2-text-3); flex-wrap: wrap; }
.ct__item-user { font-family: var(--v2-font-mono); }
.ct__role-chip { font-size: 10px; padding: 1px 6px; background: var(--v2-bg-sunken); color: var(--v2-text-2); border-radius: 3px; margin-right: 3px; }
.ct__nil { text-align: center; color: var(--v2-text-3); padding: 40px 0; }

.ct__st { font-size: 10px; padding: 1px 6px; border-radius: 3px; font-weight: 500; }
.ct__st--on { background: color-mix(in srgb, #22c55e 14%, transparent); color: #16a34a; }
.ct__st--off { background: color-mix(in srgb, #ef4444 14%, transparent); color: #dc2626; }

.ct__detail { flex: 1; min-width: 300px; background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-lg); padding: var(--v2-space-3); }
.ct__detail--empty { display: flex; align-items: center; justify-content: center; }
.ct__muted { color: var(--v2-text-3); }
.ct__dh { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.ct__dh-title { font-size: var(--v2-text-md); font-weight: var(--v2-font-semibold); color: var(--v2-text-1); }
.ct__meta { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 16px; }
.ct__mc { font-size: var(--v2-text-sm); padding: 6px 8px; background: var(--v2-bg-sunken); border-radius: var(--v2-radius-sm); display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.ct__mc-k { color: var(--v2-text-3); min-width: 56px; flex-shrink: 0; }
.ct__mono { font-family: var(--v2-font-mono); font-size: var(--v2-text-xs); }
.ct__sec { margin-bottom: 14px; }
.ct__sec-label { font-size: var(--v2-text-xs); font-weight: var(--v2-font-semibold); color: var(--v2-text-3); margin-bottom: 6px; }
.ct__actions { display: flex; gap: 8px; margin-top: 12px; }
.ct__form { display: flex; flex-direction: column; gap: 10px; }
.ct__form-label { font-size: var(--v2-text-xs); font-weight: var(--v2-font-semibold); color: var(--v2-text-3); text-transform: uppercase; letter-spacing: .4px; }
</style>
