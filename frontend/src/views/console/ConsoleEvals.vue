<template>
  <div class="ce page-enter-active">
    <header class="ce-hd">
      <div>
        <h1 class="v2-title">评测中心</h1>
        <p class="v2-mono-meta">AI Agent 自动化评测 · 自进化 · 轨迹记忆</p>
      </div>
      <div class="ce-hd__actions">
        <div class="ce-tabs">
          <button v-for="tab in tabs" :key="tab.key" class="ce-tab"
            :class="{ 'is-active': activeTab === tab.key }" @click="activeTab = tab.key">
            {{ tab.label }}
          </button>
        </div>
      </div>
    </header>

    <!-- ═══ Tab 0: Benchmark 综合面板 ═══ -->
    <div class="ce-bd" v-if="activeTab === 'benchmark'">
      <BenchmarkDashboard />
    </div>

    <!-- ═══ Tab 1: 实验竞技场（Karpathy Loop） ═══ -->
    <div class="ce-bd" v-if="activeTab === 'arena'">
      <div class="ce-arena-top">
        <!-- Agent Selector + Golden Set -->
        <div class="v2-hairline-card ce-arena-ctrl">
          <div class="ce-ctrl-row">
            <label class="v2-mono-meta">Agent</label>
            <select v-model="arena.agentName" class="ce-select">
              <option value="">选择被测 Agent</option>
              <option v-for="a in agentList" :key="a" :value="a">{{ a }}</option>
            </select>
          </div>
          <div class="ce-ctrl-row">
            <label class="v2-mono-meta">Golden Set</label>
            <select v-model="arena.datasetId" class="ce-select">
              <option value="">选择数据集</option>
              <option v-for="d in datasets" :key="d.id" :value="d.id">{{ d.name }}</option>
            </select>
          </div>
          <div class="ce-ctrl-row">
            <label class="v2-mono-meta">评估器</label>
            <select v-model="arena.evaluatorId" class="ce-select">
              <option value="">选择评估器</option>
              <option v-for="ev in evaluators" :key="ev.id" :value="ev.id">{{ ev.name }}</option>
            </select>
          </div>
          <div class="ce-ctrl-row">
            <label class="v2-mono-meta">轮次上限</label>
            <input v-model.number="arena.maxIter" type="number" min="1" max="20" class="ce-input" />
          </div>
          <button class="ce-btn-primary" :disabled="arena.running || !arena.agentName || !arena.datasetId || !arena.evaluatorId" @click="startKarpathyLoop">
            {{ arena.running ? '运行中...' : '开始实验循环' }}
          </button>
          <div v-if="!datasets.length || !evaluators.length" class="v2-mono-meta" style="font-size:11px; line-height:1.4; color:var(--v2-warning);">
            {{ !datasets.length ? '⚠ 无数据集，请先在「趋势总览」创建' : '' }}
            {{ !evaluators.length ? '⚠ 无评估器，请先创建评估器' : '' }}
          </div>
        </div>

        <!-- Hill Climb Chart Area -->
        <div class="v2-hairline-card ce-chart-card">
          <div class="ce-chart-header">
            <span class="v2-mono-meta">爬山曲线</span>
            <div class="ce-odometer">
              <span class="v2-mono-meta">最优指标</span>
              <span class="ce-odometer-val">{{ arena.bestMetric.toFixed(4) }}</span>
            </div>
          </div>
          <canvas ref="hillClimbCanvas" class="ce-canvas" width="800" height="260"></canvas>
        </div>
      </div>

      <!-- Experiment Timeline (Git-style) -->
      <div class="v2-hairline-card ce-timeline-card">
        <div class="v2-mono-meta" style="padding: 16px 24px; border-bottom: var(--v2-border-width) solid var(--v2-border-2);">
          实验历史 ({{ arena.iterations.length }} 轮)
        </div>
        <div class="ce-timeline-list">
          <div v-for="it in [...arena.iterations].reverse()" :key="it.iteration" class="ce-tl-item" :class="'is-' + it.decision">
            <div class="ce-tl-dot" :class="'is-' + it.decision"></div>
            <div class="ce-tl-body">
              <div class="ce-tl-hd">
                <span class="v2-badge" :class="it.decision === 'keep' ? 'v2-badge--success' : 'v2-badge--error'">{{ it.decision.toUpperCase() }}</span>
                <span class="v2-mono-meta">Round {{ it.iteration }}</span>
                <span class="v2-mono-meta" style="margin-left: auto;">{{ it.duration_ms }}ms</span>
              </div>
              <div class="ce-tl-desc">{{ it.change_desc || '—' }}</div>
              <div class="ce-tl-metric v2-mono">
                {{ it.metric_before.toFixed(4) }} → {{ it.metric_after.toFixed(4) }}
                <span :style="{ color: it.metric_after > it.metric_before ? 'var(--v2-success)' : 'var(--v2-error)' }">
                  ({{ it.metric_after > it.metric_before ? '+' : '' }}{{ (it.metric_after - it.metric_before).toFixed(4) }})
                </span>
              </div>
            </div>
          </div>
          <div v-if="!arena.iterations.length" class="ce-empty">
            <span class="v2-mono-meta">选择 Agent 和 Golden Set 后点击「开始实验循环」</span>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══ Tab 2: Prompt 进化链 ═══ -->
    <div class="ce-bd" v-if="activeTab === 'evolution'">
      <div class="ce-evo-top">
        <div class="v2-hairline-card ce-arena-ctrl">
          <div class="ce-ctrl-row">
            <label class="v2-mono-meta">Skill</label>
            <select v-model="evo.skillName" class="ce-select" @change="loadPromptVersions">
              <option value="">选择被测 Skill</option>
              <option v-for="s in skillList" :key="s" :value="s">{{ s }}</option>
            </select>
          </div>
          <div class="ce-ctrl-row">
            <label class="v2-mono-meta">Golden Set</label>
            <select v-model="evo.datasetId" class="ce-select">
              <option value="">选择数据集</option>
              <option v-for="d in datasets" :key="d.id" :value="d.id">{{ d.name }}</option>
            </select>
          </div>
          <div class="ce-ctrl-row">
            <label class="v2-mono-meta">最大重试</label>
            <input v-model.number="evo.maxRetry" type="number" min="1" max="10" class="ce-input" />
          </div>
          <button class="ce-btn-primary" :disabled="evo.running || !evo.skillName || !evo.datasetId" @click="startEvolution">
            {{ evo.running ? '进化中...' : '启动进化' }}
          </button>
        </div>

        <!-- Prompt Version Timeline (horizontal) -->
        <div class="v2-hairline-card ce-versions-card">
          <div class="v2-mono-meta" style="padding: 12px 24px;">版本历史</div>
          <div class="ce-version-axis">
            <div v-for="v in evo.versions" :key="v.id" class="ce-ver-node" :class="'is-' + v.status"
              @click="evo.selectedVersion = v">
              <div class="ce-ver-dot"></div>
              <span class="v2-mono" style="font-size: 11px;">v{{ v.version }}</span>
              <span class="v2-mono-meta" style="font-size: 10px;">{{ v.avg_score != null ? (v.avg_score * 100).toFixed(1) + '%' : '—' }}</span>
            </div>
            <div v-if="!evo.versions.length" class="ce-empty" style="padding: 24px;">
              <span class="v2-mono-meta">选择 Skill 查看版本历史</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Grader Radar + Detail -->
      <div class="ce-evo-detail" v-if="evo.selectedVersion">
        <div class="v2-hairline-card" style="padding: 24px;">
          <h4 class="v2-mono-meta" style="margin-bottom: 16px;">
            v{{ evo.selectedVersion.version }} 评分详情
            <span class="v2-badge" :class="statusBadgeClass(evo.selectedVersion.status)" style="margin-left: 8px;">{{ evo.selectedVersion.status }}</span>
          </h4>
          <div v-if="evo.selectedVersion.grader_scores" class="ce-grader-bars">
            <div v-for="(score, name) in evo.selectedVersion.grader_scores" :key="name" class="ce-grader-row">
              <span class="v2-mono-meta" style="width: 140px;">{{ name }}</span>
              <div class="ce-score-bar" style="flex: 1;">
                <div class="ce-score-fill" :class="{ 'is-low': score < 0.8 }" :style="{ width: (score * 100) + '%' }"></div>
              </div>
              <span class="v2-mono" style="width: 50px; text-align: right;">{{ (score * 100).toFixed(1) }}%</span>
            </div>
          </div>
          <div v-if="evo.selectedVersion.status === 'testing'" class="ce-approval-actions" style="margin-top: 20px; display: flex; gap: 12px;">
            <button class="ce-btn-primary" @click="approveVersion(evo.selectedVersion.id)">批准上线</button>
            <button class="ce-btn-ghost" @click="rollbackVersion(evo.selectedVersion.id)">回滚</button>
          </div>
        </div>
      </div>

      <!-- Evolution result -->
      <div class="v2-hairline-card" v-if="evo.result" style="padding: 24px;">
        <h4 class="v2-mono-meta" style="margin-bottom: 12px;">进化结果</h4>
        <div class="ce-evo-summary">
          <div class="ce-kpi"><span class="v2-mono-meta">最优版本</span><span class="ce-kpi-val">v{{ evo.result.best_version }}</span></div>
          <div class="ce-kpi"><span class="v2-mono-meta">最优分数</span><span class="ce-kpi-val">{{ (evo.result.best_score * 100).toFixed(1) }}%</span></div>
          <div class="ce-kpi"><span class="v2-mono-meta">通过率</span><span class="ce-kpi-val">{{ (evo.result.pass_rate * 100).toFixed(1) }}%</span></div>
          <div class="ce-kpi"><span class="v2-mono-meta">状态</span><span class="v2-badge v2-badge--warning">{{ evo.result.status }}</span></div>
        </div>
      </div>
    </div>

    <!-- ═══ Tab 3: 轨迹记忆网络 ═══ -->
    <div class="ce-bd" v-if="activeTab === 'memory'">
      <div class="ce-mem-top">
        <!-- Tips Stats -->
        <div class="v2-hairline-card ce-mem-stats">
          <div v-for="s in memory.stats" :key="s.tip_type" class="ce-mem-stat-item">
            <span class="ce-mem-stat-type" :class="'is-' + s.tip_type">{{ tipTypeLabel(s.tip_type) }}</span>
            <span class="ce-kpi-val">{{ s.total }}</span>
            <span class="v2-mono-meta">{{ s.active }} 活跃 · {{ s.total_references }} 引用</span>
          </div>
          <div v-if="!memory.stats.length" class="ce-empty" style="padding: 24px;">
            <span class="v2-mono-meta">暂无 Tips 数据</span>
          </div>
        </div>

        <!-- Tip Retrieval Test -->
        <div class="v2-hairline-card" style="padding: 24px;">
          <h4 class="v2-mono-meta" style="margin-bottom: 12px;">Tips 检索测试</h4>
          <div style="display: flex; gap: 12px;">
            <input v-model="memory.query" class="ce-input" style="flex: 1;" placeholder="输入任务描述来检索相关 Tips..." />
            <button class="ce-btn-primary" @click="retrieveTips" :disabled="!memory.query">检索</button>
          </div>
        </div>
      </div>

      <!-- Tips List -->
      <div class="v2-hairline-card ce-tips-list">
        <div class="v2-mono-meta" style="padding: 16px 24px; border-bottom: var(--v2-border-width) solid var(--v2-border-2); display: flex; justify-content: space-between;">
          <span>Tips ({{ memory.tips.length }})</span>
          <div style="display: flex; gap: 8px;">
            <button v-for="t in ['all','strategy','recovery','optimization']" :key="t"
              class="ce-tab" :class="{ 'is-active': memory.filter === t }" style="font-size: 11px; padding: 3px 10px;"
              @click="memory.filter = t; loadTips()">
              {{ t === 'all' ? '全部' : tipTypeLabel(t) }}
            </button>
          </div>
        </div>
        <div class="ce-tip-rows">
          <div v-for="tip in memory.tips" :key="tip.tip_id" class="ce-tip-row">
            <div class="ce-tip-type-dot" :class="'is-' + tip.tip_type"></div>
            <div class="ce-tip-body">
              <div class="ce-tip-content">{{ tip.content }}</div>
              <div class="v2-mono-meta" style="margin-top: 4px;">
                {{ tipTypeLabel(tip.tip_type) }} · 置信度 {{ (tip.confidence * 100).toFixed(0) }}% · 引用 {{ tip.reference_count }}次
                <span v-if="tip.relevance_score" style="color: var(--v2-text-1);"> · 相关度 {{ (tip.relevance_score * 100).toFixed(1) }}%</span>
              </div>
            </div>
            <button class="ce-toggle" :class="{ 'is-on': tip.is_active }" @click="toggleTip(tip.tip_id)">
              {{ tip.is_active ? 'ON' : 'OFF' }}
            </button>
          </div>
          <div v-if="!memory.tips.length" class="ce-empty" style="padding: 40px;">
            <span class="v2-mono-meta">{{ memory.query ? '无匹配 Tips' : '暂无 Tips 数据' }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══ Tab 4: 趋势总览 ═══ -->
    <div class="ce-bd" v-if="activeTab === 'trends'">
      <!-- KPI Cards -->
      <div class="ce-trend-kpis">
        <div class="v2-hairline-card ce-trend-kpi">
          <span class="v2-mono-meta">总实验数</span>
          <span class="ce-kpi-val">{{ trends.totalExperiments }}</span>
        </div>
        <div class="v2-hairline-card ce-trend-kpi">
          <span class="v2-mono-meta">平均通过率</span>
          <span class="ce-kpi-val">{{ trends.avgPassRate }}%</span>
        </div>
        <div class="v2-hairline-card ce-trend-kpi">
          <span class="v2-mono-meta">Tips 总数</span>
          <span class="ce-kpi-val">{{ trends.totalTips }}</span>
        </div>
        <div class="v2-hairline-card ce-trend-kpi">
          <span class="v2-mono-meta">Prompt 版本</span>
          <span class="ce-kpi-val">{{ trends.totalPromptVersions }}</span>
        </div>
      </div>

      <!-- Pass Rate Heatmap (真实数据) -->
      <div class="v2-hairline-card" style="padding: 24px;">
        <h4 class="v2-mono-meta" style="margin-bottom: 16px;">每日实验通过率（近 30 天）</h4>
        <div class="ce-heatmap-grid">
          <div v-for="day in heatmapDays" :key="day.date"
            class="ce-heatmap-cell" :class="heatmapColorClass(day)"
            :title="heatmapTip(day)">
          </div>
        </div>
        <div class="ce-heatmap-legend">
          <span class="v2-mono-meta" style="font-size: 11px;">少</span>
          <div class="ce-heatmap-cell is-empty" style="width:12px;height:12px;"></div>
          <div class="ce-heatmap-cell is-green-1" style="width:12px;height:12px;"></div>
          <div class="ce-heatmap-cell is-green-2" style="width:12px;height:12px;"></div>
          <div class="ce-heatmap-cell is-green-3" style="width:12px;height:12px;"></div>
          <div class="ce-heatmap-cell is-green-4" style="width:12px;height:12px;"></div>
          <span class="v2-mono-meta" style="font-size: 11px;">多/优</span>
        </div>
      </div>

      <!-- Recent Experiments -->
      <div class="v2-hairline-card ce-list-card" v-loading="loading">
        <div class="ce-list__hd v2-mono-meta">
          <div class="ce-col-id">实验 ID</div>
          <div class="ce-col-name">Agent / Skill</div>
          <div class="ce-col-dataset">数据集</div>
          <div class="ce-col-score">通过率</div>
          <div class="ce-col-time">日期</div>
          <div class="ce-col-status">状态</div>
        </div>
        <div class="ce-row" v-for="e in experiments" :key="e.id" @click="openDetail(e)">
          <div class="ce-col-id v2-mono">{{ (e.experiment_id || e.id || '').substring(0,8) }}</div>
          <div class="ce-col-name">{{ agentLabel(e.agent_name || e.target_id) }}</div>
          <div class="ce-col-dataset v2-mono-meta">{{ e.dataset_id ? e.dataset_id.substring(0,8) : '—' }}</div>
          <div class="ce-col-score">
            <div class="ce-score-wrap" v-if="e.pass_rate != null">
              <span class="v2-mono" :class="{ 'is-low': e.pass_rate < 0.8 }">{{ (e.pass_rate * 100).toFixed(1) }}%</span>
              <div class="ce-score-bar"><div class="ce-score-fill" :class="{ 'is-low': e.pass_rate < 0.8 }" :style="{ width: (e.pass_rate * 100) + '%' }"></div></div>
            </div>
            <span v-else class="v2-mono-meta">—</span>
          </div>
          <div class="ce-col-time v2-mono">{{ formatTime(e.created_at) }}</div>
          <div class="ce-col-status">
            <span class="v2-badge" :class="statusBadgeClass(e.status)">{{ evalStatusLabel(e.status) }}</span>
          </div>
        </div>
        <div v-if="!experiments.length" class="ce-empty"><span class="v2-mono-meta">暂无实验数据</span></div>
      </div>
    </div>

    <!-- ── Experiment Detail Drawer ── -->
    <div class="cr-drawer-overlay" v-if="selectedExp" @click="selectedExp = null"></div>
    <transition name="drawer-slide">
      <div class="cr-drawer v2-hairline-card" v-if="selectedExp" style="width: 700px;">
        <div class="cr-drawer__hd" style="display: flex; justify-content: space-between; align-items: flex-start;">
          <div>
            <h3 class="v2-title" style="font-size: 20px; margin-bottom: 4px;">{{ selectedExp.name || '评估报告' }}</h3>
            <div class="v2-mono-meta" style="display: flex; gap: 8px; flex-wrap: wrap;">
              <span>{{ agentLabel(selectedExp.agent_name || selectedExp.target_id) }}</span>
              <span>·</span>
              <span>{{ formatTime(selectedExp.created_at) }}</span>
              <span v-if="selectedExp.created_by">· {{ selectedExp.created_by }}</span>
            </div>
          </div>
          <button class="ce-btn-ghost" style="padding: 8px;" @click="selectedExp = null">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>
          </button>
        </div>
        <div class="cr-drawer__bd" style="padding: 0;">
          <div class="ce-detail-kpis">
            <div class="ce-kpi">
              <span class="v2-mono-meta">通过率</span>
              <span class="ce-kpi-val" :class="{ 'is-low': selectedExp.pass_rate != null && selectedExp.pass_rate < 0.8 }">
                {{ selectedExp.pass_rate != null ? (selectedExp.pass_rate * 100).toFixed(1) + '%' : '—' }}
              </span>
            </div>
            <div class="ce-kpi">
              <span class="v2-mono-meta">测试用例</span>
              <span class="ce-kpi-val">{{ selectedExp.total_cases || 0 }}</span>
            </div>
            <div class="ce-kpi">
              <span class="v2-mono-meta">状态</span>
              <span class="v2-badge" :class="statusBadgeClass(selectedExp.status)">{{ evalStatusLabel(selectedExp.status) }}</span>
            </div>
          </div>
          <div v-if="selectedExp.results && selectedExp.results.length" class="ce-failures">
            <h4 class="v2-mono-meta" style="padding: 16px 24px; margin: 0; background: var(--v2-bg-hover);">
              用例结果（{{ selectedExp.results.length }} 条）
            </h4>
            <div class="ce-case" v-for="(r, idx) in selectedExp.results" :key="r.case_id || r.id"
              @click.stop="expandedCase === idx ? expandedCase = null : expandedCase = idx"
              style="cursor: pointer;">
              <div class="ce-case-hd">
                <span class="ce-case-idx v2-mono-meta">#{{ idx + 1 }}</span>
                <span class="v2-badge" :class="r.passed ? 'v2-badge--success' : 'v2-badge--error'">{{ r.passed ? '通过' : '未通过' }}</span>
                <span class="v2-mono" style="margin-left: auto;">得分 {{ r.score != null ? (r.score * 100).toFixed(1) + '%' : '—' }}</span>
                <svg :class="{ 'is-expanded': expandedCase === idx }" class="ce-case-arrow" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M6 9l6 6 6-6"/></svg>
              </div>
              <div v-if="expandedCase === idx" class="ce-case-detail">
                <template v-if="parseCaseDetail(r)">
                  <div v-if="parseCaseDetail(r).runner_latency_ms" class="ce-case-meta v2-mono-meta">
                    响应耗时 {{ parseCaseDetail(r).runner_latency_ms }}ms
                    <span v-if="parseCaseDetail(r).tokens_used"> · {{ parseCaseDetail(r).tokens_used }} tokens</span>
                  </div>
                  <div v-if="parseCaseDetail(r).runner_error" class="ce-case-error v2-mono-meta">
                    错误: {{ parseCaseDetail(r).runner_error }}
                  </div>
                  <div v-if="parseCaseDetail(r).grader_reasoning" class="ce-grader-details">
                    <div v-for="(info, gname) in parseCaseDetail(r).grader_reasoning" :key="gname" class="ce-grader-item">
                      <div class="ce-grader-hd">
                        <span class="v2-mono-meta">{{ gname }}</span>
                        <span class="v2-badge" :class="info.passed ? 'v2-badge--success' : 'v2-badge--error'" style="font-size: 10px;">{{ info.passed ? '通过' : '未通过' }}</span>
                        <span class="v2-mono" style="font-size: 12px; margin-left: auto;">{{ (info.score * 100).toFixed(1) }}%</span>
                      </div>
                      <div v-if="info.reasoning" class="ce-grader-reasoning v2-mono-meta">{{ info.reasoning }}</div>
                    </div>
                  </div>
                </template>
                <div v-else class="v2-mono-meta" style="padding: 8px 0;">暂无详细评分数据</div>
              </div>
            </div>
          </div>
          <div v-else class="ce-empty" style="padding: 40px;">
            <span class="v2-mono-meta">暂无用例结果，请先运行实验</span>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch, nextTick } from 'vue'
