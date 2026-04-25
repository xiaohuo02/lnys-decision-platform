<template>
  <div class="ap">
    <PageHeaderV2 title="多智能体工作台" desc="AI 智能体集群 · 工作流编排 · 拓扑可视化">
      <template #actions>
        <div class="ap__hd-actions">
          <!-- View toggle: topology / timeline -->
          <div class="ap__view-toggle" v-if="phase === 'executing'">
            <button class="ap__view-btn" :class="{ 'ap__view-btn--active': viewMode === 'topology' }" @click="viewMode = 'topology'" title="拓扑视图">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="5" cy="6" r="3"/><circle cx="19" cy="6" r="3"/><circle cx="12" cy="18" r="3"/><path d="M7.5 7.5L10.5 16M16.5 7.5L13.5 16"/></svg>
            </button>
            <button class="ap__view-btn" :class="{ 'ap__view-btn--active': viewMode === 'timeline' }" @click="viewMode = 'timeline'" title="时间线视图">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="12" y1="2" x2="12" y2="22"/><circle cx="12" cy="6" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="12" cy="18" r="2"/></svg>
            </button>
          </div>
          <button class="ap__toggle-panel" :class="{ 'ap__toggle-panel--active': showRight }" @click="showRight = !showRight" title="AI 面板">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="3"/><line x1="15" y1="3" x2="15" y2="21"/></svg>
          </button>
        </div>
      </template>
    </PageHeaderV2>

    <SplitInspector :hide-right="!showRight">
      <template #main>
        <div class="ap__main-scroll">
          <!-- ① Setup Card -->
          <SectionCardV2 v-if="phase === 'form'" title="工作流配置">
            <div class="ap__form">
              <div class="ap__form-field">
                <label class="ap__label">工作流策略</label>
                <div class="ap__radio-group">
                  <button class="ap__radio" :class="{ 'ap__radio--active': workflowId === 'business_overview' }" @click="workflowId = 'business_overview'">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
                    业务综述
                  </button>
                  <button class="ap__radio" :class="{ 'ap__radio--active': workflowId === 'risk_review' }" @click="workflowId = 'risk_review'">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                    风险审查
                  </button>
                </div>
              </div>
              <div class="ap__form-field">
                <label class="ap__label">分析提示</label>
                <div class="ap__composer">
                  <textarea class="ap__textarea" v-model="query" placeholder="例如：给我一份昨日销售综述和潜在欺诈风险分析..." rows="3" @keydown.shift.enter.stop @keydown.enter.exact.prevent="enterPreview"></textarea>
                  <div class="ap__composer-ft">
                    <span class="ap__hint">Shift+Enter 换行</span>
                    <button class="ap__submit" :disabled="!query.trim()" @click="enterPreview">
                      <svg v-if="!loading" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                      <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="ap__spin"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>
                      执行分析
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </SectionCardV2>

          <!-- ①½ Plan Preview -->
          <SectionCardV2 v-if="phase === 'preview'">
            <template #header>
              <div class="ap__plan-hd">
                <span class="ap__progress-title">执行计划预览</span>
                <span class="ap__badge ap__badge--idle">{{ planSteps.length }} 步</span>
              </div>
            </template>
            <div class="ap__plan">
              <p class="ap__plan-desc">
                即将执行 <strong>{{ workflowLabel }}</strong> 工作流，包含以下分析步骤：
              </p>
              <div class="ap__plan-steps">
                <div v-for="(step, idx) in planSteps" :key="step.key" class="ap__plan-step">
                  <span class="ap__plan-idx">{{ idx + 1 }}</span>
                  <div class="ap__plan-info">
                    <div class="ap__plan-name">
                      {{ step.name }}
                      <span v-if="step.parallel" class="ap__plan-tag">并行</span>
                    </div>
                    <div class="ap__plan-note">{{ step.desc }}</div>
                  </div>
                </div>
              </div>
              <div v-if="preflightError" class="ap__plan-error">{{ preflightError }}</div>
              <div class="ap__plan-ft">
                <button class="ap__btn" @click="phase = 'form'">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="15 18 9 12 15 6"/></svg>
                  返回修改
                </button>
                <button class="ap__submit" :disabled="loading" @click="startAnalysis">
                  <svg v-if="!loading" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                  <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="ap__spin"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>
                  确认执行
                </button>
              </div>
            </div>
          </SectionCardV2>

          <!-- ② Topology / Timeline Progress -->
          <SectionCardV2 v-if="phase === 'executing'" class="ap__progress-card">
            <template #header>
              <div class="ap__progress-hd">
                <span class="ap__progress-title">执行追踪</span>
                <span class="ap__badge" :class="'ap__badge--' + status">{{ statusText }}</span>
              </div>
            </template>

            <!-- Topology View -->
            <AgentTopologyGraph
              v-if="viewMode === 'topology'"
              :steps="topoSteps"
              :workflow-type="workflowId"
              @node-click="onNodeClick"
            />

            <!-- Timeline View -->
            <div v-else class="ap__timeline">
              <div v-for="(step, idx) in timelineSteps" :key="idx" class="ap__step" :class="'ap__step--' + step.status" @click="onStepClick(step)">
                <div class="ap__step-line" v-if="idx < timelineSteps.length - 1"></div>
                <div class="ap__step-dot">
                  <svg v-if="step.status === 'completed'" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
                  <svg v-else-if="step.status === 'running'" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="ap__spin"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>
                  <svg v-else-if="step.status === 'error'" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </div>
                <div class="ap__step-content">
                  <div class="ap__step-name">
                    {{ step.name }}
                    <span v-if="step.status === 'completed' && confTag(step.confidence)" class="ap__conf" :class="confTag(step.confidence).cls">{{ confTag(step.confidence).icon }} {{ confTag(step.confidence).label }}</span>
                  </div>
                  <div v-if="step.latency" class="ap__step-meta">{{ step.latency }}s</div>
                </div>
              </div>
            </div>

            <!-- Progress bar -->
            <div class="ap__bar" v-if="status === 'running'">
              <div class="ap__bar-fill" :style="{ width: progressPct + '%' }"></div>
            </div>

            <!-- Actions -->
            <div class="ap__progress-ft">
              <button v-if="status === 'running'" class="ap__btn ap__btn--danger" @click="cancelAnalysis">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
                终止执行
              </button>
              <button v-if="status === 'completed' || status === 'error'" class="ap__btn" @click="resetForm">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 102.13-9.36L1 10"/></svg>
                新建分析
              </button>
            </div>
          </SectionCardV2>

          <!-- ③ Result Artifact -->
          <SectionCardV2 v-if="phase === 'executing'" title="执行摘要">
            <template #header>
              <span v-if="status === 'completed' && confTag(overallConfidence)" class="ap__conf ap__conf--pill" :class="confTag(overallConfidence).cls">{{ confTag(overallConfidence).icon }} 综合{{ confTag(overallConfidence).label }}</span>
            </template>
            <div v-if="status === 'running' && !resultContent" class="ap__skeleton">
              <div class="ap__skeleton-line" style="width: 100%"></div>
              <div class="ap__skeleton-line" style="width: 80%"></div>
              <div class="ap__skeleton-line" style="width: 90%"></div>
              <div class="ap__skeleton-line" style="width: 60%"></div>
            </div>
            <MarkdownRenderer v-else-if="resultContent" :content="resultContent" />
            <EmptyStateV2 v-else title="暂无内容生成" />
          </SectionCardV2>
        </div>
      </template>

      <!-- ═══ Right Panel ═══ -->
      <template #right>
        <PageAICopilotPanel
          ref="aiPanel"
          :ai="ai"
          welcome-title="AI 工作流助手"
          welcome-desc="分析步骤解读、结果摘要、策略建议"
          collection="workflow"
          command-bar-placeholder="询问工作流相关问题...  @ 选择智能体"
          :quick-questions="quickQuestions"
          :mention-catalog="mentionCatalog"
        >
          <template #detail>
            <div v-if="selectedStep" class="ap__detail">
              <h4>步骤详情</h4>
              <div class="ap__dl"><span>名称</span><span>{{ selectedStep.name }}</span></div>
              <div class="ap__dl"><span>状态</span><span>{{ selectedStep.status }}</span></div>
              <div class="ap__dl" v-if="selectedStep.latency"><span>耗时</span><span>{{ selectedStep.latency }}s</span></div>
              <div class="ap__dl" v-if="selectedStep.confidence != null"><span>置信度</span><span class="ap__conf" :class="confTag(selectedStep.confidence)?.cls">{{ confTag(selectedStep.confidence)?.icon }} {{ confTag(selectedStep.confidence)?.label }}</span></div>
              <button class="ap__detail-ask" @click="aiPanel?.askAndSwitch(`详细解读「${selectedStep.name}」步骤的执行情况和优化建议`)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
                AI 步骤分析
              </button>
            </div>
            <div v-else class="ap__detail ap__detail--empty">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--v2-text-4)" stroke-width="1"><circle cx="5" cy="6" r="3"/><circle cx="19" cy="6" r="3"/><circle cx="12" cy="18" r="3"/><path d="M7.5 7.5L10.5 16M16.5 7.5L13.5 16"/></svg>
              <p>点击拓扑节点或时间线步骤查看详情</p>
            </div>
          </template>
        </PageAICopilotPanel>
      </template>
    </SplitInspector>
  </div>
