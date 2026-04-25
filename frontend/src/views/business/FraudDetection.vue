<template>
  <div class="fd">
    <PageHeaderV2 title="风控中心" desc="实时交易风险评估 · 规则解释 · 人工审核">
      <template #actions>
        <el-button size="small" @click="scrollToReviews">待审核队列</el-button>
        <button class="fd__toggle-panel" :class="{ 'fd__toggle-panel--active': showRight }" @click="showRight = !showRight" title="AI 面板">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="3"/><line x1="15" y1="3" x2="15" y2="21"/></svg>
        </button>
      </template>
    </PageHeaderV2>

    <SplitInspector :hide-right="!showRight">
      <template #main>
        <div class="fd__main-scroll" ref="scrollRoot">
          <!-- C-α: 从 Dashboard 跳转带入的 intent 提示 -->
          <DegradedBannerV2
            v-if="fromDashboardNotice"
            level="info"
            :title="fromDashboardNotice.title"
            :desc="fromDashboardNotice.desc"
            :closable="true"
            @close="fromDashboardNotice = null"
          />
          <!-- ① 风险概览 KPI -->
          <div class="fd__kpis">
            <ClickToAsk question="今日拦截交易的特征分析和异常模式" @ask="onAskAI">
              <StatCardV2 class="fd__kpi-hero" label="今日拦截" :value="stats.today_blocked ?? '--'" trend-dir="neutral" sub="已拦截交易" clickable />
            </ClickToAsk>
            <StatCardV2 label="拦截率" :value="blockRateStr" sub="今日" />
            <ClickToAsk question="高风险交易有哪些共同特征？是否存在团伙欺诈？" @ask="onAskAI">
              <StatCardV2 label="高风险" :value="stats.high_risk_count ?? '--'" trend-dir="down" sub="需立即审核" clickable />
            </ClickToAsk>
            <StatCardV2 label="中风险" :value="stats.mid_risk_count ?? '--'" sub="需二次验证" />
            <StatCardV2 label="模型 AUC" :value="stats.model_auc ?? '--'" trend-dir="up" sub="检测能力" />
          </div>

          <!-- ② 风险分层 -->
          <div class="fd__layers">
            <div class="fd__layer fd__layer--high"><div class="fd__layer-bar" /><div class="fd__layer-body"><span class="fd__layer-count">{{ stats.high_risk_count ?? 0 }}</span><span class="fd__layer-label">高风险</span><span class="fd__layer-desc">立即冻结并审核</span></div></div>
            <div class="fd__layer fd__layer--mid"><div class="fd__layer-bar" /><div class="fd__layer-body"><span class="fd__layer-count">{{ stats.mid_risk_count ?? 0 }}</span><span class="fd__layer-label">中风险</span><span class="fd__layer-desc">需二次验证</span></div></div>
            <div class="fd__layer fd__layer--low"><div class="fd__layer-bar" /><div class="fd__layer-body"><span class="fd__layer-count">{{ (stats.today_total ?? 0) - (stats.today_blocked ?? 0) }}</span><span class="fd__layer-label">正常</span><span class="fd__layer-desc">自动放行</span></div></div>
          </div>

          <!-- ③ 评分表单 + 结果 -->
          <div class="fd__scoring">
            <SectionCardV2 title="实时交易评分" class="fd__form-card">
              <el-form :model="scoreForm" label-width="90px" size="small">
                <el-form-item label="交易ID"><el-input v-model="scoreForm.transaction_id" placeholder="TX20240315001" /></el-form-item>
                <el-form-item label="客户ID"><el-input v-model="scoreForm.customer_id" placeholder="LY000088" /></el-form-item>
                <el-form-item label="金额"><el-input-number v-model="scoreForm.amount" :min="0.01" :precision="2" style="width:100%" /></el-form-item>
                <el-form-item label="时段"><el-input-number v-model="scoreForm.hour_of_day" :min="0" :max="23" style="width:100%" /></el-form-item>
                <el-form-item label="新账户"><el-switch v-model="scoreForm.is_new_account" /></el-form-item>
                <el-form-item><el-button type="primary" :loading="scoreLoading" @click="runScore">评分</el-button></el-form-item>
              </el-form>
            </SectionCardV2>

            <SectionCardV2 title="评分结果" class="fd__result-card">
              <SkeletonBlockV2 v-if="scoreLoading" :rows="5" />
              <ErrorStateV2 v-else-if="scoreError" :desc="scoreError" @retry="runScore" />
              <template v-else-if="scoreResult">
                <div class="fd__score-head">
                  <div class="fd__score-ring" :class="'fd__score-ring--' + scoreResult.risk_level">{{ scoreResult.final_score?.toFixed(1) }}</div>
                  <div class="fd__score-info">
                    <el-tag :type="riskType(scoreResult.risk_level)" size="large">{{ scoreResult.risk_level }}</el-tag>
                    <span class="fd__score-action">动作: <strong>{{ scoreResult.action }}</strong></span>
                    <span class="fd__score-src">来源: {{ scoreResult.source || 'ensemble' }}</span>
                  </div>
                </div>
                <div class="fd__explain">
                  <div class="fd__explain-title"><AIInlineLabel text="模型解释" size="sm" /></div>
                  <div class="fd__explain-grid">
                    <div class="fd__exp-item"><span class="fd__exp-label">LightGBM</span><span class="fd__exp-val">{{ scoreResult.lgbm_score?.toFixed(4) ?? '-' }}</span></div>
                    <div class="fd__exp-item"><span class="fd__exp-label">IsoForest</span><span class="fd__exp-val">{{ scoreResult.ae_score?.toFixed(4) ?? '-' }}</span></div>
                    <div class="fd__exp-item"><span class="fd__exp-label">综合分数</span><span class="fd__exp-val" style="font-weight:700">{{ scoreResult.final_score?.toFixed(2) ?? '-' }}</span></div>
                  </div>
                  <p class="fd__explain-text">{{ scoreExplain }}</p>
                </div>
                <div v-if="scoreResult.rules_triggered?.length" class="fd__rules">
                  <div class="fd__rules-hd">命中规则</div>
                  <div class="fd__rules-list"><div v-for="rule in scoreResult.rules_triggered" :key="rule" class="fd__rule-chip">{{ rule }}</div></div>
                </div>
                <DegradedBannerV2 v-if="scoreResult.hitl_required" level="warning" :title="`需人工审核 (${scoreResult.thread_id?.slice(0,12)}…)`" desc="高风险交易已进入审核队列" :closable="false" />
              </template>
              <EmptyStateV2 v-else title="输入交易信息后点击评分" height="180px" />
            </SectionCardV2>
          </div>

          <!-- ④ 待审核 -->
          <SectionCardV2 title="待审核交易" :flush="true" data-section="pending-reviews">
            <template #header>
              <CrossAgentBridge :ai="ai" skill-id="customer_intel" question="待审核交易中的客户是否有高流失或高价值标签？" :context="{ pending_count: pendingList.length }" label="客群交叉" style="margin-right:8px" />
              <el-button size="small" @click="loadPending" :loading="pendingLoading">刷新</el-button>
            </template>
            <SkeletonBlockV2 v-if="pendingLoading" :rows="4" />
            <ErrorStateV2 v-else-if="pendingError" :desc="pendingError" @retry="loadPending" />
            <template v-else-if="pendingList.length">
              <el-table :data="pendingList" size="small" max-height="300" style="width:100%" @row-click="onPendingRowClick">
                <el-table-column prop="thread_id" label="Thread" width="160" show-overflow-tooltip />
                <el-table-column label="交易ID" width="140"><template #default="{ row }">{{ row.transaction?.transaction_id || '-' }}</template></el-table-column>
                <el-table-column label="金额" width="100" align="right"><template #default="{ row }">¥{{ row.transaction?.amount?.toFixed(2) || '-' }}</template></el-table-column>
                <el-table-column label="风险分" width="80" align="right"><template #default="{ row }"><span :style="{ color: (row.risk_info?.risk_score??0)>70?'var(--v2-error)':'var(--v2-warning)', fontWeight:600 }">{{ row.risk_info?.risk_score?.toFixed(1) ?? '-' }}</span></template></el-table-column>
                <el-table-column prop="status" label="状态" width="80" align="center"><template #default="{ row }"><el-tag size="small" type="warning">{{ row.status||'pending' }}</el-tag></template></el-table-column>
                <el-table-column prop="created_at" label="时间" width="140" show-overflow-tooltip />
                <el-table-column label="" width="80" align="center"><template #default="{ row }"><el-button size="small" type="primary" text @click.stop="onPendingRowClick(row)">审核</el-button></template></el-table-column>
              </el-table>
            </template>
            <EmptyStateV2 v-else title="暂无待审核交易" />
          </SectionCardV2>
        </div>
      </template>

      <!-- ═══ Right Panel ═══ -->
      <template #right>
        <PageAICopilotPanel
          ref="aiPanel"
          :ai="ai"
          welcome-title="AI 风控助手"
          welcome-desc="分析交易风险、解读模型评分、审核辅助"
          collection="fraud"
          command-bar-placeholder="询问风控相关问题...  @ 选择智能体"
          :quick-questions="quickQuestions"
          :mention-catalog="mentionCatalog"
        >
          <template #detail>
            <div v-if="selectedPending" class="fd__detail">
              <div class="fd__detail-sec"><h4>风险评估</h4>
                <div class="fd__dl"><span>风险等级</span><el-tag :type="riskType(selectedPending.risk_level)" size="small">{{ selectedPending.risk_level }}</el-tag></div>
                <div class="fd__dl"><span>综合评分</span><span style="font-weight:600">{{ selectedPending.final_score?.toFixed(2) }}</span></div>
                <div class="fd__dl"><span>LightGBM</span><span>{{ selectedPending.lgbm_score?.toFixed(4) ?? '-' }}</span></div>
                <div class="fd__dl"><span>IsoForest</span><span>{{ selectedPending.ae_score?.toFixed(4) ?? '-' }}</span></div>
                <div class="fd__dl"><span>执行动作</span><span>{{ selectedPending.action }}</span></div>
              </div>
              <div v-if="selectedPending.rules_triggered?.length" class="fd__detail-sec"><h4>命中规则</h4>
                <div class="fd__rules-list"><div v-for="r in selectedPending.rules_triggered" :key="r" class="fd__rule-chip">{{ r }}</div></div>
              </div>
              <button class="fd__detail-ask" @click="aiPanel?.askAndSwitch(`分析交易 ${selectedPending.transaction_id} 的风险特征和审核建议`)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
                AI 审核建议
              </button>
            </div>
            <div v-else class="fd__empty-detail">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
              <p>点击待审核交易查看详情</p>
            </div>
          </template>
        </PageAICopilotPanel>
      </template>
    </SplitInspector>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, nextTick } from 'vue'
