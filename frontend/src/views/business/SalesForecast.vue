<template>
  <div class="fc">
    <PageHeaderV2 title="预测与决策" desc="多模型融合预测 · 置信区间 · 决策建议">
      <template #actions>
        <button class="fc__toggle-panel" :class="{ 'fc__toggle-panel--active': showRight }" @click="showRight = !showRight" title="AI 面板">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="3"/><line x1="15" y1="3" x2="15" y2="21"/></svg>
        </button>
      </template>
    </PageHeaderV2>

    <SplitInspector :hide-right="!showRight">
      <template #main>
        <div class="fc__main-scroll">
          <!-- ① 模型摘要 KPI -->
          <div class="fc__kpis">
            <ClickToAsk question="Stacking 融合模型的精度如何？各单模型表现对比分析" @ask="onAskAI">
              <StatCardV2 class="fc__kpi-hero" label="Stacking MAPE" :value="mapeStacking + '%'" trend-dir="up" sub="融合模型精度" clickable />
            </ClickToAsk>
            <ClickToAsk question="当前参与对比的模型有哪些？各模型的优劣势分析" @ask="onAskAI">
              <StatCardV2 label="模型数量" :value="modelComparison.length || '--'" sub="参与对比" clickable />
            </ClickToAsk>
            <ClickToAsk question="未来 7 天销售预测趋势和备货建议" @ask="onAskAI">
              <StatCardV2 label="7 天预测" :value="forecast7d.length ? forecast7d.length + '天' : '--'" sub="覆盖天数" clickable />
            </ClickToAsk>
            <StatCardV2 label="预测状态" :value="summaryDegraded ? '降级' : summaryError ? '异常' : '正常'" :trend-dir="summaryError ? 'down' : 'up'" sub="数据源" />
          </div>

          <!-- ② 模型对比 + 主预测趋势 -->
          <div class="fc__charts">
            <SectionCardV2 title="模型精度对比" class="fc__comp">
              <SkeletonBlockV2 v-if="summaryLoading" :rows="5" />
              <ErrorStateV2 v-else-if="summaryError" :desc="summaryError" @retry="loadSummary" />
              <template v-else-if="modelComparison.length">
                <div style="height:240px"><v-chart :option="compOption" autoresize /></div>
              </template>
              <EmptyStateV2 v-else title="暂无模型数据" />
            </SectionCardV2>

            <SectionCardV2 title="近 7 天预测趋势" subtitle="含置信区间" class="fc__trend">
              <template #header><AIInlineLabel v-if="summaryDegraded" text="缓存数据" size="xs" /></template>
              <SkeletonBlockV2 v-if="summaryLoading" :rows="6" />
              <ErrorStateV2 v-else-if="summaryError" :desc="summaryError" @retry="loadSummary" />
              <div v-else-if="forecast7d.length" style="height:300px"><v-chart :option="trendOption" autoresize /></div>
              <EmptyStateV2 v-else title="暂无趋势数据" />
            </SectionCardV2>
          </div>

          <!-- ③ 自定义预测 -->
          <SectionCardV2 title="自定义预测" subtitle="输入参数运行模型" class="fc__predict">
            <template #header>
              <el-button v-if="predictResult" size="small" @click="exportResult">导出结果</el-button>
            </template>
            <el-form :model="predictForm" inline size="small" class="fc__form">
              <el-form-item label="SKU"><el-input v-model="predictForm.sku_code" placeholder="LY-TEA-001" style="width:140px" /></el-form-item>
              <el-form-item label="门店"><el-input v-model="predictForm.store_id" placeholder="NDE-001" style="width:120px" /></el-form-item>
              <el-form-item label="天数"><el-input-number v-model="predictForm.days" :min="1" :max="90" style="width:110px" /></el-form-item>
              <el-form-item><el-button type="primary" :loading="predictLoading" @click="runPredict">运行预测</el-button></el-form-item>
            </el-form>

            <SkeletonBlockV2 v-if="predictLoading" :rows="5" />
            <ErrorStateV2 v-else-if="predictError" :desc="predictError" @retry="runPredict" />
            <template v-else-if="predictResult">
              <div class="fc__result-summary">
                <div class="fc__rs-item"><span class="fc__rs-label">模型</span><el-tag size="small">{{ predictResult.model_used }}</el-tag></div>
                <div class="fc__rs-item"><span class="fc__rs-label">SKU</span><span>{{ predictResult.sku_code }}</span></div>
                <div class="fc__rs-item"><span class="fc__rs-label">门店</span><span>{{ predictResult.store_id }}</span></div>
                <div class="fc__rs-item"><span class="fc__rs-label">预测天数</span><span>{{ predictResult.forecast?.length ?? 0 }} 天</span></div>
              </div>
              <div style="height:300px;margin-top:var(--v2-space-4)"><v-chart :option="predictChartOpt" autoresize /></div>
              <SectionCardV2 title="预测明细" :flush="true" style="margin-top:var(--v2-space-4)">
                <el-table :data="predictResult.forecast" size="small" max-height="260" style="width:100%">
                  <el-table-column prop="date" label="日期" width="120" />
                  <el-table-column prop="predicted" label="预测值" width="120" align="right">
                    <template #default="{ row }">{{ row.predicted?.toLocaleString() }}</template>
                  </el-table-column>
                  <el-table-column prop="lower" label="下界 (95%)" width="120" align="right">
                    <template #default="{ row }">{{ row.lower?.toLocaleString() }}</template>
                  </el-table-column>
                  <el-table-column prop="upper" label="上界 (95%)" width="120" align="right">
                    <template #default="{ row }">{{ row.upper?.toLocaleString() }}</template>
                  </el-table-column>
                  <el-table-column label="区间宽度" width="100" align="right">
                    <template #default="{ row }">{{ row.upper != null && row.lower != null ? (row.upper - row.lower).toLocaleString() : '-' }}</template>
                  </el-table-column>
                </el-table>
              </SectionCardV2>
            </template>
          </SectionCardV2>
        </div>
      </template>

      <!-- ═══ Right Panel ═══ -->
      <template #right>
        <PageAICopilotPanel
          ref="aiPanel"
          :ai="ai"
          welcome-title="AI 预测分析助手"
          welcome-desc="解读预测模型、分析趋势、提供决策建议"
          collection="forecast"
          command-bar-placeholder="询问预测相关问题...  @ 选择智能体"
          :quick-questions="quickQuestions"
          :mention-catalog="mentionCatalog"
        >
          <template #detail>
            <div v-if="predictResult" class="fc__detail">
              <h4>预测结果摘要</h4>
              <div class="fc__dl"><span>模型</span><span>{{ predictResult.model_used }}</span></div>
              <div class="fc__dl"><span>SKU</span><span>{{ predictResult.sku_code }}</span></div>
              <div class="fc__dl"><span>门店</span><span>{{ predictResult.store_id }}</span></div>
              <div class="fc__dl"><span>天数</span><span>{{ predictResult.forecast?.length ?? 0 }}</span></div>
              <div class="fc__explain-box">
                <AIInlineLabel text="预测解读" size="sm" />
                <p>{{ predictExplain }}</p>
              </div>
              <button class="fc__detail-ask" @click="aiPanel?.askAndSwitch(`基于当前预测结果给出备货和促销建议`)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
                AI 决策建议
              </button>
            </div>
            <div v-else class="fc__empty-detail">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
              <p>运行自定义预测后查看结果详情</p>
            </div>
          </template>
        </PageAICopilotPanel>
      </template>
    </SplitInspector>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { forecastApi } from '@/api/business'
