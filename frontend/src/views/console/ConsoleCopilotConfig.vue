<template>
  <div class="cop-cfg">
    <!-- Tab Bar -->
    <div class="cop-cfg__tabs">
      <button
        v-for="t in tabs" :key="t.key"
        :class="['cop-cfg__tab', { active: activeTab === t.key }]"
        @click="activeTab = t.key"
      >{{ t.label }}</button>
    </div>

    <!-- Tab: 权限配置 -->
    <div v-if="activeTab === 'permissions'" class="cop-cfg__panel">
      <div class="cop-cfg__toolbar">
        <input
          v-model="filterUser"
          class="cop-cfg__input"
          placeholder="按用户 ID 过滤..."
        />
        <button class="cop-cfg__btn" @click="loadOverrides">刷新</button>
      </div>

      <!-- Skill 矩阵 -->
      <div class="cop-cfg__section-title">已注册技能 ({{ skills.length }})</div>
      <div class="cop-cfg__skills-grid">
        <div v-for="s in skills" :key="s.name" class="cop-cfg__skill-card">
          <div class="cop-cfg__skill-hd">
            <span class="cop-cfg__skill-name">{{ s.display_name }}</span>
            <span class="cop-cfg__skill-badge" v-if="s.ops_only">OPS</span>
            <span class="cop-cfg__skill-badge biz" v-for="m in s.mode" :key="m">{{ m }}</span>
          </div>
          <div class="cop-cfg__skill-desc">{{ s.description }}</div>
          <div class="cop-cfg__skill-roles">
            <span v-for="r in s.required_roles" :key="r" class="cop-cfg__role-chip">{{ r }}</span>
          </div>
        </div>
      </div>

      <!-- 用户级覆盖 -->
      <div class="cop-cfg__section-title">用户级权限覆盖 ({{ overrides.length }})</div>
      <table class="cop-cfg__table" v-if="overrides.length">
        <thead>
          <tr>
            <th>用户</th><th>技能</th><th>状态</th><th>授权人</th><th>原因</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="o in filteredOverrides" :key="o.id">
            <td class="mono">{{ o.user_id }}</td>
            <td>{{ o.skill_name }}</td>
            <td>
              <span :class="['cop-cfg__status', o.enabled ? 'on' : 'off']">
                {{ o.enabled ? '已开放' : '已关闭' }}
              </span>
            </td>
            <td class="mono">{{ o.granted_by }}</td>
            <td>{{ o.reason || '-' }}</td>
            <td>
              <button class="cop-cfg__btn-sm" @click="toggleOverride(o)">
                {{ o.enabled ? '关闭' : '开放' }}
              </button>
              <button class="cop-cfg__btn-sm danger" @click="removeOverride(o)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="cop-cfg__empty">暂无用户级覆盖配置</div>

      <!-- 新增覆盖 -->
      <div class="cop-cfg__add-form">
        <input v-model="newOverride.user_id" class="cop-cfg__input sm" placeholder="用户 ID" />
        <select v-model="newOverride.skill_name" class="cop-cfg__input sm">
          <option value="">选择技能</option>
          <option v-for="s in skills" :key="s.name" :value="s.name">{{ s.display_name }}</option>
        </select>
        <select v-model="newOverride.enabled" class="cop-cfg__input sm">
          <option :value="true">开放</option>
          <option :value="false">关闭</option>
        </select>
        <input v-model="newOverride.reason" class="cop-cfg__input sm" placeholder="原因（可选）" />
        <button class="cop-cfg__btn" @click="addOverride" :disabled="!newOverride.user_id || !newOverride.skill_name">
          添加
        </button>
      </div>
    </div>

    <!-- Tab: 反馈看板 -->
    <div v-if="activeTab === 'feedback'" class="cop-cfg__panel">
      <div class="cop-cfg__toolbar">
        <select v-model="feedbackDays" class="cop-cfg__input sm" @change="loadFeedback">
          <option :value="7">近 7 天</option>
          <option :value="30">近 30 天</option>
          <option :value="90">近 90 天</option>
        </select>
        <button class="cop-cfg__btn" @click="loadFeedback">刷新</button>
      </div>

      <!-- 总览卡片 -->
      <div class="cop-cfg__stats-grid" v-if="feedbackStats.overview">
        <div class="cop-cfg__stat-card">
          <span class="cop-cfg__stat-num">{{ feedbackStats.overview.total }}</span>
          <span class="cop-cfg__stat-label">总回答数</span>
        </div>
        <div class="cop-cfg__stat-card">
          <span class="cop-cfg__stat-num pos">{{ feedbackStats.overview.positive }}</span>
          <span class="cop-cfg__stat-label">👍 好评</span>
        </div>
        <div class="cop-cfg__stat-card">
          <span class="cop-cfg__stat-num neg">{{ feedbackStats.overview.negative }}</span>
          <span class="cop-cfg__stat-label">👎 差评</span>
        </div>
        <div class="cop-cfg__stat-card">
          <span class="cop-cfg__stat-num">{{ feedbackStats.overview.satisfaction_rate }}%</span>
          <span class="cop-cfg__stat-label">满意率</span>
        </div>
        <div class="cop-cfg__stat-card">
          <span class="cop-cfg__stat-num">{{ feedbackStats.overview.avg_latency_ms }}ms</span>
          <span class="cop-cfg__stat-label">平均延迟</span>
        </div>
      </div>

      <!-- Skill 分布 -->
      <div class="cop-cfg__section-title">按技能分布</div>
      <table class="cop-cfg__table" v-if="feedbackStats.by_skill?.length">
        <thead><tr><th>技能</th><th class="num">调用次数</th><th class="num">👍</th><th class="num">👎</th><th class="num">满意率</th></tr></thead>
        <tbody>
          <tr v-for="s in feedbackStats.by_skill" :key="s.skill">
            <td>{{ s.skill }}</td>
            <td class="num">{{ s.count }}</td>
            <td class="num pos">{{ s.positive }}</td>
            <td class="num neg">{{ s.negative }}</td>
            <td class="num">{{ satRate(s.positive, s.negative) }}%</td>
          </tr>
        </tbody>
      </table>

      <!-- 每日趋势 -->
      <div class="cop-cfg__section-title">每日趋势</div>
      <div class="cop-cfg__trend" v-if="feedbackStats.daily_trend?.length">
        <div class="cop-cfg__trend-row" v-for="d in feedbackStats.daily_trend" :key="d.date">
          <span class="cop-cfg__trend-date">{{ d.date }}</span>
          <div class="cop-cfg__trend-bar-wrap">
            <div class="cop-cfg__trend-bar pos" :style="{ width: barWidth(d.positive, trendMax) }"></div>
            <div class="cop-cfg__trend-bar neg" :style="{ width: barWidth(d.negative, trendMax) }"></div>
          </div>
          <span class="cop-cfg__trend-num">{{ d.total }}</span>
        </div>
      </div>

      <!-- 最近差评 -->
      <div class="cop-cfg__section-title">最近差评 ({{ feedbackStats.recent_negative?.length || 0 }})</div>
      <div class="cop-cfg__neg-list">
        <div v-for="n in feedbackStats.recent_negative || []" :key="n.id" class="cop-cfg__neg-item">
          <div class="cop-cfg__neg-hd">
            <span class="mono">{{ n.thread_id?.slice(0, 8) }}</span>
            <span>{{ n.created_at }}</span>
          </div>
          <div class="cop-cfg__neg-content">{{ n.content }}</div>
          <div class="cop-cfg__neg-fb" v-if="n.feedback_text">💬 {{ n.feedback_text }}</div>
        </div>
      </div>
    </div>

    <!-- Tab: 对话搜索 -->
    <div v-if="activeTab === 'search'" class="cop-cfg__panel">
      <div class="cop-cfg__toolbar">
        <input
          v-model="searchQuery"
          class="cop-cfg__input"
          placeholder="搜索对话内容..."
          @keydown.enter="doSearch"
        />
        <select v-model="searchMode" class="cop-cfg__input sm">
          <option value="">全部</option>
          <option value="ops">运维</option>
          <option value="biz">运营</option>
        </select>
        <button class="cop-cfg__btn" @click="doSearch" :disabled="!searchQuery">搜索</button>
      </div>

      <div class="cop-cfg__search-results">
        <div v-for="r in searchResults" :key="r.message_id" class="cop-cfg__search-item">
          <div class="cop-cfg__search-hd">
            <span :class="['cop-cfg__search-role', r.role]">{{ r.role }}</span>
            <span class="cop-cfg__search-mode">{{ r.mode }}</span>
            <span class="cop-cfg__search-thread mono">{{ r.thread_id?.slice(0, 8) }}</span>
            <span>{{ r.thread_title || '无标题' }}</span>
            <span class="cop-cfg__search-time">{{ r.created_at }}</span>
          </div>
          <div class="cop-cfg__search-content">{{ r.content }}</div>
        </div>
        <div v-if="searchResults.length === 0 && searchDone" class="cop-cfg__empty">
          未找到匹配结果
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { getSkillList, listOverrides, setOverride, deleteOverride, getFeedbackStats, searchConversations } from '@/api/admin/copilotConfig'

