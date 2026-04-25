<template>
  <div class="cs">
    <div class="cs__header">
      <h2 class="cs__title">系统设置</h2>
      <div class="cs__tabs">
        <button v-for="t in tabs" :key="t.key" class="cs__tab" :class="{ 'cs__tab--active': activeTab === t.key }" @click="activeTab = t.key">{{ t.label }}</button>
      </div>
    </div>

    <!-- ── Tab: 个人信息与偏好 ──────────────────────────── -->
    <div v-if="activeTab === 'profile'" class="cs__grid">
      <div class="cs__card">
        <div class="cs__card-title">个人信息</div>
        <div class="cs__kv">
          <div class="cs__kv-row"><span class="cs__kv-k">用户名</span><span class="cs__kv-v">{{ username }}</span></div>
          <div class="cs__kv-row"><span class="cs__kv-k">角色</span><span class="cs__kv-v">{{ roleLabel }}</span></div>
          <div class="cs__kv-row"><span class="cs__kv-k">会话状态</span><span class="cs__kv-v cs__kv-v--ok" v-if="auth.isLoggedIn">已登录</span><span class="cs__kv-v cs__kv-v--err" v-else>已过期</span></div>
        </div>
        <V2Button variant="danger" size="sm" style="margin-top:14px" @click="doLogout">退出登录</V2Button>
      </div>

      <div class="cs__card">
        <div class="cs__card-title">界面偏好</div>
        <div class="cs__pref-row">
          <span>表格密度</span>
          <V2Segment v-model="density" :options="[{label:'紧凑',value:'compact'},{label:'默认',value:'default'}]" size="sm" @change="saveDensity" />
        </div>
        <div class="cs__pref-row">
          <span>时区</span>
          <V2Select v-model="tz" :options="[{label:'Asia/Shanghai (UTC+8)',value:'Asia/Shanghai'}]" size="sm" style="width:180px" disabled />
        </div>
        <div class="cs__notice">偏好设置仅存储在本地浏览器，不会同步到服务端。</div>
      </div>

      <div class="cs__card">
        <div class="cs__card-title">键盘快捷键</div>
        <div class="cs__shortcuts">
          <div class="cs__sc-row"><kbd>Ctrl+K</kbd><span>打开命令面板</span></div>
          <div class="cs__sc-row"><kbd>/</kbd><span>打开搜索</span></div>
          <div class="cs__sc-row"><kbd>g d</kbd><span>跳转到仪表盘</span></div>
          <div class="cs__sc-row"><kbd>g t</kbd><span>跳转到 Trace 追踪</span></div>
          <div class="cs__sc-row"><kbd>g r</kbd><span>跳转到 HITL 审核</span></div>
          <div class="cs__sc-row"><kbd>g p</kbd><span>跳转到 Prompt 中心</span></div>
          <div class="cs__sc-row"><kbd>↑↓</kbd><span>上下导航表格行</span></div>
          <div class="cs__sc-row"><kbd>Enter</kbd><span>选择当前行</span></div>
        </div>
      </div>

      <div class="cs__card">
        <div class="cs__card-title">关于平台</div>
        <div class="cs__kv">
          <div class="cs__kv-row"><span class="cs__kv-k">平台名称</span><span class="cs__kv-v">柠优生活大数据智能决策平台</span></div>
          <div class="cs__kv-row"><span class="cs__kv-k">版本</span><span class="cs__kv-v">v4.0.0</span></div>
          <div class="cs__kv-row"><span class="cs__kv-k">前端技术栈</span><span class="cs__kv-v">Vue 3 + Element Plus + Pinia</span></div>
          <div class="cs__kv-row"><span class="cs__kv-k">后端技术栈</span><span class="cs__kv-v">FastAPI + LangGraph Multi-Agent</span></div>
        </div>
      </div>
    </div>

    <!-- ── Tab: User Management ─────────────────────────────── -->
    <div v-if="activeTab === 'users'" class="cs__section">
      <div class="cs__sec-bar">
        <span class="cs__sec-title">用户列表 <span class="cs__badge">{{ users.length }}</span></span>
        <V2Button variant="primary" size="sm" @click="showAddUser = true">新增用户</V2Button>
      </div>
      <div class="cs__table-wrap">
        <table class="cs__table">
          <thead>
            <tr><th>用户名</th><th>显示名</th><th>角色</th><th>状态</th><th>最近登录</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="row in users" :key="row.username">
              <td>{{ row.username }}</td>
              <td>{{ row.display_name }}</td>
              <td><span class="cs__role-chip" :class="'cs__role-chip--' + row.role">{{ roleMap[row.role] || row.role }}</span></td>
              <td><span class="cs__dot" :class="row.is_active ? 'cs__dot--on' : 'cs__dot--off'" />{{ row.is_active ? '启用' : '停用' }}</td>
              <td class="cs__mono">{{ row.last_login }}</td>
              <td>
                <button class="cs__link" @click="editUser(row)">编辑</button>
                <button class="cs__link" :class="row.is_active ? 'cs__link--danger' : 'cs__link--success'" @click="toggleUser(row)">{{ row.is_active ? '停用' : '启用' }}</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <V2Drawer v-model="showAddUser" :title="editingUser ? '编辑用户' : '新增用户'" size="sm">
        <div class="cs__form">
          <label class="cs__form-label">用户名</label>
          <V2Input v-model="userForm.username" :disabled="!!editingUser" size="sm" />
          <label class="cs__form-label">显示名</label>
          <V2Input v-model="userForm.display_name" size="sm" />
          <label class="cs__form-label">角色</label>
          <V2Select v-model="userForm.role" :options="roleOptions" size="sm" />
          <template v-if="!editingUser">
            <label class="cs__form-label">密码</label>
            <V2Input v-model="userForm.password" type="password" size="sm" />
          </template>
        </div>
        <template #footer>
          <V2Button variant="ghost" size="sm" @click="showAddUser = false">取消</V2Button>
          <V2Button variant="primary" size="sm" @click="saveUser">{{ editingUser ? '更新' : '创建' }}</V2Button>
        </template>
      </V2Drawer>
    </div>

    <!-- ── Tab: Role & Permissions ──────────────────────────── -->
    <div v-if="activeTab === 'roles'" class="cs__section">
      <div class="cs__sec-bar">
        <span class="cs__sec-title">角色定义</span>
      </div>
      <div class="cs__roles-grid">
        <div v-for="r in rolesConfig" :key="r.key" class="cs__role-card">
          <div class="cs__role-hd">
            <span class="cs__role-chip cs__role-chip--lg" :class="'cs__role-chip--' + r.key">{{ r.label }}</span>
            <span class="cs__role-key">{{ r.key }}</span>
          </div>
          <div class="cs__role-desc">{{ r.description }}</div>
          <div class="cs__role-perms">
            <div class="cs__perm-label">权限</div>
            <div class="cs__perm-tags">
              <span v-for="p in r.permissions" :key="p" class="cs__perm-tag">{{ permLabel(p) }}</span>
            </div>
          </div>
          <div class="cs__role-groups">
            <div class="cs__perm-label">可访问模块</div>
            <div class="cs__perm-tags">
              <span v-for="g in r.groups" :key="g" class="cs__perm-tag cs__perm-tag--grp">{{ groupLabel(g) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Tab: Environment ─────────────────────────────────── -->
    <div v-if="activeTab === 'env'" class="cs__section">
      <div class="cs__sec-bar">
        <span class="cs__sec-title">环境配置</span>
      </div>
      <div class="cs__env-grid">
        <div class="cs__card">
          <div class="cs__card-title">后端服务</div>
          <div class="cs__kv">
            <div class="cs__kv-row"><span class="cs__kv-k">API 基础路径</span><span class="cs__kv-v cs__mono">/api/v1</span></div>
            <div class="cs__kv-row"><span class="cs__kv-k">管理后台路径</span><span class="cs__kv-v cs__mono">/admin</span></div>
            <div class="cs__kv-row"><span class="cs__kv-k">SSE 工作流</span><span class="cs__kv-v cs__mono">/api/v1/workflows/{run_id}/stream</span></div>
            <div class="cs__kv-row"><span class="cs__kv-k">SSE 对话</span><span class="cs__kv-v cs__mono">/api/chat/stream</span></div>
          </div>
        </div>
        <div class="cs__card">
          <div class="cs__card-title">基础设施</div>
          <div class="cs__kv">
            <div class="cs__kv-row"><span class="cs__kv-k">MySQL</span><span class="cs__kv-v" :class="envHealth.mysql === '已连接' ? 'cs__kv-v--ok' : 'cs__kv-v--err'">{{ envHealth.mysql }}</span></div>
            <div class="cs__kv-row"><span class="cs__kv-k">Redis</span><span class="cs__kv-v" :class="envHealth.redis === '已连接' ? 'cs__kv-v--ok' : 'cs__kv-v--err'">{{ envHealth.redis }}</span></div>
            <div class="cs__kv-row"><span class="cs__kv-k">PostgreSQL</span><span class="cs__kv-v" :class="envHealth.postgres === '已连接' ? 'cs__kv-v--ok' : 'cs__kv-v--err'">{{ envHealth.postgres }}</span></div>
            <div class="cs__kv-row"><span class="cs__kv-k">LLM 模型</span><span class="cs__kv-v">{{ envHealth.llm_model }}</span></div>
          </div>
        </div>
        <div class="cs__card">
          <div class="cs__card-title">功能开关</div>
          <div class="cs__pref-row"><span>模拟数据</span><V2Toggle v-model="flags.mockData" disabled /></div>
          <div class="cs__pref-row"><span>SSE 实时推送</span><V2Toggle v-model="flags.sseEnabled" disabled /></div>
          <div class="cs__pref-row"><span>LLM 增强路由</span><V2Toggle v-model="flags.llmRouting" disabled /></div>
          <div class="cs__pref-row"><span>HITL 自动创建</span><V2Toggle v-model="flags.hitlAuto" disabled /></div>
          <div class="cs__notice">功能开关由后端 .env 配置控制，此处仅为只读展示。</div>
        </div>
        <div class="cs__card">
          <div class="cs__card-title">部署信息</div>
          <div class="cs__kv">
            <div class="cs__kv-row"><span class="cs__kv-k">运行环境</span><span class="cs__kv-v">{{ envLabel(envHealth.environment) }}</span></div>
            <div class="cs__kv-row"><span class="cs__kv-k">服务器</span><span class="cs__kv-v cs__mono">{{ envHealth.server }}</span></div>
            <div class="cs__kv-row"><span class="cs__kv-k">运行状态</span><span class="cs__kv-v">{{ envHealth.uptime }}</span></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/useAuthStore'
import V2Button from '@/components/v2/V2Button.vue'
import V2Input from '@/components/v2/V2Input.vue'
import V2Select from '@/components/v2/V2Select.vue'
import V2Drawer from '@/components/v2/V2Drawer.vue'
import V2Segment from '@/components/v2/V2Segment.vue'
import V2Toggle from '@/components/v2/V2Toggle.vue'
import { requestAdmin } from '@/api/request'

const router = useRouter()
const auth = useAuthStore()
const username = computed(() => auth.username || '未知')
const roleLabel = computed(() => auth.roleLabel || '未知')

const activeTab = ref('profile')
const tabs = [
  { key: 'profile', label: '个人信息' },
  { key: 'users',   label: '用户管理' },
  { key: 'roles',   label: '角色权限' },
  { key: 'env',     label: '环境配置' },
]

const density = ref(localStorage.getItem('tableDensity') || 'default')
const tz = ref('Asia/Shanghai')

function saveDensity(val) { localStorage.setItem('tableDensity', val) }
function doLogout() { if (!confirm('确定要退出登录吗？')) return; auth.logout(); router.push('/login') }

// ── User Management ────────────────────────────────────────
const roleMap = {
  super_admin: '超级管理员',
  platform_admin: '平台管理员',
  business_admin: '业务管理员',
  ops_analyst: '运维分析师',
  risk_reviewer: '风控审核员',
  service_agent: '客服专员',
  auditor: '审计员',
}
const roleOptions = Object.entries(roleMap).map(([value, label]) => ({ value, label }))

const users = ref([
  { username: 'admin', display_name: '管理员', role: 'super_admin', is_active: true, last_login: '2026-04-04 20:30' },
  { username: 'biz_admin', display_name: '业务主管刘海', role: 'business_admin', is_active: true, last_login: '2026-04-03 18:10' },
  { username: 'analyst01', display_name: '分析师小王', role: 'ops_analyst', is_active: true, last_login: '2026-04-03 14:20' },
  { username: 'reviewer01', display_name: '审核员小李', role: 'risk_reviewer', is_active: true, last_login: '2026-04-02 09:15' },
  { username: 'agent01', display_name: '客服小张', role: 'service_agent', is_active: true, last_login: '2026-04-04 16:40' },
  { username: 'auditor01', display_name: '审计员小陈', role: 'auditor', is_active: true, last_login: '2026-04-01 11:05' },
])

const showAddUser = ref(false)
const editingUser = ref(null)
const userForm = reactive({ username: '', display_name: '', role: 'service_agent', password: '' })

function editUser(row) {
  editingUser.value = row
  Object.assign(userForm, { username: row.username, display_name: row.display_name, role: row.role, password: '' })
  showAddUser.value = true
}

function saveUser() {
  if (editingUser.value) {
    Object.assign(editingUser.value, { display_name: userForm.display_name, role: userForm.role })
  } else {
    if (!userForm.username.trim()) { alert('请填写用户名'); return }
    users.value.push({ ...userForm, is_active: true, last_login: '-' })
  }
  showAddUser.value = false
  editingUser.value = null
  Object.assign(userForm, { username: '', display_name: '', role: 'service_agent', password: '' })
}

function toggleUser(row) {
  row.is_active = !row.is_active
}

// ── Roles Config ───────────────────────────────────────────
const rolesConfig = [
  { key: 'super_admin', label: '超级管理员', description: '全局最高权限，可管理用户、角色、所有治理模块',
    permissions: ['user_manage', 'role_manage', 'policy_write', 'prompt_publish', 'release_manage', 'review_all', 'trace_all', 'audit_read'],
    groups: ['business', 'console'] },
  { key: 'business_admin', label: '业务管理员', description: '可访问所有业务模块和大部分治理功能',
    permissions: ['policy_read', 'prompt_publish', 'review_all', 'trace_all', 'eval_manage'],
    groups: ['business', 'console'] },
  { key: 'ops_analyst', label: '运维分析师', description: '专注于 Trace、Eval、Prompt 调试和 Ops Copilot',
    permissions: ['trace_all', 'eval_manage', 'prompt_read', 'ops_copilot'],
    groups: ['console'] },
  { key: 'risk_reviewer', label: '风控审核员', description: '负责 HITL 审核队列和风控业务页面',
    permissions: ['review_own', 'trace_read', 'fraud_access'],
    groups: ['business', 'console'] },
  { key: 'service_agent', label: '客服专员', description: '仅可使用 OpenClaw 客服和知识库',
    permissions: ['chat_access', 'knowledge_read'],
    groups: ['business'] },
  { key: 'auditor', label: '审计员', description: '只读访问审计日志和 Trace',
    permissions: ['audit_read', 'trace_read'],
    groups: ['console'] },
]

// ── 权限、模块、环境标签映射 ─────────────────────
const PERM_LABELS = {
  user_manage: '用户管理', role_manage: '角色管理', policy_write: '策略写入', policy_read: '策略只读',
  prompt_publish: 'Prompt 发布', prompt_read: 'Prompt 只读', release_manage: '发布管理',
  review_all: '全部审核', review_own: '本人审核', trace_all: 'Trace 全部', trace_read: 'Trace 只读',
  audit_read: '审计只读', eval_manage: '评测管理', ops_copilot: 'Ops Copilot',
  chat_access: '客服对话', knowledge_read: '知识库只读', fraud_access: '风控访问',
}
function permLabel(p) { return PERM_LABELS[p] || p }

const GROUP_LABELS = { business: '业务模块', console: '治理控制台' }
function groupLabel(g) { return GROUP_LABELS[g] || g }

const ENV_LABELS = { development: '开发环境', production: '生产环境', staging: '预发布环境' }
function envLabel(v) { return ENV_LABELS[v] || v || '-' }

// ── 环境健康 ───────────────────────────────────
const envHealth = reactive({
  mysql: '检测中...', redis: '检测中...', postgres: '检测中...',
  llm_model: 'qwen-plus', environment: 'development', server: 'Docker Compose',
  uptime: '-',
})
const flags = reactive({ mockData: true, sseEnabled: true, llmRouting: true, hitlAuto: true })

onMounted(async () => {
  try {
    const d = await requestAdmin.get('/health')
    envHealth.mysql    = d?.db === 'ok' ? '已连接' : (d?.db || '未知')
    envHealth.redis    = d?.redis === 'ok' ? '已连接' : (d?.redis || '未知')
    envHealth.postgres = '已连接'  // PG 用于 LangGraph checkpoint
    if (d?.env)    envHealth.environment = d.env
    if (d?.status) envHealth.uptime = d.status === 'ok' ? '正常运行' : d.status
    const dd = await requestAdmin.get('/health/deps').catch(() => null)
    if (dd?.mock_data_enabled != null) flags.mockData = dd.mock_data_enabled
  } catch { /* use defaults */ }
})
</script>

<style scoped>
.cs__header {
  display: flex;
  align-items: center;
  gap: var(--v2-space-4);
  margin-bottom: var(--v2-space-4);
}
.cs__title {
  font-size: var(--v2-text-lg);
  font-weight: var(--v2-font-semibold);
  color: var(--v2-text-1);
  margin: 0;
}
.cs__tabs {
  display: flex;
  gap: 2px;
  background: var(--v2-bg-sunken);
  border-radius: var(--v2-radius-md);
  padding: 2px;
}
.cs__tab {
  padding: 5px 14px;
  border: none;
  background: transparent;
  color: var(--v2-text-3);
  font-size: var(--v2-text-sm);
  border-radius: var(--v2-radius-sm);
  cursor: pointer;
  transition: all var(--v2-trans-fast);
}
.cs__tab:hover { color: var(--v2-text-1); }
.cs__tab--active {
  background: var(--v2-bg-card);
  color: var(--v2-text-1);
  font-weight: var(--v2-font-medium);
  box-shadow: 0 1px 2px rgba(0,0,0,.06);
}

.cs__grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
}
.cs__card {
  background: var(--v2-bg-card);
  border: 1px solid var(--v2-border-2);
  border-radius: var(--v2-radius-lg);
  padding: 18px;
}
.cs__card-title {
  font-size: var(--v2-text-sm);
  font-weight: var(--v2-font-semibold);
  color: var(--v2-text-3);
  text-transform: uppercase;
  letter-spacing: .5px;
  margin-bottom: 14px;
}
.cs__kv { display: flex; flex-direction: column; gap: 8px; }
.cs__kv-row { display: flex; justify-content: space-between; font-size: 13px; }
.cs__kv-k { color: var(--v2-text-3); }
.cs__kv-v { color: var(--v2-text-1); font-weight: var(--v2-font-medium); }
.cs__kv-v--ok { color: var(--v2-success); }
.cs__kv-v--err { color: var(--v2-error); }
.cs__mono { font-family: var(--v2-font-mono); font-size: 11px; }
.cs__pref-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: var(--v2-text-base);
  color: var(--v2-text-1);
  margin-bottom: 12px;
}
.cs__notice { font-size: var(--v2-text-xs); color: var(--v2-text-4); margin-top: 6px; }
.cs__shortcuts { display: flex; flex-direction: column; gap: 8px; }
.cs__sc-row {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: var(--v2-text-base);
  color: var(--v2-text-1);
}
.cs__sc-row kbd {
  font-size: var(--v2-text-xs);
  padding: 2px 7px;
  background: var(--v2-bg-sunken);
  border: 1px solid var(--v2-border-1);
  border-radius: var(--v2-radius-sm);
  font-family: var(--v2-font-mono);
  color: var(--v2-text-3);
  min-width: 48px;
  text-align: center;
}