import { usePageCopilot } from '@/composables/usePageCopilot'
import { baseChartOption } from '@/utils/chartDefaults'
import { exportCSV } from '@/utils/chartDefaults'
import {
  PageHeaderV2, StatCardV2, SectionCardV2, EmptyStateV2, ErrorStateV2,
  SkeletonBlockV2, AIInlineLabel, SplitInspector, ClickToAsk, PageAICopilotPanel,
} from '@/components/v2'

// ── AI Copilot ──
const ai = usePageCopilot('forecast', ['forecast_skill', 'kb_rag'])
const aiPanel = ref(null)
const showRight = ref(true)

const quickQuestions = [
  '当前预测模型整体表现如何？',
  '未来 7 天销售趋势和备货建议',
  '哪些因素影响预测精度？',
]

const mentionCatalog = [
  { id: 'forecast', label: '销售预测', type: 'skill', icon: '📈' },
  { id: 'inventory_skill', label: '库存管理', type: 'skill', icon: '📦' },
  { id: 'customer_intel', label: '客群洞察', type: 'skill', icon: '👥' },
  { id: 'kb_rag', label: '知识库', type: 'collection', icon: '📚' },
]

function onAskAI({ question }) {
  showRight.value = true
  aiPanel.value?.askAndSwitch(question)
}

// ── Summary ──────────────────────────────────────────────────
const summaryLoading = ref(false), summaryError = ref(''), summaryDegraded = ref(false)
const mapeStacking = ref('-'), modelComparison = ref([]), forecast7d = ref([])

