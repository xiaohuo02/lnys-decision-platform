<template>
  <div class="ca">
    <PageHeaderV2 title="客群洞察" desc="RFM 分层 · CLV 预测 · 流失预警">
      <template #actions>
        <el-select v-model="rfmFilter" placeholder="会员等级" clearable size="small" style="width:120px" @change="loadRfm">
          <el-option label="全部" value="" /><el-option v-for="lv in ['普通','银卡','金卡','钻石']" :key="lv" :label="lv" :value="lv" />
        </el-select>
        <button class="ca__toggle-panel" :class="{ 'ca__toggle-panel--active': showRight }" @click="showRight = !showRight" title="AI 面板">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="3"/><line x1="15" y1="3" x2="15" y2="21"/></svg>
        </button>
      </template>
    </PageHeaderV2>

    <SplitInspector :hide-right="!showRight">
      <!-- ═══ Main Content ═══ -->
      <template #main>
        <div class="ca__main" ref="scrollRoot">
          <!-- C-α: 从 Dashboard 跳转带入的 intent 提示 -->
          <DegradedBannerV2
            v-if="fromDashboardNotice"
            level="info"
            :title="fromDashboardNotice.title"
            :desc="fromDashboardNotice.desc"
            :closable="true"
            @close="fromDashboardNotice = null"
          />
          <!-- ① KPI Strip -->
          <div class="ca__kpis">
            <ClickToAsk question="当前客群分层有哪些特征？各客群的消费行为有什么差异？" @ask="onAskAI">
              <StatCardV2 label="客群总数" :value="segments.length || '--'" sub="分层客群" clickable />
            </ClickToAsk>
            <ClickToAsk question="CLV 最高的客户有什么特点？如何提高高价值客户留存？" @ask="onAskAI">
              <StatCardV2 label="CLV Top1" :value="topClv" sub="最高预测终身价值" clickable />
            </ClickToAsk>
            <ClickToAsk question="高流失风险客户的主要特征是什么？建议采取哪些措施？" @ask="onAskAI">
              <StatCardV2 label="高风险客户" :value="churnData.length || '--'" trend-dir="down" sub="流失概率 > 70%" clickable />
            </ClickToAsk>
            <ClickToAsk question="当前 RFM 客户价值分布情况如何？" @ask="onAskAI">
              <StatCardV2 label="RFM 客户" :value="rfmTotal || '--'" sub="已分析客户" clickable />
            </ClickToAsk>
          </div>

          <!-- ② 客群分布 + CLV -->
          <div class="ca__charts">
            <SectionCardV2 title="客群分布" class="ca__seg">
              <SkeletonBlockV2 v-if="segLoading" :rows="5" />
              <ErrorStateV2 v-else-if="segError" :desc="segError" @retry="loadSegments" />
              <div v-else-if="segments.length" style="height:280px"><v-chart :option="segOption" autoresize /></div>
              <EmptyStateV2 v-else title="暂无客群数据" />
            </SectionCardV2>
            <SectionCardV2 title="CLV Top 20" class="ca__clv">
              <template #header><AIInlineLabel v-if="clvDegraded" text="降级数据" size="xs" /></template>
              <SkeletonBlockV2 v-if="clvLoading" :rows="5" />
              <ErrorStateV2 v-else-if="clvError" :desc="clvError" @retry="loadClv" />
              <div v-else-if="clvData.length" style="height:280px"><v-chart :option="clvOption" autoresize /></div>
              <EmptyStateV2 v-else title="暂无 CLV 数据" />
            </SectionCardV2>
          </div>

          <!-- ③ 高风险客户 -->
          <SectionCardV2 title="高流失风险客户" :subtitle="`概率 > ${(churnThreshold * 100).toFixed(0)}%`" data-section="churn-risk">
            <template #header>
              <AIInlineLabel v-if="churnDegraded" text="降级数据" size="xs" />
              <CrossAgentBridge :ai="ai" skill-id="fraud" question="这些高流失客户中是否有欺诈风险记录？" :context="{ churn_count: churnData.length }" label="风控交叉" style="margin-left:auto" />
            </template>
            <SkeletonBlockV2 v-if="churnLoading" :rows="4" />
            <ErrorStateV2 v-else-if="churnError" :desc="churnError" @retry="loadChurn" />
            <template v-else-if="churnData.length">
              <el-table :data="churnData" size="small" max-height="300" style="width:100%" @row-click="onChurnRowClick">
                <el-table-column prop="customer_id" label="客户ID" width="110" />
                <el-table-column prop="churn_probability" label="流失概率" width="100" align="right">
                  <template #default="{ row }">
                    <span :style="{ color: row.churn_probability > .8 ? 'var(--v2-error)' : 'var(--v2-warning)', fontWeight: 600 }">{{ (row.churn_probability * 100).toFixed(1) }}%</span>
                  </template>
                </el-table-column>
                <el-table-column prop="risk_level" label="风险" width="70" align="center">
                  <template #default="{ row }"><el-tag :type="row.risk_level === '高' ? 'danger' : 'warning'" size="small">{{ row.risk_level }}</el-tag></template>
                </el-table-column>
                <el-table-column prop="top3_reasons" label="主因" min-width="200">
                  <template #default="{ row }">{{ (row.top3_reasons || []).join(' · ') }}</template>
                </el-table-column>
                <el-table-column prop="recommended_action" label="建议" min-width="140" />
              </el-table>
            </template>
            <EmptyStateV2 v-else title="暂无高风险客户" />
          </SectionCardV2>

          <!-- ④ RFM 表格 -->
          <SectionCardV2 title="RFM 客户价值明细" :subtitle="`共 ${rfmTotal} 条`" :flush="true" class="ca__rfm">
            <template #header><AIInlineLabel v-if="rfmDegraded" text="降级数据" size="xs" /></template>
            <SkeletonBlockV2 v-if="rfmLoading" :rows="6" />
            <ErrorStateV2 v-else-if="rfmError" :desc="rfmError" @retry="loadRfm" />
            <template v-else-if="rfmData.length">
              <el-table :data="rfmData" size="small" max-height="400" style="width:100%" @row-click="onRfmRowClick">
                <el-table-column prop="customer_id" label="客户ID" width="110" />
                <el-table-column prop="member_level" label="等级" width="80" />
                <el-table-column prop="recency" label="R" width="60" align="right" />
                <el-table-column prop="frequency" label="F" width="60" align="right" />
                <el-table-column prop="monetary" label="M (元)" width="100" align="right">
                  <template #default="{ row }">{{ row.monetary?.toLocaleString() }}</template>
                </el-table-column>
                <el-table-column prop="r_score" label="Rs" width="50" align="center" />
                <el-table-column prop="f_score" label="Fs" width="50" align="center" />
                <el-table-column prop="m_score" label="Ms" width="50" align="center" />
                <el-table-column prop="segment" label="客群" min-width="100" />
              </el-table>
              <div style="padding:var(--v2-space-3) var(--v2-space-4);display:flex;justify-content:flex-end;border-top:1px solid var(--v2-border-2)">
                <el-pagination size="small" background layout="prev,pager,next" :total="rfmTotal" :page-size="50" v-model:current-page="rfmPage" @current-change="loadRfm" />
              </div>
            </template>
            <EmptyStateV2 v-else title="暂无 RFM 数据" />
          </SectionCardV2>
        </div>
      </template>

      <!-- ═══ Right Panel: AI / Detail / KB ═══ -->
      <template #right>
        <PageAICopilotPanel
          ref="aiPanel"
          :ai="ai"
          welcome-title="AI 客群分析助手"
          welcome-desc="探索客群结构、预测客户价值、分析流失风险"
          collection="customer"
          command-bar-placeholder="询问客户相关问题...  @ 选择智能体"
          :quick-questions="quickQuestions"
          :mention-catalog="mentionCatalog"
          @tab-change="onTabChange"
        >
          <!-- Detail tab: customer detail -->
          <template #detail>
            <div v-if="selectedRow" class="ca__detail">
              <div class="ca__detail-section">
                <h4>基础信息</h4>
                <div class="ca__dl"><span>客户ID</span><span>{{ selectedRow.customer_id }}</span></div>
                <div class="ca__dl"><span>会员等级</span><span>{{ selectedRow.member_level || '-' }}</span></div>
                <div class="ca__dl"><span>客群</span><span>{{ selectedRow.segment || '-' }}</span></div>
              </div>
              <div v-if="selectedRow.r_score" class="ca__detail-section">
                <h4>RFM 分析</h4>
                <div class="ca__rfm-scores">
                  <div class="ca__rfm-sc"><span class="ca__rfm-sc-v">{{ selectedRow.r_score }}</span><span class="ca__rfm-sc-l">R</span></div>
                  <div class="ca__rfm-sc"><span class="ca__rfm-sc-v">{{ selectedRow.f_score }}</span><span class="ca__rfm-sc-l">F</span></div>
                  <div class="ca__rfm-sc"><span class="ca__rfm-sc-v">{{ selectedRow.m_score }}</span><span class="ca__rfm-sc-l">M</span></div>
                </div>
                <div class="ca__dl"><span>Recency</span><span>{{ selectedRow.recency }} 天</span></div>
                <div class="ca__dl"><span>Frequency</span><span>{{ selectedRow.frequency }} 次</span></div>
                <div class="ca__dl"><span>Monetary</span><span>¥{{ selectedRow.monetary?.toLocaleString() }}</span></div>
              </div>
              <div v-if="selectedRow.churn_probability != null" class="ca__detail-section">
                <h4>流失风险</h4>
                <div class="ca__dl"><span>流失概率</span>
                  <span :style="{ color: selectedRow.churn_probability > .7 ? 'var(--v2-error)' : 'var(--v2-warning)', fontWeight: 600 }">{{ (selectedRow.churn_probability * 100).toFixed(1) }}%</span>
                </div>
                <div v-if="selectedRow.risk_level" class="ca__dl"><span>风险等级</span><el-tag :type="selectedRow.risk_level === '高' ? 'danger' : 'warning'" size="small">{{ selectedRow.risk_level }}</el-tag></div>
                <div v-if="selectedRow.top3_reasons" class="ca__dl"><span>主因</span><span>{{ (selectedRow.top3_reasons || []).join('、') }}</span></div>
                <div v-if="selectedRow.recommended_action" class="ca__detail-action">
                  <AIInlineLabel text="建议措施" size="sm" />
                  <p>{{ selectedRow.recommended_action }}</p>
                </div>
              </div>
              <div v-if="selectedRow.predicted_clv != null" class="ca__detail-section">
                <h4>预测 CLV</h4>
                <div class="ca__dl"><span>终身价值</span><span style="font-weight:600">¥{{ selectedRow.predicted_clv?.toLocaleString() }}</span></div>
              </div>
              <button class="ca__detail-ask" @click="askAboutSelected">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
                AI 分析此客户
              </button>
            </div>
            <div v-else class="ca__empty-detail">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4-4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/></svg>
              <p>点击客户行查看详情</p>
            </div>
          </template>
        </PageAICopilotPanel>
      </template>
    </SplitInspector>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { customersApi } from '@/api/business'