/* ── Sections ───────────────────────────────── */
.cs__section {
  background: var(--v2-bg-card);
  border: 1px solid var(--v2-border-2);
  border-radius: var(--v2-radius-lg);
  padding: var(--v2-space-4);
}
.cs__sec-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--v2-space-3);
}
.cs__sec-title {
  font-size: var(--v2-text-md);
  font-weight: var(--v2-font-semibold);
  color: var(--v2-text-1);
}
.cs__badge {
  font-size: var(--v2-text-xs);
  padding: 0 5px;
  background: var(--v2-bg-sunken);
  color: var(--v2-text-3);
  border-radius: var(--v2-radius-sm);
  margin-left: 6px;
}
.cs__table-wrap { overflow-x: auto; }
.cs__table { width: 100%; border-collapse: collapse; font-size: var(--v2-text-sm); }
.cs__table th { text-align: left; padding: 8px 12px; font-weight: var(--v2-font-semibold); color: var(--v2-text-3); font-size: var(--v2-text-xs); text-transform: uppercase; letter-spacing: .4px; border-bottom: 1px solid var(--v2-border-2); background: var(--v2-bg-sunken); }
.cs__table td { padding: 8px 12px; border-bottom: 1px solid var(--v2-border-2); color: var(--v2-text-1); }
.cs__table tbody tr:hover { background: var(--v2-bg-hover); }
.cs__link { background: none; border: none; padding: 0; font-size: var(--v2-text-xs); color: var(--v2-brand-primary); cursor: pointer; margin-right: 8px; }
.cs__link:hover { text-decoration: underline; }
.cs__link--danger { color: var(--v2-error); }
.cs__link--success { color: var(--v2-success); }
.cs__form { display: flex; flex-direction: column; gap: 10px; }
.cs__form-label { font-size: var(--v2-text-xs); font-weight: var(--v2-font-semibold); color: var(--v2-text-3); text-transform: uppercase; letter-spacing: .4px; }