const compOption = computed(() => baseChartOption({
  grid: { left: 100, right: 40, top: 10, bottom: 30 },
  xAxis: { type: 'value', name: 'MAPE %' },
  yAxis: { type: 'category', data: modelComparison.value.map(m => m.model).reverse() },
  series: [{
    type: 'bar', data: [...modelComparison.value].reverse().map(m => m.mape), barWidth: 16,
    itemStyle: { color: (p) => p.data === Math.min(...modelComparison.value.map(m => m.mape)) ? '#16a34a' : '#2563eb', borderRadius: [0, 4, 4, 0] },
    label: { show: true, position: 'right', fontSize: 11, formatter: '{c}%' },
  }],
}))

const trendOption = computed(() => {
  const dates = forecast7d.value.map(d => d.date)
  const predicted = forecast7d.value.map(d => d.predicted)
  const upper = forecast7d.value.map(d => d.upper)
  const lower = forecast7d.value.map(d => d.lower)
  return baseChartOption({
    xAxis: { type: 'category', data: dates },
    yAxis: { type: 'value' },
    series: [
      { name: '预测值', type: 'line', data: predicted, smooth: true, lineStyle: { width: 2.5 }, symbol: 'circle', symbolSize: 6, z: 3 },
      { name: '置信下界', type: 'line', data: lower, lineStyle: { width: 0 }, symbol: 'none', stack: 'band', areaStyle: { opacity: 0 } },
      { name: '置信区间', type: 'line', data: lower.map((v, i) => (upper[i] ?? 0) - (v ?? 0)), lineStyle: { width: 0 }, symbol: 'none', stack: 'band', areaStyle: { color: 'rgba(37,99,235,.12)' } },
    ],
  })
})

async function loadSummary() {
  summaryLoading.value = true; summaryError.value = ''
  try {
    const d = await forecastApi.getSummary()
    mapeStacking.value = d?.mape_stacking ?? '-'
    modelComparison.value = d?.model_comparison ?? []
    forecast7d.value = d?.forecast_7d ?? []
    summaryDegraded.value = !!d?._meta?.degraded
  } catch (e) { summaryError.value = e?.response?.data?.message || '加载预测汇总失败' }
  finally { summaryLoading.value = false }
}

// ── 自定义预测 ───────────────────────────────────────────────
const predictForm = reactive({ sku_code: 'LY-TEA-001', store_id: 'NDE-001', days: 30 })
const predictLoading = ref(false), predictError = ref(''), predictResult = ref(null)