</template>

<script>
export default { name: 'AnalyzeProgress' }
</script>
<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import MarkdownRenderer from '@/components/v2/MarkdownRenderer.vue'
import { PageHeaderV2, SectionCardV2, EmptyStateV2, SplitInspector, PageAICopilotPanel, AgentTopologyGraph } from '@/components/v2'
import { usePageCopilot } from '@/composables/usePageCopilot'
import { workflowApi } from '@/api/workflow'
import { useWorkflowStream } from '@/composables/useWorkflowStream'
import { useRunStore } from '@/stores/useRunStore'

const route = useRoute()
const runStore = useRunStore()

// ── AI Copilot ──
const ai = usePageCopilot('workflow', ['kb_rag'])
const aiPanel = ref(null)
const showRight = ref(false)
const selectedStep = ref(null)
const viewMode = ref('topology')

// ── Plan-and-Execute Preview ──
const phase = ref('form')  // 'form' | 'preview' | 'executing'
const preflightError = ref('')

const WORKFLOW_PLANS = {
  business_overview: [
    { key: 'data_preparation', name: '数据准备', desc: '清洗与融合 OMO 多源数据', parallel: false },
    { key: 'customer_intel', name: '客群分析', desc: 'RFM 分群 · 流失预测 · CLV 评估', parallel: true },
    { key: 'sales_forecast', name: '销售预测', desc: '多模型集成预测未来 7 天趋势', parallel: true },
    { key: 'sentiment_intel', name: '舆情分析', desc: '情感分类 · 主题提取 · 负面预警', parallel: true },
    { key: 'fraud_scoring', name: '欺诈风控', desc: '多模型融合欺诈评分 · 高风险标记', parallel: true },
    { key: 'inventory', name: '库存优化', desc: 'ABC-XYZ 分类 · EOQ · 安全库存建议', parallel: false },
    { key: 'insight_composer', name: 'AI 报告合成', desc: 'LLM 综合各维度洞察生成经营报告', parallel: false },
  ],
  risk_review: [
    { key: 'fraud_scoring', name: '欺诈评分', desc: '批量交易风险评分', parallel: false },
    { key: 'prepare_review', name: '风险审查准备', desc: '筛选高风险交易 · 生成审查案例', parallel: false },
    { key: 'hitl_interrupt', name: '人工审核', desc: '暂停等待人工审批决策', parallel: false },
    { key: 'post_review', name: '审核后处理', desc: '执行审批决策 · 记录审计日志', parallel: false },
  ],
}