import { fraudApi } from '@/api/business'
import { usePageCopilot } from '@/composables/usePageCopilot'
import { useIntentStore } from '@/stores/useIntentStore'
import {
  PageHeaderV2, StatCardV2, SectionCardV2, EmptyStateV2, ErrorStateV2,
  SkeletonBlockV2, AIInlineLabel, DegradedBannerV2, SplitInspector,
  ClickToAsk, CrossAgentBridge, PageAICopilotPanel,
} from '@/components/v2'

// ── AI Copilot ──
const ai = usePageCopilot('fraud', ['fraud_skill', 'kb_rag'])
const aiPanel = ref(null)
const showRight = ref(true)
const selectedPending = ref(null)

// ── C-α: Intent Store ──
const intentStore = useIntentStore()
const scrollRoot = ref(null)
const fromDashboardNotice = ref(null)

function scrollToReviews() {
  // 使用 data-ref 定位待审核 section（见模板 SectionCardV2 title='待审核交易' 区域）
  const el = scrollRoot.value?.querySelector('[data-section="pending-reviews"]')
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    el.classList.add('fd__highlight')
    setTimeout(() => el.classList.remove('fd__highlight'), 1600)
  }
}

const quickQuestions = [
  '今日风控整体态势如何？',
  '高风险交易的共同特征是什么？',
  '当前待审核交易的优先级排序',
]