import { evalsApi } from '@/api/admin/evals'
import BenchmarkDashboard from '@/components/telemetry/BenchmarkDashboard.vue'

const tabs = [
  { key: 'benchmark',  label: 'Benchmark' },
  { key: 'arena',      label: '实验竞技场' },
  { key: 'evolution',  label: 'Prompt 进化' },
  { key: 'memory',     label: '轨迹记忆' },
  { key: 'trends',     label: '趋势总览' },
]
const activeTab = ref('benchmark')
const loading = ref(false)
const experiments = ref([])
const datasets = ref([])
const evaluators = ref([])
const selectedExp = ref(null)
const expandedCase = ref(null)
const hillClimbCanvas = ref(null)

const agentList = ref([
  'customer_agent', 'forecast_agent', 'fraud_agent', 'sentiment_agent',
  'inventory_agent', 'association_agent', 'openclaw_agent',
])
const skillList = ref([
  'inventory', 'forecast', 'sentiment', 'customer_intel', 'fraud',
  'association', 'kb_rag', 'memory', 'trace', 'system',
])

// ── Tab 1: Arena state ──
const arena = reactive({
  agentName: '', datasetId: '', evaluatorId: '', maxIter: 5,
  running: false, bestMetric: 0, iterations: [],
})

// ── Tab 2: Evolution state ──
const evo = reactive({
  skillName: '', datasetId: '', maxRetry: 3,
  running: false, versions: [], selectedVersion: null, result: null,
})