import { usePageCopilot } from '@/composables/usePageCopilot'
import { useIntentStore } from '@/stores/useIntentStore'
import { basePieOption, baseChartOption } from '@/utils/chartDefaults'
import {
  PageHeaderV2, StatCardV2, SectionCardV2, EmptyStateV2, ErrorStateV2,
  SkeletonBlockV2, AIInlineLabel, DegradedBannerV2, SplitInspector, ClickToAsk,
  CrossAgentBridge, PageAICopilotPanel,
} from '@/components/v2'

// ── AI Copilot ──
const ai = usePageCopilot('customer', ['customer_intel', 'kb_rag'])
const aiPanel = ref(null)
const showRight = ref(true)
const selectedRow = ref(null)

// ── C-α: Intent Store ──
const intentStore = useIntentStore()
const scrollRoot = ref(null)
const fromDashboardNotice = ref(null)

function scrollToChurn() {
  const el = scrollRoot.value?.querySelector('[data-section="churn-risk"]')
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    el.classList.add('ca__highlight')
    setTimeout(() => el.classList.remove('ca__highlight'), 1600)
  }
}

const quickQuestions = [
  '当前客群整体概览和关键指标',
  '高价值客户有什么特征？',
  '高流失风险客户的挽回建议',
]

const mentionCatalog = [
  { id: 'customer_intel', label: '客群洞察', type: 'skill', icon: '👥' },
  { id: 'fraud', label: '风控中心', type: 'skill', icon: '🛡️' },
  { id: 'forecast', label: '销售预测', type: 'skill', icon: '📈' },
  { id: 'kb_rag', label: '知识库', type: 'collection', icon: '📚' },
]