const mentionCatalog = [
  { id: 'fraud', label: '风控中心', type: 'skill', icon: '🛡️' },
  { id: 'customer_intel', label: '客群洞察', type: 'skill', icon: '👥' },
  { id: 'kb_rag', label: '知识库', type: 'collection', icon: '📚' },
]

function onAskAI({ question }) {
  showRight.value = true
  aiPanel.value?.askAndSwitch(question)
}

const riskType = (level) => ({ '高': 'danger', '中': 'warning', '低': 'success' }[level] || 'info')

const stats = ref({})
const blockRateStr = computed(() => stats.value.block_rate != null ? (stats.value.block_rate * 100).toFixed(1) + '%' : '--')
async function loadStats() { try { stats.value = (await fraudApi.getStats()) ?? {} } catch {} }

const scoreForm = reactive({ transaction_id: 'TX20240315001', customer_id: 'LY000088', amount: 9999, hour_of_day: 3, is_new_account: false })
const scoreLoading = ref(false), scoreError = ref(''), scoreResult = ref(null)

const scoreExplain = computed(() => {
  const r = scoreResult.value; if (!r) return ''
  const parts = [`交易 ${r.transaction_id} 综合风险评分 ${r.final_score?.toFixed(1)}，判定为「${r.risk_level}」级。`]
  if (r.lgbm_score > 0.7) parts.push('LightGBM 模型给出高风险信号。')
  if (r.rules_triggered?.length) parts.push(`触发 ${r.rules_triggered.length} 条风控规则：${r.rules_triggered.join('、')}。`)
  parts.push(`系统建议执行「${r.action}」。`)
  if (r.hitl_required) parts.push('该交易已进入人工审核队列。')
  return parts.join('')
})