const planSteps = computed(() => WORKFLOW_PLANS[workflowId.value] || [])
const workflowLabel = computed(() => workflowId.value === 'business_overview' ? '业务综述' : '风险审查')

function enterPreview() {
  if (!query.value.trim()) return
  preflightError.value = ''
  phase.value = 'preview'
}

const quickQuestions = [
  '当前工作流各步骤执行情况总结',
  '哪些步骤耗时最长？有优化空间吗？',
  '分析结果的关键洞察和行动建议',
]

const mentionCatalog = [
  { id: 'forecast', label: '销售预测', type: 'skill', icon: '📈' },
  { id: 'customer_intel', label: '客群洞察', type: 'skill', icon: '👥' },
  { id: 'fraud', label: '风控检测', type: 'skill', icon: '🛡️' },
  { id: 'kb_rag', label: '知识库', type: 'collection', icon: '📚' },
]

function onNodeClick(node) {
  selectedStep.value = node
  showRight.value = true
  aiPanel.value?.switchTab('detail')
}

function onStepClick(step) {
  selectedStep.value = step
  showRight.value = true
  aiPanel.value?.switchTab('detail')
}

// ── Workflow State ──
const workflowId = ref('business_overview')
const query = ref('')
const loading = ref(false)
const resultContent = ref('')
const currentRunId = ref(null)