// ── Row Selection → AI Context ──
function onChurnRowClick(row) {
  selectedRow.value = row
  showRight.value = true
  aiPanel.value?.switchTab('detail')
  ai.setContext({
    selected_customer: row.customer_id,
    churn_probability: row.churn_probability,
    risk_level: row.risk_level,
    top3_reasons: row.top3_reasons,
  })
}

function onRfmRowClick(row) {
  selectedRow.value = row
  showRight.value = true
  aiPanel.value?.switchTab('detail')
  ai.setContext({
    selected_customer: row.customer_id,
    member_level: row.member_level,
    segment: row.segment,
    rfm: { r: row.r_score, f: row.f_score, m: row.m_score },
  })
}

function askAboutSelected() {
  if (!selectedRow.value) return
  aiPanel.value?.askAndSwitch(`分析客户 ${selectedRow.value.customer_id} 的消费行为和价值潜力`)
}

function onAskAI({ question }) {
  showRight.value = true
  aiPanel.value?.askAndSwitch(question)
}

function onTabChange() { /* reserved */ }

// ── 客群 ─────────────────────────────────────────────────────
const segLoading = ref(false), segError = ref(''), segments = ref([])
const segOption = computed(() => basePieOption({
  series: [{ type: 'pie', radius: ['42%', '72%'], center: ['50%', '46%'], label: { fontSize: 11 }, data: segments.value.map(s => ({ name: s.name, value: s.count })), emphasis: { itemStyle: { shadowBlur: 8, shadowColor: 'rgba(0,0,0,.1)' } } }],
}))
async function loadSegments() {
  segLoading.value = true; segError.value = ''
  try { const d = await customersApi.getSegments(); segments.value = d?.segments ?? [] }
  catch (e) { segError.value = e?.response?.data?.message || '加载客群失败' } finally { segLoading.value = false }
}