const tabs = [
  { key: 'permissions', label: '权限配置' },
  { key: 'feedback', label: '反馈看板' },
  { key: 'search', label: '对话搜索' },
]
const activeTab = ref('permissions')

// ── 权限 ──
const skills = ref([])
const overrides = ref([])
const filterUser = ref('')
const newOverride = ref({ user_id: '', skill_name: '', enabled: true, reason: '' })

const filteredOverrides = computed(() => {
  if (!filterUser.value) return overrides.value
  return overrides.value.filter(o => o.user_id.includes(filterUser.value))
})

async function loadSkills() {
  try {
    const res = await getSkillList()
    skills.value = res.skills || []
  } catch { /* */ }
}

async function loadOverrides() {
  try {
    const res = await listOverrides()
    overrides.value = res.overrides || []
  } catch { /* */ }
}

async function addOverride() {
  const o = newOverride.value
  if (!o.user_id || !o.skill_name) return
  await setOverride(o.user_id, o.skill_name, o.enabled, o.reason)
  newOverride.value = { user_id: '', skill_name: '', enabled: true, reason: '' }
  await loadOverrides()
}

async function toggleOverride(o) {
  await setOverride(o.user_id, o.skill_name, !o.enabled, o.reason)
  await loadOverrides()
}

async function removeOverride(o) {
  await deleteOverride(o.user_id, o.skill_name)
  await loadOverrides()
}