const stream = useWorkflowStream()

const status = computed(() => {
  const s = stream.status.value
  if (s === 'failed') return 'error'
  if (s === 'connecting') return 'running'
  return s
})

const statusText = computed(() => {
  const m = { idle: '就绪', running: '运行中', completed: '已完成', error: '失败' }
  return m[status.value] || status.value
})

const progressPct = computed(() => stream.progress.value)

// Steps for topology (keep original status)
const topoSteps = computed(() => stream.steps.value)

// Steps for timeline (map failed → error for display)
const timelineSteps = computed(() =>
  stream.steps.value.map(s => ({
    name: s.name,
    status: s.status === 'failed' ? 'error' : (s.status === 'hitl_pending' ? 'running' : s.status),
    latency: s.latency_ms != null ? (s.latency_ms / 1000).toFixed(1) : null,
    confidence: s.confidence ?? null,
  }))
)

// ── Confidence Signal ──
function confTag(val) {
  if (val == null) return null
  if (val > 0.7)  return { label: '高信度', cls: 'ap__conf--high', icon: '✓' }
  if (val >= 0.4) return { label: '需确认', cls: 'ap__conf--mid',  icon: '?' }
  return              { label: '低信度', cls: 'ap__conf--low',  icon: '!' }
}

const overallConfidence = computed(() => {
  const done = stream.steps.value.filter(s => s.status === 'completed' && s.confidence != null)
  if (!done.length) return null
  return done.reduce((sum, s) => sum + s.confidence, 0) / done.length
})

// ── SSE result extraction ──
watch(() => stream.result.value, (res) => {
  if (!res) return
  const parts = []
  if (res.executive_summary) parts.push(`## 执行概述\n\n${res.executive_summary}`)
  if (res.risk_highlights)   parts.push(`### 风险提示\n\n${res.risk_highlights}`)
  if (res.action_plan)       parts.push(`### 行动建议\n\n${res.action_plan}`)
  if (res.summary)           parts.push(res.summary)
  if (res.report)            parts.push(res.report)
  if (res.reply)             parts.push(res.reply)
  resultContent.value = parts.length
    ? parts.join('\n\n')
    : (res.message || JSON.stringify(res, null, 2))
})

watch(() => stream.error.value, (err) => {
  if (err) resultContent.value = `## 执行失败\n\n${err}`
})

// Auto-inject context when workflow completes
watch(status, (s) => {
  if (s === 'completed' && resultContent.value) {
    ai.setContext({
      workflow: workflowId.value,
      steps: timelineSteps.value,
      result_preview: resultContent.value.slice(0, 500),
    })
  }
})

function resetForm() {
  stream.reset()
  query.value = ''
  resultContent.value = ''
  currentRunId.value = null
  selectedStep.value = null
  preflightError.value = ''
  phase.value = 'form'
}

async function cancelAnalysis() {
  if (currentRunId.value) {
    try { await workflowApi.cancel(currentRunId.value) } catch {}
  }
  stream.stop()
  stream.injectEvent('final', { status: 'failed', message: '用户已终止执行' })
}

async function startAnalysis() {
  loading.value = true
  preflightError.value = ''
  selectedStep.value = null
  try {
    const res = await workflowApi.run({
      request_text: query.value,
      request_type: workflowId.value,
      use_mock: false,
    })
    const runId = res?.run_id || res?.data?.run_id
    if (!runId) throw new Error('未获取到 run_id')
    currentRunId.value = runId
    phase.value = 'executing'
    stream.start(`/api/v1/workflows/${runId}/stream`)

    // C-β: 同时注册到全局 RunStore，让 Header 指示器可见 + 跨页持久跟踪
    runStore.track({
      runId,
      streamUrl: `/api/v1/workflows/${runId}/stream`,
      route: workflowId.value,
      query: query.value,
      origin: 'analyze',
    })
  } catch (e) {
    console.error('[AnalyzeProgress] startAnalysis error:', e)
    preflightError.value = e?.message || '请检查后端服务是否正常运行'
  } finally {
    loading.value = false
  }
}