const predictChartOpt = computed(() => {
  const fc = predictResult.value?.forecast ?? []
  const dates = fc.map(d => d.date), predicted = fc.map(d => d.predicted), upper = fc.map(d => d.upper), lower = fc.map(d => d.lower)
  return baseChartOption({
    xAxis: { type: 'category', data: dates, axisLabel: { rotate: fc.length > 14 ? 45 : 0 } },
    yAxis: { type: 'value' },
    dataZoom: [{ type: 'inside' }],
    series: [
      { name: '预测值', type: 'line', data: predicted, smooth: true, lineStyle: { width: 2.5 }, areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(37,99,235,.10)' }, { offset: 1, color: 'rgba(37,99,235,.01)' }] } }, symbol: 'none', z: 3 },
      { name: '置信下界', type: 'line', data: lower, lineStyle: { width: 0 }, symbol: 'none', stack: 'band', areaStyle: { opacity: 0 } },
      { name: '置信区间', type: 'line', data: lower.map((v, i) => (upper[i] ?? 0) - (v ?? 0)), lineStyle: { width: 0 }, symbol: 'none', stack: 'band', areaStyle: { color: 'rgba(37,99,235,.08)' } },
    ],
  })
})

const predictExplain = computed(() => {
  const fc = predictResult.value?.forecast ?? []
  if (!fc.length) return ''
  const avg = fc.reduce((s, d) => s + (d.predicted || 0), 0) / fc.length
  const maxW = Math.max(...fc.map(d => (d.upper || 0) - (d.lower || 0)))
  return `预测 ${fc.length} 天，日均预测值 ${avg.toFixed(0)}。最大置信区间宽度 ${maxW.toFixed(0)}，表明${maxW > avg * 0.5 ? '不确定性较高，建议参考下界做保守决策' : '预测较为稳定'}。模型使用 ${predictResult.value?.model_used || 'Stacking'}。`
})

async function runPredict() {
  predictLoading.value = true; predictError.value = ''; predictResult.value = null
  try {
    predictResult.value = await forecastApi.predict(predictForm)
    ai.setContext({
      predict_sku: predictForm.sku_code,
      predict_days: predictForm.days,
      model_used: predictResult.value?.model_used,
    })
  }
  catch (e) { predictError.value = e?.response?.data?.message || '预测请求失败' }
  finally { predictLoading.value = false }
}

function exportResult() {
  if (!predictResult.value?.forecast?.length) return ElMessage.info('无数据可导出')
  exportCSV(predictResult.value.forecast, `forecast_${predictForm.sku_code}_${predictForm.days}d`)
  ElMessage.success('已导出 CSV')
}

onMounted(async () => {
  loadSummary()
  await ai.init()
  // [TEMP] 暂停自动 AI 问答，后续测试完毕再打开
  // if (!ai.messages.value.length) {
  //   ai.ask('当前预测模型概览：Stacking 精度、单模型对比和 7 天趋势解读')
  // }
})
</script>

<style scoped>
.fc { display: flex; flex-direction: column; gap: var(--v2-space-3); height: 100%; }
.fc__main-scroll { display: flex; flex-direction: column; gap: var(--v2-space-4); padding: var(--v2-space-3); overflow-y: auto; min-height: 0; }
.fc__main-scroll > * { flex-shrink: 0; }
.fc__kpis { display: grid; grid-template-columns: 1.5fr 1fr 1fr 1fr; gap: var(--v2-space-4); }
.fc__kpi-hero { border-left: 3px solid var(--v2-success); }
.fc__charts { display: grid; grid-template-columns: 380px 1fr; gap: var(--v2-space-4); }
.fc__predict { margin-bottom: 0; }
.fc__form { margin-bottom: var(--v2-space-4); }

.fc__result-summary { display: flex; gap: var(--v2-space-6); padding: var(--v2-space-3) var(--v2-space-4); background: var(--v2-bg-sunken); border-radius: var(--v2-radius-md); }
.fc__rs-item { display: flex; align-items: center; gap: var(--v2-space-2); font-size: var(--v2-text-sm); }
.fc__rs-label { color: var(--v2-text-3); }

/* Toggle Panel Button */
.fc__toggle-panel { display: flex; align-items: center; justify-content: center; width: 28px; height: 28px; border: 1px solid var(--v2-border-1); border-radius: var(--v2-radius-md); background: var(--v2-bg-card); color: var(--v2-text-3); cursor: pointer; transition: all var(--v2-trans-fast); }
.fc__toggle-panel:hover { color: var(--v2-text-1); }
.fc__toggle-panel--active { background: var(--v2-text-1); color: #fff; border-color: var(--v2-text-1); }

/* Detail panel */
.fc__detail { display: flex; flex-direction: column; gap: var(--v2-space-3); padding: 12px; overflow-y: auto; }
.fc__detail h4 { font-size: 12px; font-weight: 600; color: #71717a; text-transform: uppercase; letter-spacing: .5px; margin: 0 0 8px; padding-bottom: 6px; border-bottom: 1px solid rgba(0,0,0,0.06); }
.fc__dl { display: flex; justify-content: space-between; padding: 3px 0; font-size: 13px; }
.fc__dl > span:first-child { color: #71717a; }
.fc__dl > span:last-child { color: #18181b; font-variant-numeric: tabular-nums; }
.fc__explain-box { margin-top: 8px; padding: 10px; background: rgba(124,58,237,.04); border-radius: 8px; border: 1px solid rgba(124,58,237,.1); }
.fc__explain-box p { font-size: 12px; color: #52525b; margin: 4px 0 0; line-height: 1.6; }
.fc__detail-ask { display: flex; align-items: center; justify-content: center; gap: 6px; padding: 8px; border: 1px solid rgba(0,0,0,0.08); border-radius: 8px; background: #fff; font-size: 12px; font-weight: 500; color: #18181b; cursor: pointer; transition: all 0.15s; font-family: inherit; margin-top: 4px; }
.fc__detail-ask:hover { background: #f4f4f5; border-color: rgba(0,0,0,0.15); }
.fc__empty-detail { display: flex; flex-direction: column; align-items: center; justify-content: center; flex: 1; gap: 8px; color: #a1a1aa; }
.fc__empty-detail p { font-size: 12px; margin: 0; }

@media (max-width: 1200px) {
  .fc__kpis { grid-template-columns: repeat(2, 1fr); }
  .fc__charts { grid-template-columns: 1fr; }
}
</style>