// ── Tab 3: Memory state ──
const memory = reactive({
  stats: [], tips: [], query: '', filter: 'all',
})

// ── Tab 4: Trends state ──
const trends = reactive({
  totalExperiments: 0, avgPassRate: '—', totalTips: 0, totalPromptVersions: 0,
})

// ── Utils ──
function formatTime(isoStr) {
  if (!isoStr) return '—'
  const d = new Date(isoStr)
  return `${d.getMonth()+1}/${d.getDate()} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
}
const EVAL_STATUS = { completed: '已完成', running: '运行中', pending: '等待中', failed: '失败', pending_approval: '待审批' }
function evalStatusLabel(s) { return EVAL_STATUS[s] || s }
function statusBadgeClass(s) {
  if (s === 'completed' || s === 'approved' || s === 'active') return 'v2-badge--success'
  if (s === 'failed' || s === 'rolled_back') return 'v2-badge--error'
  if (s === 'running' || s === 'testing') return 'v2-badge--warning'
  return 'v2-badge--gray'
}
function tipTypeLabel(t) {
  return { strategy: '策略', recovery: '恢复', optimization: '优化' }[t] || t
}
const AGENT_LABELS = {
  customer_agent: '客户分析',
  forecast_agent: '销量预测',
  fraud_agent: '风控检测',
  sentiment_agent: '舆情分析',
  inventory_agent: '库存管理',
  association_agent: '关联推荐',
  openclaw_agent: '开放问答',
}
function agentLabel(name) {
  if (!name) return '—'
  return AGENT_LABELS[name] || name.replace(/_/g, ' ')
}

const heatmapDays = computed(() => {
  const today = new Date()
  today.setHours(23, 59, 59, 999)
  const days = []
  for (let i = 29; i >= 0; i--) {
    const d = new Date(today)
    d.setDate(d.getDate() - i)
    const dateStr = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
    const dayExps = experiments.value.filter(e => {
      if (!e.created_at) return false
      return String(e.created_at).substring(0, 10) === dateStr
    })
    const withRate = dayExps.filter(e => e.pass_rate != null)
    const avgRate = withRate.length
      ? withRate.reduce((s, e) => s + Number(e.pass_rate), 0) / withRate.length
      : null
    days.push({ date: dateStr, count: dayExps.length, avgRate })
  }
  return days
})

function heatmapColorClass(day) {
  if (!day.count) return 'is-empty'
  if (day.avgRate == null) return 'is-green-1'
  if (day.avgRate >= 0.85) return 'is-green-4'
  if (day.avgRate >= 0.6) return 'is-green-3'
  if (day.avgRate >= 0.3) return 'is-green-2'
  return 'is-green-1'
}

function heatmapTip(day) {
  if (!day.count) return `${day.date}  无实验`
  const rate = day.avgRate != null ? `平均通过率 ${(day.avgRate * 100).toFixed(1)}%` : '暂无通过率'
  return `${day.date}\n${day.count} 个实验\n${rate}`
}

function parseCaseDetail(r) {
  if (!r.detail_json) return null
  if (typeof r.detail_json === 'string') {
    try { return JSON.parse(r.detail_json) } catch { return null }
  }
  return r.detail_json
}

function openDetail(e) {
  selectedExp.value = e
  expandedCase.value = null
  if ((e.experiment_id || e.id) && !e.results) {
    evalsApi.getExperiment(e.experiment_id || e.id).then(r => {
      selectedExp.value = { ...e, ...r }
    }).catch(() => {})
  }
}

// ── Data loading ──
async function loadDatasets() {
  try {
    const r = await evalsApi.getDatasets({ limit: 100 })
    datasets.value = (r.items || []).map(d => ({ id: d.dataset_id || d.id, name: d.name }))
  } catch { datasets.value = [] }
}

async function loadEvaluators() {
  try {
    const r = await evalsApi.getEvaluators({ limit: 100 })
    evaluators.value = (r.items || []).map(e => ({ id: e.evaluator_id || e.id, name: e.name }))
    if (evaluators.value.length && !arena.evaluatorId) arena.evaluatorId = evaluators.value[0].id
  } catch { evaluators.value = [] }
}

async function loadExperiments() {
  loading.value = true
  try {
    const r = await evalsApi.getExperiments({ limit: 50 })
    experiments.value = r.items || []
    trends.totalExperiments = r.total || experiments.value.length
    const rates = experiments.value.filter(e => e.pass_rate != null).map(e => e.pass_rate)
    trends.avgPassRate = rates.length ? (rates.reduce((a, b) => a + b, 0) / rates.length * 100).toFixed(1) : '—'
  } catch { experiments.value = [] }
  loading.value = false
}

async function loadTips() {
  try {
    const params = { limit: 50 }
    if (memory.filter !== 'all') params.tip_type = memory.filter
    const r = await evalsApi.getTips(params)
    memory.tips = r.items || []
  } catch { memory.tips = [] }
}

async function loadTipsStats() {
  try {
    const r = await evalsApi.getTipsStats()
    memory.stats = r.stats || []
    trends.totalTips = memory.stats.reduce((s, x) => s + (x.total || 0), 0)
  } catch { memory.stats = [] }
}

async function loadPromptVersions() {
  if (!evo.skillName) { evo.versions = []; return }
  try {
    const r = await evalsApi.getPromptVersions(evo.skillName)
    evo.versions = r.items || []
    trends.totalPromptVersions = evo.versions.length
  } catch { evo.versions = [] }
}

// ── Actions ──
async function startKarpathyLoop() {
  if (!arena.agentName || !arena.datasetId) return
  arena.running = true
  arena.iterations = []
  arena.bestMetric = 0
  try {
    const evalId = arena.evaluatorId
    if (!evalId) { alert('请先选择评估器'); arena.running = false; return }

    const result = await evalsApi.startKarpathyLoop({
      agent_name: arena.agentName,
      dataset_id: arena.datasetId,
      evaluator_id: evalId,
      max_iterations: arena.maxIter,
    })
    arena.iterations = result.iterations || []
    arena.bestMetric = result.best_metric || 0
    drawHillClimb()
  } catch (err) {
    console.error('[KarpathyLoop]', err)
    alert('实验失败: ' + (err?.response?.data?.message || err.message))
  }
  arena.running = false
}

async function startEvolution() {
  if (!evo.skillName || !evo.datasetId) return
  evo.running = true
  evo.result = null
  try {
    const result = await evalsApi.startEvolution({
      skill_name: evo.skillName,
      dataset_id: evo.datasetId,
      max_retry: evo.maxRetry,
    })
    evo.result = result
    await loadPromptVersions()
  } catch (err) {
    console.error('[Evolution]', err)
    alert('进化失败: ' + (err?.response?.data?.message || err.message))
  }
  evo.running = false
}

async function approveVersion(id) {
  try {
    await evalsApi.approveVersion(id)
    await loadPromptVersions()
  } catch (err) { alert('审批失败: ' + err.message) }
}

async function rollbackVersion(id) {
  try {
    await evalsApi.rollbackVersion(id)
    await loadPromptVersions()
  } catch (err) { alert('回滚失败: ' + err.message) }
}

async function retrieveTips() {
  if (!memory.query) return
  try {
    const r = await evalsApi.retrieveTips({ task_description: memory.query, top_k: 10 })
    memory.tips = r.tips || []
  } catch { memory.tips = [] }
}

async function toggleTip(tipId) {
  try {
    const r = await evalsApi.toggleTip(tipId)
    const tip = memory.tips.find(t => t.tip_id === tipId)
    if (tip) tip.is_active = r.is_active
  } catch {}
}

// ── Canvas: Hill Climb Chart ──
function drawHillClimb() {
  nextTick(() => {
    const canvas = hillClimbCanvas.value
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    const W = canvas.width, H = canvas.height
    const pad = { t: 20, r: 20, b: 30, l: 50 }
    ctx.clearRect(0, 0, W, H)

    const iters = arena.iterations
    if (!iters.length) return

    const metrics = iters.map(it => it.metric_after)
    const minM = Math.min(...metrics, ...iters.map(it => it.metric_before)) * 0.95
    const maxM = Math.max(...metrics, ...iters.map(it => it.metric_before)) * 1.05 || 1

    const xScale = (i) => pad.l + (i / Math.max(iters.length - 1, 1)) * (W - pad.l - pad.r)
    const yScale = (v) => H - pad.b - ((v - minM) / (maxM - minM)) * (H - pad.t - pad.b)

    // Grid
    ctx.strokeStyle = 'rgba(128,128,128,0.15)'
    ctx.lineWidth = 0.5
    for (let i = 0; i <= 4; i++) {
      const y = pad.t + (i / 4) * (H - pad.t - pad.b)
      ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(W - pad.r, y); ctx.stroke()
    }

    // Best line
    ctx.strokeStyle = 'rgba(128,128,128,0.3)'
    ctx.lineWidth = 1
    ctx.setLineDash([4, 4])
    const bestY = yScale(arena.bestMetric)
    ctx.beginPath(); ctx.moveTo(pad.l, bestY); ctx.lineTo(W - pad.r, bestY); ctx.stroke()
    ctx.setLineDash([])

    // Lines + Points
    let prevKeepIdx = null
    iters.forEach((it, i) => {
      const x = xScale(i), y = yScale(it.metric_after)
      const isKeep = it.decision === 'keep'

      // Line from prev keep
      if (prevKeepIdx !== null) {
        const px = xScale(prevKeepIdx), py = yScale(iters[prevKeepIdx].metric_after)
        ctx.strokeStyle = isKeep ? 'rgba(20,20,20,0.6)' : 'rgba(200,50,50,0.3)'
        ctx.lineWidth = isKeep ? 1.5 : 1
        ctx.setLineDash(isKeep ? [] : [3, 3])
        ctx.beginPath(); ctx.moveTo(px, py); ctx.lineTo(x, y); ctx.stroke()
        ctx.setLineDash([])
      }

      // Point
      ctx.beginPath(); ctx.arc(x, y, isKeep ? 5 : 4, 0, Math.PI * 2)
      if (isKeep) {
        ctx.fillStyle = 'rgba(20,20,20,0.8)'; ctx.fill()
        prevKeepIdx = i
      } else {
        ctx.strokeStyle = 'rgba(220,50,50,0.6)'; ctx.lineWidth = 1.5; ctx.stroke()
        // Cross
        ctx.beginPath(); ctx.moveTo(x-3, y-3); ctx.lineTo(x+3, y+3); ctx.moveTo(x+3, y-3); ctx.lineTo(x-3, y+3)
        ctx.strokeStyle = 'rgba(220,50,50,0.4)'; ctx.lineWidth = 1; ctx.stroke()
      }
    })

    // Axis labels
    ctx.fillStyle = 'rgba(128,128,128,0.6)'
    ctx.font = '10px var(--v2-font-mono, monospace)'
    ctx.textAlign = 'center'
    iters.forEach((_, i) => {
      if (i % Math.max(1, Math.floor(iters.length / 8)) === 0)
        ctx.fillText(`R${i+1}`, xScale(i), H - 8)
    })
    ctx.textAlign = 'right'
    for (let i = 0; i <= 4; i++) {
      const v = minM + (1 - i/4) * (maxM - minM)
      ctx.fillText(v.toFixed(3), pad.l - 6, pad.t + (i/4) * (H - pad.t - pad.b) + 3)
    }
  })
}

// ── Init ──
onMounted(async () => {
  await Promise.all([loadDatasets(), loadEvaluators(), loadExperiments(), loadTipsStats()])
})

watch(activeTab, (tab) => {
  if (tab === 'memory') { loadTips(); loadTipsStats() }
  if (tab === 'trends') loadExperiments()
})
</script>

<style scoped>
.ce { display: flex; flex-direction: column; height: calc(100vh - var(--v2-header-height) - var(--v2-space-6) * 2); gap: var(--v2-space-6); max-width: var(--v2-layout-max-width); margin: 0 auto; }
.ce-hd { display: flex; justify-content: space-between; align-items: flex-end; flex-shrink: 0; }
.ce-tabs { display: flex; background: var(--v2-bg-hover); border-radius: var(--v2-radius-btn); padding: 4px; }
.ce-tab { border: none; background: transparent; padding: 6px 16px; border-radius: var(--v2-radius-btn); font-size: 13px; font-weight: 500; color: var(--v2-text-3); cursor: pointer; transition: all var(--v2-trans-fast); }
.ce-tab.is-active { background: var(--v2-bg-card); color: var(--v2-text-1); box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
.ce-bd { flex: 1; display: flex; flex-direction: column; gap: var(--v2-space-6); min-height: 0; overflow-y: auto; }

/* ── Controls ── */
.ce-arena-top, .ce-evo-top, .ce-mem-top { display: flex; gap: var(--v2-space-6); flex-shrink: 0; }
.ce-arena-ctrl { padding: 24px; display: flex; flex-direction: column; gap: 16px; width: 280px; flex-shrink: 0; }
.ce-ctrl-row { display: flex; flex-direction: column; gap: 4px; }
.ce-select, .ce-input { border: var(--v2-border-width) solid var(--v2-border-2); background: var(--v2-bg-sunken); border-radius: var(--v2-radius-btn); padding: 8px 12px; font-size: 13px; font-family: var(--v2-font-mono); color: var(--v2-text-1); outline: none; }
.ce-select:focus, .ce-input:focus { border-color: var(--v2-text-3); }
.ce-btn-primary { border: none; background: var(--v2-text-1); color: var(--v2-bg-card); padding: 10px 20px; border-radius: var(--v2-radius-btn); font-size: 13px; font-weight: 600; cursor: pointer; transition: opacity var(--v2-trans-fast); }
.ce-btn-primary:hover { opacity: 0.85; }
.ce-btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
.ce-btn-ghost { border: var(--v2-border-width) solid var(--v2-border-2); background: transparent; color: var(--v2-text-2); padding: 10px 20px; border-radius: var(--v2-radius-btn); font-size: 13px; cursor: pointer; }

/* ── Chart ── */
.ce-chart-card { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.ce-chart-header { padding: 16px 24px; display: flex; justify-content: space-between; align-items: center; border-bottom: var(--v2-border-width) solid var(--v2-border-2); }
.ce-canvas { width: 100%; height: 260px; }
.ce-odometer { display: flex; align-items: center; gap: 12px; }
.ce-odometer-val { font-family: var(--v2-font-mono); font-size: 28px; font-weight: 700; color: var(--v2-text-1); letter-spacing: -0.03em; }

/* ── Timeline ── */
.ce-timeline-card { flex-shrink: 0; max-height: 300px; overflow: hidden; display: flex; flex-direction: column; }
.ce-timeline-list { overflow-y: auto; flex: 1; }
.ce-tl-item { display: flex; gap: 16px; padding: 16px 24px; border-bottom: var(--v2-border-width) solid var(--v2-border-2); }
.ce-tl-dot { width: 10px; height: 10px; border-radius: 50%; margin-top: 4px; flex-shrink: 0; }
.ce-tl-dot.is-keep { background: var(--v2-success); }
.ce-tl-dot.is-discard { background: var(--v2-error); }
.ce-tl-dot.is-crash { background: var(--v2-warning); }
.ce-tl-body { flex: 1; display: flex; flex-direction: column; gap: 4px; }
.ce-tl-hd { display: flex; align-items: center; gap: 8px; }
.ce-tl-desc { font-size: 13px; color: var(--v2-text-2); }
.ce-tl-metric { font-size: 12px; }

/* ── Versions ── */
.ce-versions-card { flex: 1; }
.ce-version-axis { display: flex; gap: 16px; padding: 16px 24px; overflow-x: auto; }
.ce-ver-node { display: flex; flex-direction: column; align-items: center; gap: 4px; cursor: pointer; padding: 8px 12px; border-radius: var(--v2-radius-btn); transition: background var(--v2-trans-fast); min-width: 56px; }
.ce-ver-node:hover { background: var(--v2-bg-hover); }
.ce-ver-dot { width: 12px; height: 12px; border-radius: 50%; background: var(--v2-text-3); }
.ce-ver-node.is-active .ce-ver-dot { background: var(--v2-success); box-shadow: 0 0 0 3px rgba(34,197,94,0.2); }
.ce-ver-node.is-testing .ce-ver-dot { background: var(--v2-warning); }
.ce-ver-node.is-rolled_back .ce-ver-dot { background: var(--v2-text-4); }
.ce-ver-node.is-approved .ce-ver-dot { background: var(--v2-success); }
.ce-ver-node.is-draft .ce-ver-dot { background: var(--v2-text-3); }

.ce-evo-detail { display: flex; gap: var(--v2-space-6); flex-shrink: 0; }
.ce-evo-detail > * { flex: 1; }
.ce-grader-bars { display: flex; flex-direction: column; gap: 12px; }
.ce-grader-row { display: flex; align-items: center; gap: 12px; }
.ce-evo-summary { display: flex; gap: 32px; flex-wrap: wrap; }

/* ── Memory ── */
.ce-mem-stats { display: flex; gap: 24px; padding: 24px; flex: 1; }
.ce-mem-stat-item { display: flex; flex-direction: column; gap: 6px; }
.ce-mem-stat-type { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
.ce-mem-stat-type.is-strategy { color: var(--v2-text-2); }
.ce-mem-stat-type.is-recovery { color: var(--v2-warning); }
.ce-mem-stat-type.is-optimization { color: var(--v2-text-3); }
.ce-tips-list { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.ce-tip-rows { flex: 1; overflow-y: auto; }
.ce-tip-row { display: flex; align-items: flex-start; gap: 12px; padding: 16px 24px; border-bottom: var(--v2-border-width) solid var(--v2-border-2); }
.ce-tip-type-dot { width: 8px; height: 8px; border-radius: 50%; margin-top: 6px; flex-shrink: 0; }
.ce-tip-type-dot.is-strategy { background: var(--v2-text-2); }
.ce-tip-type-dot.is-recovery { background: var(--v2-warning); }
.ce-tip-type-dot.is-optimization { background: var(--v2-text-3); }
.ce-tip-body { flex: 1; }
.ce-tip-content { font-size: 13px; color: var(--v2-text-1); line-height: 1.5; }
.ce-toggle { border: var(--v2-border-width) solid var(--v2-border-2); background: transparent; padding: 4px 10px; border-radius: var(--v2-radius-btn); font-size: 11px; font-family: var(--v2-font-mono); cursor: pointer; color: var(--v2-text-3); }
.ce-toggle.is-on { color: var(--v2-success); border-color: rgba(34,197,94,0.4); }

/* ── Trends ── */
.ce-trend-kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--v2-space-6); flex-shrink: 0; }
.ce-trend-kpi { padding: 20px 24px; display: flex; flex-direction: column; gap: 8px; }

/* ── Heatmap ── */
.ce-heatmap-grid { display: grid; grid-template-columns: repeat(30, 1fr); gap: 3px; }
.ce-heatmap-cell { aspect-ratio: 1; border-radius: 2px; background: var(--v2-bg-hover); }
.ce-heatmap-cell.is-empty { background: var(--v2-bg-hover); }
.ce-heatmap-cell.is-green-1 { background: rgba(128,128,128,0.15); }
.ce-heatmap-cell.is-green-2 { background: rgba(128,128,128,0.3); }
.ce-heatmap-cell.is-green-3 { background: rgba(128,128,128,0.5); }
.ce-heatmap-cell.is-green-4 { background: rgba(20,20,20,0.7); }
.ce-heatmap-legend { display: flex; align-items: center; gap: 4px; margin-top: 12px; justify-content: flex-end; }

/* ── List ── */
.ce-list-card { flex: 1; display: flex; flex-direction: column; background: var(--v2-bg-card); overflow: hidden; min-height: 200px; }
.ce-list__hd { display: flex; padding: 12px 24px; border-bottom: var(--v2-border-width) solid var(--v2-border-2); background: var(--v2-bg-hover); flex-shrink: 0; }
.ce-row { display: flex; align-items: center; padding: 16px 24px; border-bottom: var(--v2-border-width) solid var(--v2-border-2); cursor: pointer; transition: background var(--v2-trans-fast); }
.ce-row:hover { background: var(--v2-bg-hover); }
.ce-col-id { width: 100px; flex-shrink: 0; color: var(--v2-text-3); }
.ce-col-name { width: 180px; flex-shrink: 0; font-size: 14px; color: var(--v2-text-1); font-weight: 500; }
.ce-col-dataset { flex: 1; min-width: 0; font-size: 13px; color: var(--v2-text-2); }
.ce-col-score { width: 140px; flex-shrink: 0; }
.ce-col-time { width: 100px; flex-shrink: 0; color: var(--v2-text-3); text-align: right; }
.ce-col-status { width: 90px; flex-shrink: 0; text-align: right; }
.ce-score-wrap { display: flex; align-items: center; gap: 8px; }
.ce-score-bar { flex: 1; height: 4px; background: var(--v2-border-2); border-radius: 2px; overflow: hidden; }
.ce-score-fill { height: 100%; background: var(--v2-text-2); border-radius: 2px; transition: width 0.4s ease; }
.ce-score-fill.is-low { background: var(--v2-error); }
.v2-mono.is-low { color: var(--v2-error); }

/* ── Shared ── */
.ce-kpi { display: flex; flex-direction: column; gap: 6px; }
.ce-kpi-val { font-size: 24px; font-weight: 600; font-family: var(--v2-font-mono); color: var(--v2-text-1); }
.ce-empty { display: flex; justify-content: center; align-items: center; padding: 60px; }

/* ── Drawer ── */
.cr-drawer-overlay { position: fixed; inset: 0; z-index: var(--v2-z-drawer, 100); background: rgba(0,0,0,0.4); backdrop-filter: blur(4px); }
.cr-drawer { position: fixed; right: 0; top: 0; bottom: 0; background: var(--v2-bg-card); z-index: calc(var(--v2-z-drawer, 100) + 1); display: flex; flex-direction: column; box-shadow: -10px 0 30px rgba(0,0,0,0.2); }
.drawer-slide-enter-active, .drawer-slide-leave-active { transition: transform 0.35s cubic-bezier(0.16, 1, 0.3, 1); }
.drawer-slide-enter-from, .drawer-slide-leave-to { transform: translateX(100%); }
.cr-drawer__hd { padding: 24px; border-bottom: var(--v2-border-width) solid var(--v2-border-2); }
.cr-drawer__bd { flex: 1; overflow-y: auto; }
.ce-detail-kpis { display: flex; padding: 24px; border-bottom: var(--v2-border-width) solid var(--v2-border-2); gap: 40px; }
.ce-failures { display: flex; flex-direction: column; }
.ce-case { border-bottom: var(--v2-border-width) solid var(--v2-border-2); padding: 16px 24px; display: flex; flex-direction: column; gap: 8px; }
.ce-case-hd { display: flex; align-items: center; gap: 12px; }
.ce-case-idx { margin-right: 4px; }
.ce-case-arrow { margin-left: 8px; transition: transform 0.2s ease; flex-shrink: 0; }
.ce-case-arrow.is-expanded { transform: rotate(180deg); }
.ce-case-detail { padding: 12px 0 4px; border-top: var(--v2-border-width) solid var(--v2-border-2); margin-top: 8px; }
.ce-case-meta { margin-bottom: 8px; }
.ce-case-error { color: var(--v2-error); margin-bottom: 8px; }
.ce-grader-details { display: flex; flex-direction: column; gap: 8px; }
.ce-grader-item { background: var(--v2-bg-sunken); border-radius: var(--v2-radius-btn); padding: 10px 12px; }
.ce-grader-hd { display: flex; align-items: center; gap: 8px; }
.ce-grader-reasoning { margin-top: 6px; font-size: 12px; line-height: 1.5; white-space: pre-wrap; max-height: 120px; overflow-y: auto; }
.ce-kpi-val.is-low { color: var(--v2-error); }
</style>