/**
 * C-β Fix A: 支持 ?run_id= 恢复正在跑/已跑完的任务
 *
 * 必须用 watch 而不是 onMounted，因为 Vue Router 在同路径下
 * （比如当前已在 /analyze，点 Header RunTicker 跳 /analyze?run_id=xxx）
 * 复用组件，onMounted 不会再次触发，只有 route.query 会响应式变化。
 *
 * 逻辑：
 *   1. 有 run_id → 进 executing 阶段，重启 stream
 *   2. 无 run_id → 保持/切回 form
 *   3. 从 RunStore 复用 route/query（跨页来源），拿不到也没关系
 *      SSE 本身会 emit route_decided 重建 steps
 */
watch(
  () => route.query.run_id,
  (resumeRunId, oldRunId) => {
    // 从 /analyze?run_id=xxx 跳到 /analyze（新建任务）→ 回到 form 阶段
    if (!resumeRunId) {
      if (oldRunId) {
        // 之前有 run，现在清空：停流 + 重置 UI
        stream.stop()
        stream.reset()
        currentRunId.value = null
        resultContent.value = ''
        selectedStep.value = null
        phase.value = 'form'
      }
      return
    }
    if (resumeRunId === currentRunId.value) return  // 同一个 run，避免重复订阅

    const existing = runStore.getRun(resumeRunId)
    currentRunId.value = resumeRunId
    if (existing) {
      workflowId.value = existing.route || workflowId.value
      query.value = existing.query || query.value
    }
    phase.value = 'executing'
    // 即使 RunStore 未命中也直接订阅 SSE；后端 Redis snapshot (Fix B)
    // 能让已完成的 run 立即回放 final 事件
    stream.start(`/api/v1/workflows/${resumeRunId}/stream`)
  },
  { immediate: true },
)

onMounted(() => { ai.init() })
</script>

<style scoped>
.ap { display: flex; flex-direction: column; gap: var(--v2-space-3); height: 100%; overflow: hidden; }
.ap__main-scroll { position: absolute; inset: 0; overflow-y: auto; display: flex; flex-direction: column; gap: var(--v2-space-4); padding: var(--v2-space-3); }
/* Fix H: 防止 flex column 将子 SectionCardV2 压缩低于其内容高度，
   否则 SectionCardV2 自带的 overflow:hidden 会直接切掉底部内容（如"执行摘要"
   的"行动建议"部分看不到），同时父级 overflow-y:auto 因总高未超而不触发滚动。 */
.ap__main-scroll > :deep(.sec) { flex-shrink: 0; }