// ── CLV ──────────────────────────────────────────────────────
const clvLoading = ref(false), clvError = ref(''), clvDegraded = ref(false), clvData = ref([])
const topClv = computed(() => clvData.value[0]?.predicted_clv != null ? '¥' + clvData.value[0].predicted_clv.toLocaleString() : '--')
const clvOption = computed(() => baseChartOption({
  grid: { left: 90, right: 20, top: 10, bottom: 30 },
  xAxis: { type: 'value' }, yAxis: { type: 'category', data: clvData.value.map(c => c.customer_id).reverse() },
  series: [{ type: 'bar', data: [...clvData.value].reverse().map(c => c.predicted_clv), barWidth: 12, itemStyle: { borderRadius: [0, 4, 4, 0] } }],
}))
async function loadClv() {
  clvLoading.value = true; clvError.value = ''
  try { const d = await customersApi.getClv({ top_n: 20 }); clvData.value = Array.isArray(d) ? d : (d?.data ?? []); clvDegraded.value = !!d?._meta?.degraded }
  catch (e) { clvError.value = e?.response?.data?.message || '加载 CLV 失败' } finally { clvLoading.value = false }
}

// ── RFM ──────────────────────────────────────────────────────
const rfmLoading = ref(false), rfmError = ref(''), rfmDegraded = ref(false), rfmData = ref([]), rfmTotal = ref(0), rfmPage = ref(1), rfmFilter = ref('')
async function loadRfm() {
  rfmLoading.value = true; rfmError.value = ''
  try { const p = { page: rfmPage.value, page_size: 50 }; if (rfmFilter.value) p.member_level = rfmFilter.value; const d = await customersApi.getRfm(p); rfmData.value = d?.items ?? (Array.isArray(d) ? d : []); rfmTotal.value = d?.total ?? rfmData.value.length; rfmDegraded.value = !!d?._meta?.degraded }
  catch (e) { rfmError.value = e?.response?.data?.message || '加载 RFM 失败' } finally { rfmLoading.value = false }
}

// ── 流失 ─────────────────────────────────────────────────────
const churnLoading = ref(false), churnError = ref(''), churnDegraded = ref(false), churnData = ref([])
const churnThreshold = ref(0.7)
async function loadChurn() {
  churnLoading.value = true; churnError.value = ''
  try { const d = await customersApi.getChurnRisk({ threshold: churnThreshold.value, top_n: 30 }); churnData.value = Array.isArray(d) ? d : (d?.items ?? []); churnDegraded.value = !!d?._meta?.degraded }
  catch (e) { churnError.value = e?.response?.data?.message || '加载流失风险失败' } finally { churnLoading.value = false }
}