async function runScore() {
  scoreLoading.value = true; scoreError.value = ''; scoreResult.value = null
  try {
    scoreResult.value = await fraudApi.score(scoreForm)
    ai.setContext({ last_scored_tx: scoreForm.transaction_id, risk_level: scoreResult.value?.risk_level })
  }
  catch (e) { scoreError.value = e?.response?.data?.message || '评分失败' }
  finally { scoreLoading.value = false }
}

const pendingLoading = ref(false), pendingError = ref(''), pendingList = ref([])
async function loadPending() {
  pendingLoading.value = true; pendingError.value = ''
  try { const d = await fraudApi.getPendingReviews(); pendingList.value = Array.isArray(d) ? d : (d?.items ?? []) }
  catch (e) { pendingError.value = e?.response?.data?.message || '加载失败' } finally { pendingLoading.value = false }
}

function onPendingRowClick(row) {
  selectedPending.value = {
    transaction_id: row.transaction?.transaction_id || row.thread_id,
    risk_level: row.risk_info?.risk_level || '-',
    final_score: row.risk_info?.risk_score,
    lgbm_score: row.risk_info?.lgbm_score,
    ae_score: row.risk_info?.ae_score,
    action: row.risk_info?.action || '-',
    rules_triggered: row.risk_info?.rules_triggered || [],
    hitl_required: true,
    thread_id: row.thread_id,
  }
  showRight.value = true
  aiPanel.value?.switchTab('detail')
  ai.setContext({ selected_tx: selectedPending.value.transaction_id, risk_level: selectedPending.value.risk_level })
}

onMounted(async () => {
  loadStats(); loadPending()
  await ai.init()

  // ── C-α: 消费 intent（若从 Dashboard 跳转而来，自动聚焦待审区） ──
  const intent = intentStore.consume('review_high_risk')
  if (intent) {
    fromDashboardNotice.value = {
      title: '从经营总览跳转',
      desc: `检测到 ${intent.payload.pending || '若干'} 笔高风险交易待审，已自动刷新列表并聚焦下方审核区。`,
    }
    // 等 DOM 渲染和数据加载完再滚动
    nextTick(() => setTimeout(scrollToReviews, 400))
  }
})
</script>

<style scoped>
.fd { display: flex; flex-direction: column; gap: var(--v2-space-3); height: 100%; }
.fd__main-scroll { display: flex; flex-direction: column; gap: var(--v2-space-4); padding: var(--v2-space-3); overflow-y: auto; }
.fd__kpis { display: grid; grid-template-columns: 1.3fr 1fr 1fr 1fr 1fr; gap: var(--v2-space-4); }
.fd__kpi-hero { border-left: 3px solid var(--v2-error); }

.fd__layers { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--v2-space-4); }
.fd__layer { display: flex; align-items: center; gap: var(--v2-space-3); padding: var(--v2-space-4); background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-lg); }
.fd__layer-bar { width: 4px; height: 40px; border-radius: 2px; flex-shrink: 0; }
.fd__layer--high .fd__layer-bar { background: var(--v2-error); } .fd__layer--mid .fd__layer-bar { background: var(--v2-warning); } .fd__layer--low .fd__layer-bar { background: var(--v2-success); }
.fd__layer-body { min-width: 0; }
.fd__layer-count { font-size: var(--v2-text-2xl); font-weight: var(--v2-font-bold); color: var(--v2-text-1); display: block; }
.fd__layer-label { font-size: var(--v2-text-sm); font-weight: var(--v2-font-medium); color: var(--v2-text-1); }
.fd__layer-desc { font-size: var(--v2-text-xs); color: var(--v2-text-3); }

.fd__scoring { display: grid; grid-template-columns: 380px 1fr; gap: var(--v2-space-4); }