/* ── Header actions ── */
.ap__hd-actions { display: flex; align-items: center; gap: 8px; }
.ap__view-toggle { display: flex; border: 1px solid var(--v2-border-1); border-radius: var(--v2-radius-md); overflow: hidden; }
.ap__view-btn { display: flex; align-items: center; justify-content: center; width: 28px; height: 26px; border: none; background: var(--v2-bg-card); color: var(--v2-text-4); cursor: pointer; transition: all 0.15s; }
.ap__view-btn:hover { color: var(--v2-text-1); }
.ap__view-btn--active { background: var(--v2-text-1); color: #fff; }
.ap__toggle-panel { display: flex; align-items: center; justify-content: center; width: 28px; height: 28px; border: 1px solid var(--v2-border-1); border-radius: var(--v2-radius-md); background: var(--v2-bg-card); color: var(--v2-text-3); cursor: pointer; transition: all 0.15s; }
.ap__toggle-panel:hover { color: var(--v2-text-1); }
.ap__toggle-panel--active { background: var(--v2-text-1); color: #fff; border-color: var(--v2-text-1); }

/* ── Form ── */
.ap__form { display: flex; flex-direction: column; gap: 20px; }
.ap__form-field { display: flex; flex-direction: column; gap: 8px; }
.ap__label { font-size: 11px; font-weight: 600; color: var(--v2-text-3); text-transform: uppercase; letter-spacing: 0.5px; }
.ap__radio-group { display: flex; gap: 8px; }
.ap__radio { display: flex; align-items: center; gap: 8px; flex: 1; padding: 12px 14px; background: transparent; border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-lg); color: var(--v2-text-2); font-size: 13px; font-weight: 500; cursor: pointer; transition: all 0.15s; font-family: inherit; }
.ap__radio:hover { background: var(--v2-bg-hover); color: var(--v2-text-1); }
.ap__radio--active { border-color: var(--v2-text-1); color: var(--v2-text-1); background: var(--v2-bg-active, rgba(0,0,0,0.02)); }

.ap__composer { border: 1px solid var(--v2-border-1); border-radius: var(--v2-radius-lg); overflow: hidden; transition: border-color 0.15s; }
.ap__composer:focus-within { border-color: var(--v2-text-1); }
.ap__textarea { width: 100%; border: none; background: transparent; padding: 14px; font-family: inherit; font-size: 13px; line-height: 1.55; color: var(--v2-text-1); resize: vertical; outline: none; }
.ap__composer-ft { display: flex; justify-content: space-between; align-items: center; padding: 6px 14px; background: var(--v2-bg-hover); border-top: 1px solid var(--v2-border-2); }
.ap__hint { font-size: 11px; color: var(--v2-text-4); }
.ap__submit { display: flex; align-items: center; gap: 6px; padding: 6px 14px; background: var(--v2-text-1); color: #fff; border: none; border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer; font-family: inherit; transition: opacity 0.15s; }
.ap__submit:disabled { opacity: 0.4; cursor: not-allowed; }
.ap__submit:hover:not(:disabled) { opacity: 0.85; }

/* ── Progress card ── */
.ap__progress-hd { display: flex; align-items: center; justify-content: space-between; width: 100%; }
.ap__progress-title { font-size: 13px; font-weight: 600; color: var(--v2-text-1); }
.ap__badge { font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.5px; }
.ap__badge--running { background: rgba(0,0,0,0.06); color: var(--v2-text-1); }
.ap__badge--completed { background: rgba(34,197,94,0.1); color: var(--v2-success); }
.ap__badge--error { background: rgba(239,68,68,0.1); color: var(--v2-error); }
.ap__badge--idle { background: rgba(0,0,0,0.04); color: var(--v2-text-3); }

.ap__bar { height: 3px; background: var(--v2-border-2); border-radius: 2px; margin-top: 16px; overflow: hidden; }
.ap__bar-fill { height: 100%; background: var(--v2-text-1); border-radius: 2px; transition: width 0.4s ease-out; }

.ap__progress-ft { display: flex; justify-content: center; margin-top: 12px; }
.ap__btn { display: flex; align-items: center; gap: 6px; padding: 6px 14px; border: 1px solid var(--v2-border-1); border-radius: 6px; background: var(--v2-bg-card); color: var(--v2-text-2); font-size: 12px; font-weight: 500; cursor: pointer; font-family: inherit; transition: all 0.15s; }
.ap__btn:hover { color: var(--v2-text-1); background: var(--v2-bg-hover); }
.ap__btn--danger { color: var(--v2-error); border-color: rgba(239,68,68,0.2); }
.ap__btn--danger:hover { background: rgba(239,68,68,0.05); }

/* ── Timeline ── */
.ap__timeline { display: flex; flex-direction: column; }
.ap__step { display: flex; gap: 14px; position: relative; padding-bottom: 20px; cursor: pointer; }
.ap__step:last-child { padding-bottom: 0; }
.ap__step:hover .ap__step-name { color: var(--v2-text-1); }
.ap__step-line { position: absolute; top: 22px; bottom: 0; left: 10px; width: 2px; background: var(--v2-border-2); z-index: 1; }
.ap__step-dot { width: 22px; height: 22px; border-radius: 50%; background: var(--v2-bg-hover); display: flex; align-items: center; justify-content: center; color: var(--v2-text-3); z-index: 2; flex-shrink: 0; transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1); }
.ap__step--running .ap__step-dot { background: var(--v2-text-1); color: #fff; }
.ap__step--completed .ap__step-dot { background: var(--v2-success); color: #fff; }
.ap__step--error .ap__step-dot { background: var(--v2-error); color: #fff; }
.ap__step-content { padding-top: 1px; }
.ap__step-name { font-size: 13px; font-weight: 500; color: var(--v2-text-2); transition: color 0.15s; }
.ap__step--running .ap__step-name { color: var(--v2-text-1); font-weight: 600; }
.ap__step--completed .ap__step-name { color: var(--v2-text-1); }
.ap__step-meta { font-size: 10px; color: var(--v2-text-4); margin-top: 2px; font-family: var(--v2-font-mono); }

/* ── Skeleton ── */
.ap__skeleton { display: flex; flex-direction: column; gap: 10px; }
.ap__skeleton-line { height: 14px; background: var(--v2-bg-hover); border-radius: 4px; animation: ap-pulse 1.5s infinite; }
@keyframes ap-pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }

/* ── Spinner ── */
@keyframes ap-spin { to { transform: rotate(360deg); } }
.ap__spin { animation: ap-spin 0.8s linear infinite; }

/* ── Detail panel ── */
.ap__detail { display: flex; flex-direction: column; gap: 10px; padding: 12px; overflow-y: auto; }
.ap__detail h4 { font-size: 12px; font-weight: 600; color: #71717a; text-transform: uppercase; letter-spacing: .5px; margin: 0 0 8px; padding-bottom: 6px; border-bottom: 1px solid rgba(0,0,0,0.06); }
.ap__dl { display: flex; justify-content: space-between; padding: 3px 0; font-size: 13px; }
.ap__dl > span:first-child { color: #71717a; } .ap__dl > span:last-child { color: #18181b; }
.ap__detail-ask { display: flex; align-items: center; justify-content: center; gap: 6px; padding: 8px; border: 1px solid rgba(0,0,0,0.08); border-radius: 8px; background: #fff; font-size: 12px; font-weight: 500; color: #18181b; cursor: pointer; transition: all 0.15s; font-family: inherit; margin-top: 4px; }
.ap__detail-ask:hover { background: #f4f4f5; border-color: rgba(0,0,0,0.15); }
.ap__detail--empty { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; flex: 1; color: var(--v2-text-4); font-size: 12px; }
.ap__detail--empty p { margin: 0; }

/* ── Plan Preview ── */
.ap__plan-hd { display: flex; align-items: center; justify-content: space-between; width: 100%; }
.ap__plan { display: flex; flex-direction: column; gap: 16px; }
.ap__plan-desc { font-size: 13px; color: var(--v2-text-3); line-height: 1.5; margin: 0; }
.ap__plan-desc strong { color: var(--v2-text-1); font-weight: 600; }
.ap__plan-steps { display: flex; flex-direction: column; gap: 2px; }
.ap__plan-step {
  display: flex; align-items: flex-start; gap: 12px; padding: 10px 12px;
  border-radius: var(--v2-radius-md); transition: background 0.15s;
}
.ap__plan-step:hover { background: var(--v2-bg-hover); }
.ap__plan-idx {
  width: 22px; height: 22px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 600; font-family: var(--v2-font-mono);
  background: var(--v2-bg-active); color: var(--v2-text-2);
}
.ap__plan-info { flex: 1; min-width: 0; }
.ap__plan-name { font-size: 13px; font-weight: 500; color: var(--v2-text-1); display: flex; align-items: center; gap: 6px; }
.ap__plan-tag {
  font-size: 10px; font-weight: 600; padding: 1px 6px;
  border-radius: var(--v2-radius-pill); letter-spacing: 0.02em;
  background: var(--v2-bg-active); color: var(--v2-text-3);
}
.ap__plan-note { font-size: 12px; color: var(--v2-text-4); margin-top: 2px; }
.ap__plan-error { font-size: 12px; color: var(--v2-error-text); padding: 8px 12px; background: var(--v2-error-bg); border-radius: var(--v2-radius-md); }
.ap__plan-ft { display: flex; justify-content: flex-end; align-items: center; gap: 8px; padding-top: 8px; border-top: 1px solid var(--v2-border-2); }

/* ── Confidence Signal ── */
.ap__conf { display: inline-flex; align-items: center; gap: 3px; font-size: 10px; font-weight: 600; padding: 1px 6px; border-radius: var(--v2-radius-pill); letter-spacing: 0.02em; white-space: nowrap; vertical-align: middle; margin-left: 4px; }
.ap__conf--pill { margin-left: 0; }
.ap__conf--high { background: rgba(34,197,94,0.1); color: var(--v2-success); }
.ap__conf--mid  { background: rgba(234,179,8,0.1); color: var(--v2-warning, #b45309); }
.ap__conf--low  { background: rgba(239,68,68,0.1); color: var(--v2-error); }
</style>