onMounted(async () => {
  // ── C-α: 先消费 intent 决定 loadChurn 的 threshold ──
  const intent = intentStore.consume('view_churn_customers')
  if (intent) {
    if (typeof intent.payload.threshold === 'number') churnThreshold.value = intent.payload.threshold
    fromDashboardNotice.value = {
      title: '从经营总览跳转',
      desc: `已按流失概率 > ${(churnThreshold.value * 100).toFixed(0)}% 筛选${intent.payload.count ? `（${intent.payload.count} 个客户）` : ''}，下方自动聚焦高风险列表。`,
    }
  }

  loadSegments(); loadClv(); loadRfm(); loadChurn()
  await ai.init()

  if (intent) {
    nextTick(() => setTimeout(scrollToChurn, 400))
  }
})
</script>

<style scoped>
.ca { display: flex; flex-direction: column; gap: var(--v2-space-3); height: 100%; }
.ca__main { display: flex; flex-direction: column; gap: var(--v2-space-4); padding: var(--v2-space-3); overflow-y: auto; min-height: 0; }
.ca__main > * { flex-shrink: 0; }

/* C-α: 被 intent 目标定位的区域临时高亮 */
.ca__highlight { box-shadow: 0 0 0 3px color-mix(in srgb, var(--v2-warning, #f59e0b) 35%, transparent); transition: box-shadow 0.3s; border-radius: var(--v2-radius-lg); }
.ca__kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--v2-space-4); }
.ca__charts { display: grid; grid-template-columns: 1fr 1fr; gap: var(--v2-space-4); }
.ca__rfm { margin-bottom: 0; }

/* Toggle Panel Button */
.ca__toggle-panel { display: flex; align-items: center; justify-content: center; width: 28px; height: 28px; border: 1px solid var(--v2-border-1); border-radius: var(--v2-radius-md); background: var(--v2-bg-card); color: var(--v2-text-3); cursor: pointer; transition: all var(--v2-trans-fast); }
.ca__toggle-panel:hover { color: var(--v2-text-1); }
.ca__toggle-panel--active { background: var(--v2-text-1); color: #fff; border-color: var(--v2-text-1); }

/* Detail Panel */
.ca__detail { display: flex; flex-direction: column; gap: var(--v2-space-4); padding: 12px; overflow-y: auto; }
.ca__detail-section h4 { font-size: var(--v2-text-sm); font-weight: var(--v2-font-semibold); color: var(--v2-text-3); text-transform: uppercase; letter-spacing: .5px; margin-bottom: var(--v2-space-3); padding-bottom: var(--v2-space-2); border-bottom: 1px solid var(--v2-border-2); }
.ca__dl { display: flex; justify-content: space-between; padding: var(--v2-space-1) 0; font-size: 13px; }
.ca__dl > span:first-child { color: var(--v2-text-3); }
.ca__dl > span:last-child { color: var(--v2-text-1); font-variant-numeric: tabular-nums; }
.ca__rfm-scores { display: flex; gap: var(--v2-space-3); margin-bottom: var(--v2-space-3); }
.ca__rfm-sc { flex: 1; text-align: center; padding: var(--v2-space-3); background: var(--v2-bg-sunken); border-radius: var(--v2-radius-md); }
.ca__rfm-sc-v { display: block; font-size: var(--v2-text-2xl); font-weight: var(--v2-font-bold); color: var(--v2-brand-primary); }
.ca__rfm-sc-l { display: block; font-size: var(--v2-text-xs); color: var(--v2-text-3); margin-top: 2px; }
.ca__detail-action { margin-top: var(--v2-space-3); padding: var(--v2-space-3); background: var(--v2-ai-purple-bg); border-radius: var(--v2-radius-md); }
.ca__detail-action p { font-size: 13px; color: var(--v2-text-2); margin: var(--v2-space-2) 0 0; line-height: 1.6; }
.ca__detail-ask { display: flex; align-items: center; justify-content: center; gap: 6px; padding: 8px; border: 1px solid rgba(0,0,0,0.08); border-radius: 8px; background: #fff; font-size: 12px; font-weight: 500; color: #18181b; cursor: pointer; transition: all 0.15s; font-family: inherit; }
.ca__detail-ask:hover { background: #f4f4f5; border-color: rgba(0,0,0,0.15); }
.ca__empty-detail { display: flex; flex-direction: column; align-items: center; justify-content: center; flex: 1; gap: 8px; color: #a1a1aa; }
.ca__empty-detail p { font-size: 12px; margin: 0; }

@media (max-width: 1200px) {
  .ca__kpis { grid-template-columns: repeat(2, 1fr); }
  .ca__charts { grid-template-columns: 1fr; }
}
</style>