/* ── Role chips ──────────────────────────────── */
.cs__role-chip {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  font-weight: var(--v2-font-medium);
  background: var(--v2-bg-sunken);
  color: var(--v2-text-2);
}
.cs__role-chip--lg { font-size: 12px; padding: 2px 10px; }
.cs__role-chip--super_admin { background: var(--v2-error-bg); color: var(--v2-error-text); }
.cs__role-chip--business_admin { background: var(--v2-warning-bg); color: var(--v2-warning-text); }
.cs__role-chip--ops_analyst { background: var(--v2-brand-bg); color: var(--v2-brand-primary); }
.cs__role-chip--risk_reviewer { background: var(--v2-ai-purple-bg); color: var(--v2-ai-purple); }
.cs__role-chip--service_agent { background: var(--v2-success-bg); color: var(--v2-success-text); }
.cs__role-chip--auditor { background: var(--v2-bg-sunken); color: var(--v2-text-3); }

.cs__dot {
  display: inline-block;
  width: 6px; height: 6px;
  border-radius: 50%;
  margin-right: 4px;
}
.cs__dot--on { background: var(--v2-success); }
.cs__dot--off { background: var(--v2-gray-300); }

/* ── Roles Grid ──────────────────────────────── */
.cs__roles-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--v2-space-3);
}
.cs__role-card {
  padding: var(--v2-space-4);
  background: var(--v2-bg-sunken);
  border: 1px solid var(--v2-border-2);
  border-radius: var(--v2-radius-lg);
}
.cs__role-hd {
  display: flex;
  align-items: center;
  gap: var(--v2-space-2);
  margin-bottom: 6px;
}
.cs__role-key {
  font-size: 10px;
  color: var(--v2-text-4);
  font-family: var(--v2-font-mono);
}
.cs__role-desc {
  font-size: var(--v2-text-sm);
  color: var(--v2-text-2);
  margin-bottom: var(--v2-space-3);
  line-height: 1.4;
}
.cs__role-perms, .cs__role-groups { margin-bottom: var(--v2-space-2); }
.cs__perm-label {
  font-size: 9px;
  font-weight: var(--v2-font-semibold);
  color: var(--v2-text-4);
  text-transform: uppercase;
  letter-spacing: .4px;
  margin-bottom: 4px;
}
.cs__perm-tags { display: flex; flex-wrap: wrap; gap: 3px; }
.cs__perm-tag {
  font-size: 10px;
  padding: 1px 6px;
  background: var(--v2-brand-bg);
  color: var(--v2-brand-primary);
  border-radius: 3px;
}
.cs__perm-tag--grp {
  background: var(--v2-success-bg);
  color: var(--v2-success-text);
}

/* ── Env Grid ────────────────────────────────── */
.cs__env-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
}

@media (max-width: 900px) {
  .cs__grid, .cs__roles-grid, .cs__env-grid { grid-template-columns: 1fr; }
}
</style>