/* C-α: 被 intent 目标定位的区域临时高亮 */
.fd__highlight { box-shadow: 0 0 0 3px color-mix(in srgb, var(--v2-error, #dc2626) 35%, transparent); transition: box-shadow 0.3s; border-radius: var(--v2-radius-lg); }

.fd__score-head { display: flex; align-items: center; gap: var(--v2-space-5); margin-bottom: var(--v2-space-4); }
.fd__score-ring { width: 72px; height: 72px; border-radius: var(--v2-radius-full); display: flex; align-items: center; justify-content: center; font-size: var(--v2-text-2xl); font-weight: var(--v2-font-bold); color: #fff; background: var(--v2-gray-400); flex-shrink: 0; }
.fd__score-ring--高 { background: var(--v2-error); } .fd__score-ring--中 { background: var(--v2-warning); } .fd__score-ring--低 { background: var(--v2-success); }
.fd__score-info { display: flex; flex-direction: column; gap: 4px; }
.fd__score-action { font-size: var(--v2-text-sm); color: var(--v2-text-2); }
.fd__score-src { font-size: var(--v2-text-xs); color: var(--v2-text-4); }

.fd__explain { padding: var(--v2-space-4); background: var(--v2-ai-purple-bg); border: 1px solid rgba(124,58,237,.1); border-radius: var(--v2-radius-lg); margin-bottom: var(--v2-space-4); }
.fd__explain-title { margin-bottom: var(--v2-space-3); }
.fd__explain-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--v2-space-3); margin-bottom: var(--v2-space-3); }
.fd__exp-item { text-align: center; padding: var(--v2-space-2); background: rgba(255,255,255,.6); border-radius: var(--v2-radius-md); }
.fd__exp-label { display: block; font-size: var(--v2-text-xs); color: var(--v2-text-3); }
.fd__exp-val { display: block; font-size: var(--v2-text-lg); font-weight: var(--v2-font-semibold); color: var(--v2-text-1); font-variant-numeric: tabular-nums; }
.fd__explain-text { font-size: var(--v2-text-md); color: var(--v2-text-2); line-height: var(--v2-leading-relaxed); margin: 0; }

.fd__rules { margin-bottom: var(--v2-space-4); }
.fd__rules-hd { font-size: var(--v2-text-xs); font-weight: var(--v2-font-semibold); color: var(--v2-error-text); margin-bottom: var(--v2-space-2); }
.fd__rules-list { display: flex; flex-wrap: wrap; gap: var(--v2-space-2); }
.fd__rule-chip { font-size: var(--v2-text-xs); padding: 2px 8px; background: var(--v2-error-bg); color: var(--v2-error-text); border-radius: var(--v2-radius-sm); font-weight: var(--v2-font-medium); }

/* Toggle */
.fd__toggle-panel { display: flex; align-items: center; justify-content: center; width: 28px; height: 28px; border: 1px solid var(--v2-border-1); border-radius: var(--v2-radius-md); background: var(--v2-bg-card); color: var(--v2-text-3); cursor: pointer; transition: all var(--v2-trans-fast); }
.fd__toggle-panel:hover { color: var(--v2-text-1); }
.fd__toggle-panel--active { background: var(--v2-text-1); color: #fff; border-color: var(--v2-text-1); }

/* Detail */
.fd__detail { display: flex; flex-direction: column; gap: var(--v2-space-4); padding: 12px; overflow-y: auto; }
.fd__detail-sec h4 { font-size: 12px; font-weight: 600; color: #71717a; text-transform: uppercase; letter-spacing: .5px; margin: 0 0 8px; padding-bottom: 6px; border-bottom: 1px solid rgba(0,0,0,0.06); }
.fd__dl { display: flex; justify-content: space-between; padding: 3px 0; font-size: 13px; }
.fd__dl > span:first-child { color: #71717a; } .fd__dl > span:last-child { color: #18181b; }
.fd__detail-ask { display: flex; align-items: center; justify-content: center; gap: 6px; padding: 8px; border: 1px solid rgba(0,0,0,0.08); border-radius: 8px; background: #fff; font-size: 12px; font-weight: 500; color: #18181b; cursor: pointer; transition: all 0.15s; font-family: inherit; }
.fd__detail-ask:hover { background: #f4f4f5; border-color: rgba(0,0,0,0.15); }
.fd__empty-detail { display: flex; flex-direction: column; align-items: center; justify-content: center; flex: 1; gap: 8px; color: #a1a1aa; }
.fd__empty-detail p { font-size: 12px; margin: 0; }

@media (max-width: 1200px) {
  .fd__kpis { grid-template-columns: repeat(2, 1fr); }
  .fd__layers { grid-template-columns: 1fr; }
  .fd__scoring { grid-template-columns: 1fr; }
}
</style>