// ── 反馈 ──
const feedbackDays = ref(30)
const feedbackStats = ref({})

const trendMax = computed(() => {
  const arr = feedbackStats.value.daily_trend || []
  return Math.max(...arr.map(d => d.total), 1)
})

function satRate(pos, neg) {
  return ((pos / Math.max(pos + neg, 1)) * 100).toFixed(1)
}
function barWidth(val, max) {
  return (val / Math.max(max, 1) * 100) + '%'
}

async function loadFeedback() {
  try { feedbackStats.value = await getFeedbackStats(feedbackDays.value) } catch { /* */ }
}

// ── 搜索 ──
const searchQuery = ref('')
const searchMode = ref('')
const searchResults = ref([])
const searchDone = ref(false)

async function doSearch() {
  if (!searchQuery.value) return
  searchDone.value = false
  try {
    const res = await searchConversations(searchQuery.value, searchMode.value)
    searchResults.value = res.results || []
  } catch { searchResults.value = [] }
  searchDone.value = true
}

onMounted(() => {
  loadSkills()
  loadOverrides()
  loadFeedback()
})
</script>

<style scoped>
.cop-cfg { padding: 24px 32px; max-width: 1200px; }

/* Tabs */
.cop-cfg__tabs { display: flex; gap: 0; border-bottom: 1px solid rgba(0,0,0,0.08); margin-bottom: 24px; }
.cop-cfg__tab {
  padding: 10px 20px; font-size: 13px; font-weight: 500; color: #71717a;
  background: none; border: none; cursor: pointer; border-bottom: 2px solid transparent;
  transition: all 0.15s;
}
.cop-cfg__tab:hover { color: #18181b; }
.cop-cfg__tab.active { color: #18181b; border-bottom-color: #18181b; }

/* Toolbar */
.cop-cfg__toolbar { display: flex; gap: 8px; margin-bottom: 16px; align-items: center; }
.cop-cfg__input {
  padding: 7px 12px; font-size: 13px; border: 1px solid rgba(0,0,0,0.1);
  border-radius: 6px; background: #fff; color: #18181b; outline: none;
  transition: border-color 0.15s;
}
.cop-cfg__input:focus { border-color: #18181b; }
.cop-cfg__input.sm { max-width: 160px; }

.cop-cfg__btn {
  padding: 7px 16px; font-size: 13px; font-weight: 500;
  background: #18181b; color: #fff; border: none; border-radius: 6px; cursor: pointer;
}
.cop-cfg__btn:disabled { opacity: 0.4; cursor: not-allowed; }
.cop-cfg__btn-sm {
  padding: 3px 10px; font-size: 12px; background: none; border: 1px solid rgba(0,0,0,0.12);
  border-radius: 4px; cursor: pointer; color: #52525b;
}
.cop-cfg__btn-sm.danger { color: #dc2626; border-color: #fecaca; }

/* Section */
.cop-cfg__section-title { font-size: 14px; font-weight: 600; color: #18181b; margin: 20px 0 12px; }

/* Skills Grid */
.cop-cfg__skills-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 12px; }
.cop-cfg__skill-card {
  padding: 14px 16px; border: 1px solid rgba(0,0,0,0.06); border-radius: 8px; background: #fafafa;
}
.cop-cfg__skill-hd { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.cop-cfg__skill-name { font-size: 13px; font-weight: 600; color: #18181b; }
.cop-cfg__skill-badge {
  font-size: 10px; padding: 1px 6px; border-radius: 3px;
  background: rgba(0,0,0,0.06); color: #52525b; text-transform: uppercase;
}
.cop-cfg__skill-desc { font-size: 12px; color: #71717a; line-height: 1.4; margin-bottom: 8px; }
.cop-cfg__skill-roles { display: flex; flex-wrap: wrap; gap: 4px; }
.cop-cfg__role-chip {
  font-size: 10px; padding: 2px 6px; border-radius: 3px;
  background: rgba(0,0,0,0.04); color: #71717a;
}

/* Table */
.cop-cfg__table { width: 100%; border-collapse: collapse; font-size: 13px; }
.cop-cfg__table th { text-align: left; padding: 8px 12px; font-weight: 500; color: #71717a; border-bottom: 1px solid rgba(0,0,0,0.08); }
.cop-cfg__table td { padding: 8px 12px; border-bottom: 1px solid rgba(0,0,0,0.04); }
.cop-cfg__table .num { text-align: right; font-variant-numeric: tabular-nums; }
.cop-cfg__table .pos { color: #16a34a; }
.cop-cfg__table .neg { color: #dc2626; }

.cop-cfg__status { font-size: 12px; font-weight: 500; }
.cop-cfg__status.on { color: #16a34a; }
.cop-cfg__status.off { color: #dc2626; }

.cop-cfg__empty { padding: 24px; text-align: center; color: #a1a1aa; font-size: 13px; }
.cop-cfg__add-form { display: flex; gap: 8px; margin-top: 16px; align-items: center; flex-wrap: wrap; }

/* Stats */
.cop-cfg__stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 12px; margin-bottom: 20px; }
.cop-cfg__stat-card { padding: 16px; background: #fafafa; border-radius: 8px; border: 1px solid rgba(0,0,0,0.06); }
.cop-cfg__stat-num { font-size: 24px; font-weight: 600; color: #18181b; font-variant-numeric: tabular-nums; display: block; }
.cop-cfg__stat-num.pos { color: #16a34a; }
.cop-cfg__stat-num.neg { color: #dc2626; }
.cop-cfg__stat-label { font-size: 12px; color: #71717a; margin-top: 4px; display: block; }

/* Trend */
.cop-cfg__trend { display: flex; flex-direction: column; gap: 4px; }
.cop-cfg__trend-row { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.cop-cfg__trend-date { width: 80px; color: #71717a; font-variant-numeric: tabular-nums; flex-shrink: 0; }
.cop-cfg__trend-bar-wrap { flex: 1; display: flex; gap: 2px; height: 16px; background: rgba(0,0,0,0.02); border-radius: 2px; overflow: hidden; }
.cop-cfg__trend-bar { height: 100%; border-radius: 2px; transition: width 0.3s; }
.cop-cfg__trend-bar.pos { background: #16a34a; }
.cop-cfg__trend-bar.neg { background: #dc2626; }
.cop-cfg__trend-num { width: 32px; text-align: right; color: #52525b; font-variant-numeric: tabular-nums; }

/* Negative list */
.cop-cfg__neg-list { display: flex; flex-direction: column; gap: 8px; }
.cop-cfg__neg-item { padding: 12px 16px; border: 1px solid rgba(0,0,0,0.06); border-radius: 8px; background: #fffbfb; }
.cop-cfg__neg-hd { display: flex; gap: 12px; font-size: 12px; color: #71717a; margin-bottom: 6px; }
.cop-cfg__neg-content { font-size: 13px; color: #18181b; line-height: 1.5; }
.cop-cfg__neg-fb { font-size: 12px; color: #dc2626; margin-top: 6px; }

/* Search */
.cop-cfg__search-results { display: flex; flex-direction: column; gap: 8px; }
.cop-cfg__search-item { padding: 12px 16px; border: 1px solid rgba(0,0,0,0.06); border-radius: 8px; }
.cop-cfg__search-hd { display: flex; gap: 8px; font-size: 12px; color: #71717a; margin-bottom: 6px; align-items: center; }
.cop-cfg__search-role { font-weight: 500; text-transform: uppercase; }
.cop-cfg__search-role.user { color: #2563eb; }
.cop-cfg__search-role.assistant { color: #16a34a; }
.cop-cfg__search-mode { padding: 1px 6px; background: rgba(0,0,0,0.04); border-radius: 3px; }
.cop-cfg__search-thread { color: #a1a1aa; }
.cop-cfg__search-time { margin-left: auto; }
.cop-cfg__search-content { font-size: 13px; color: #18181b; line-height: 1.5; }

.mono { font-family: 'Geist Mono', monospace; }
</style>
