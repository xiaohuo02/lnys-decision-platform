<template>
  <div class="rp">
    <PageHeaderV2 title="报告工作台" desc="模板选择 · 任务管理 · 报告生成">
      <template #actions>
        <button class="rp__toggle-panel" :class="{ 'rp__toggle-panel--active': showRight }" @click="showRight = !showRight" title="AI 面板">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="3"/><line x1="15" y1="3" x2="15" y2="21"/></svg>
        </button>
      </template>
    </PageHeaderV2>

    <SplitInspector :hide-right="!showRight">
      <template #main>
        <div class="rp__main-scroll">
          <!-- ① 模板选择 + 预览 -->
          <SectionCardV2 title="报告模板" subtitle="选择模板查看预览">
            <div class="rp__tpls">
              <div v-for="tpl in templates" :key="tpl.id" class="rp__tpl" :class="{ 'rp__tpl--active': selectedTemplate === tpl.id }" @click="selectedTemplate = tpl.id">
                <div class="rp__tpl-icon">{{ tpl.emoji }}</div>
                <div class="rp__tpl-body">
                  <div class="rp__tpl-name">{{ tpl.name }}</div>
                  <div class="rp__tpl-desc">{{ tpl.desc }}</div>
                </div>
                <div v-if="selectedTemplate === tpl.id" class="rp__tpl-check">✓</div>
              </div>
            </div>
            <div class="rp__preview">
              <div class="rp__preview-header">
                <div class="rp__preview-title">预览: {{ activeTpl?.name }}</div>
                <el-button type="primary" size="small" @click="applyTemplate">使用此模板生成</el-button>
              </div>
              <div class="rp__preview-modules">
                <span v-for="mod in activeTpl?.modules" :key="mod" class="rp__preview-mod">{{ mod }}</span>
              </div>
              <p class="rp__preview-desc">{{ activeTpl?.preview }}</p>
            </div>
          </SectionCardV2>

          <!-- ② 配置 + Job List -->
          <div class="rp__body">
            <SectionCardV2 title="报告配置" class="rp__config">
              <el-form :model="configForm" label-width="90px" size="small">
                <el-form-item label="标题"><el-input v-model="configForm.title" placeholder="经营分析周报" /></el-form-item>
                <el-form-item label="时间范围">
                  <el-date-picker v-model="configForm.dateRange" type="daterange" range-separator="至" start-placeholder="开始" end-placeholder="结束" style="width:100%" value-format="YYYY-MM-DD" />
                </el-form-item>
                <el-form-item label="包含模块">
                  <el-checkbox-group v-model="configForm.modules">
                    <el-checkbox v-for="m in moduleOptions" :key="m.value" :value="m.value">{{ m.label }}</el-checkbox>
                  </el-checkbox-group>
                </el-form-item>
                <el-form-item label="格式">
                  <el-radio-group v-model="configForm.format">
                    <el-radio value="markdown">Markdown</el-radio>
                    <el-radio value="html">HTML</el-radio>
                  </el-radio-group>
                </el-form-item>
                <el-form-item><el-button type="primary" :loading="exporting" @click="handleExport">生成报告</el-button></el-form-item>
              </el-form>
            </SectionCardV2>

            <SectionCardV2 title="任务队列" :flush="true" class="rp__jobs">
              <template v-if="jobs.length">
                <div v-for="job in jobs" :key="job.id" class="rp__job" @click="selectJob(job)">
                  <div class="rp__job-status">
                    <span class="rp__job-dot" :class="'rp__job-dot--' + job.status" />
                    <span class="rp__job-state">{{ statusLabel[job.status] }}</span>
                  </div>
                  <div class="rp__job-info">
                    <div class="rp__job-title">{{ job.title }}</div>
                    <div class="rp__job-meta">{{ job.template }} · {{ job.format }} · {{ job.createdAt }}</div>
                  </div>
                  <div class="rp__job-actions">
                    <el-button v-if="job.status === 'done'" size="small" type="primary" text @click.stop="downloadJob(job)">下载</el-button>
                    <el-button v-else-if="job.status === 'failed'" size="small" type="danger" text @click.stop="retryJob(job)">重试</el-button>
                    <span v-else-if="job.status === 'running'" class="rp__job-progress">{{ job.progress }}%</span>
                  </div>
                </div>
              </template>
              <EmptyStateV2 v-else title="暂无任务" />
            </SectionCardV2>
          </div>
        </div>
      </template>

      <!-- ═══ Right Panel ═══ -->
      <template #right>
        <PageAICopilotPanel
          ref="aiPanel"
          :ai="ai"
          welcome-title="AI 报告助手"
          welcome-desc="报告内容建议、数据摘要、格式优化"
          collection="report"
          command-bar-placeholder="询问报告相关问题...  @ 选择智能体"
          :quick-questions="quickQuestions"
          :mention-catalog="mentionCatalog"
        >
          <template #detail>
            <div v-if="selectedJob" class="rp__detail">
              <h4>任务详情</h4>
              <div class="rp__dl"><span>标题</span><span>{{ selectedJob.title }}</span></div>
              <div class="rp__dl"><span>模板</span><span>{{ selectedJob.template }}</span></div>
              <div class="rp__dl"><span>格式</span><span>{{ selectedJob.format }}</span></div>
              <div class="rp__dl"><span>状态</span><span>{{ statusLabel[selectedJob.status] }}</span></div>
              <div class="rp__dl"><span>创建时间</span><span>{{ selectedJob.createdAt }}</span></div>
              <button class="rp__detail-ask" @click="aiPanel?.askAndSwitch(`帮我总结「${selectedJob.title}」报告的核心要点和建议`)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
                AI 报告摘要
              </button>
            </div>
            <div v-else class="rp__detail">
              <h4>当前模板</h4>
              <div class="rp__dl"><span>名称</span><span>{{ activeTpl?.name }}</span></div>
              <div class="rp__dl"><span>描述</span><span>{{ activeTpl?.desc }}</span></div>
              <div class="rp__dl"><span>模块数</span><span>{{ activeTpl?.modules?.length }}</span></div>
              <button class="rp__detail-ask" @click="aiPanel?.askAndSwitch(`「${activeTpl?.name}」模板适用于什么场景？有什么改善建议？`)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
                AI 模板建议
              </button>
            </div>
          </template>
        </PageAICopilotPanel>
      </template>
    </SplitInspector>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { reportApi } from '@/api/business'
import { usePageCopilot } from '@/composables/usePageCopilot'
import { PageHeaderV2, SectionCardV2, EmptyStateV2, SplitInspector, PageAICopilotPanel } from '@/components/v2'

// ── AI Copilot ──
const ai = usePageCopilot('report', ['kb_rag'])
const aiPanel = ref(null)
const showRight = ref(false)
const selectedJob = ref(null)

const quickQuestions = [
  '本周经营报告应包含哪些重点内容？',
  '如何让报告更具可读性和说服力？',
  '给出报告数据摘要和趋势解读',
]

const mentionCatalog = [
  { id: 'forecast', label: '销售预测', type: 'skill', icon: '📈' },
  { id: 'customer_intel', label: '客群洞察', type: 'skill', icon: '👥' },
  { id: 'kb_rag', label: '知识库', type: 'collection', icon: '📚' },
]

function selectJob(job) {
  selectedJob.value = job
  showRight.value = true
  aiPanel.value?.switchTab('detail')
}

const templates = [
  { id: 'weekly', name: '经营周报', desc: '销售 + 客户 + 库存 + 风控', emoji: '📊', modules: ['KPI 总览', '销售趋势', '客户分析', '库存健康', '风控摘要'], preview: '包含本周核心经营指标、销售趋势对比、客户价值变化、库存预警摘要及风控拦截统计。适合管理层周会。' },
  { id: 'customer', name: '客户洞察报告', desc: 'RFM + CLV + 流失分析', emoji: '👥', modules: ['RFM 分层', 'CLV 排行', '流失风险', '客群分布'], preview: '深度客户价值分析，涵盖 RFM 分层、CLV 预测排行、高流失风险客户清单及客群分布变化。' },
  { id: 'forecast', name: '预测分析报告', desc: '多模型预测 + 误差分析', emoji: '📈', modules: ['模型对比', '预测趋势', '置信区间', '误差分析'], preview: '多模型融合预测结果，包括 MAPE 对比、置信区间、未来趋势及备货建议。' },
  { id: 'risk', name: '风控审计报告', desc: '欺诈统计 + HITL 审核', emoji: '🛡️', modules: ['拦截统计', '风险分层', '规则命中', '审核记录'], preview: '风控系统运行报告，包括拦截率、风险分层分布、热点规则命中及人工审核明细。' },
]

const selectedTemplate = ref('weekly')
const activeTpl = computed(() => templates.find(t => t.id === selectedTemplate.value))

const moduleOptions = [
  { value: 'kpi', label: 'KPI 总览' }, { value: 'customer', label: '客户分析' },
  { value: 'forecast', label: '销售预测' }, { value: 'inventory', label: '库存健康' },
  { value: 'fraud', label: '风控摘要' }, { value: 'sentiment', label: '舆情分析' },
]

const configForm = reactive({ title: '', dateRange: [], modules: ['kpi', 'customer', 'forecast'], format: 'markdown' })
const exporting = ref(false)

const _FORMAT_EXT = { markdown: '.md', md: '.md', html: '.html' }
const statusLabel = { queued: '排队中', running: '生成中', done: '已完成', failed: '失败' }
let jobId = 1
const jobs = ref([])

onMounted(async () => {
  try {
    const res = await reportApi.getList()
    const list = res?.items ?? []
    list.forEach(r => {
      const requestedFormat = r.requested_format || 'markdown'
      jobs.value.push({
        id: jobId++,
        title: r.title,
        template: r.report_type,
        template_id: r.report_type,
        format: formatLabel(requestedFormat),
        createdAt: r.generated_at,
        status: 'done',
        progress: 100,
        report_id: r.report_id,
        download_format: requestedFormat,
      })
    })
  } catch { /* silent */ }
  await ai.init()
})

function formatLabel(format) {
  const normalized = (format || 'markdown').toLowerCase()
  if (normalized === 'html') return 'HTML'
  return 'Markdown'
}

function applyTemplate() {
  const tpl = activeTpl.value
  if (!tpl) return
  configForm.title = tpl.name + ' - ' + new Date().toLocaleDateString()
  configForm.modules = moduleOptions.filter(m => tpl.modules.some(tm => tm.includes(m.label))).map(m => m.value)
  if (!configForm.modules.length) configForm.modules = ['kpi', 'customer', 'forecast']
  nextTick(() => {
    document.querySelector('.rp__config')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
  ElMessage.success(`已应用「${tpl.name}」模板配置`)
}

async function handleExport() {
  exporting.value = true
  const title = configForm.title || `${activeTpl.value?.name} - ${new Date().toLocaleDateString()}`
  const job = {
    id: jobId++,
    title,
    template: activeTpl.value?.name,
    template_id: selectedTemplate.value,
    format: formatLabel(configForm.format),
    createdAt: new Date().toLocaleString(),
    status: 'running',
    progress: 30,
    report_id: null,
    download_format: configForm.format,
  }
  jobs.value.unshift(job)
  try {
    const res = await reportApi.generate({
      report_type: selectedTemplate.value,
      title,
      modules: configForm.modules,
      date_start: configForm.dateRange?.[0] || undefined,
      date_end: configForm.dateRange?.[1] || undefined,
      format: configForm.format,
    })
    job.report_id = res?.report_id ?? null
    job.download_format = res?.requested_format || configForm.format
    job.format = formatLabel(job.download_format)
    job.status = 'done'; job.progress = 100
    ElMessage.success('报告已生成')
  } catch (e) {
    job.status = 'failed'; job.progress = 0
    ElMessage.error(e?.response?.data?.message || '报告生成失败')
  } finally { exporting.value = false }
}

function retryJob(job) { job.status = 'queued'; job.progress = 0; handleExportJob(job) }
async function handleExportJob(job) {
  job.status = 'running'; job.progress = 30
  try {
    const format = job.download_format || 'markdown'
    const res = await reportApi.generate({ report_type: job.template_id || selectedTemplate.value, title: job.title, format })
    job.report_id = res?.report_id ?? null
    job.download_format = res?.requested_format || format
    job.format = formatLabel(job.download_format)
    job.status = 'done'; job.progress = 100
  } catch { job.status = 'failed'; job.progress = 0 }
}
async function downloadJob(job) {
  if (!job.report_id) return ElMessage.warning('无可下载的报告')
  try {
    const format = job.download_format || 'markdown'
    const blob = await reportApi.download(job.report_id, format)
    const url = URL.createObjectURL(new Blob([blob]))
    const ext = _FORMAT_EXT[(format || 'markdown').toLowerCase()] || '.md'
    const a = document.createElement('a'); a.href = url; a.download = `${job.title}${ext}`; a.click(); URL.revokeObjectURL(url)
  } catch { ElMessage.error('下载失败') }
}

</script>

<style scoped>
.rp { display: flex; flex-direction: column; gap: var(--v2-space-3); height: 100%; }
.rp__main-scroll { display: flex; flex-direction: column; gap: var(--v2-space-4); padding: var(--v2-space-3); overflow-y: auto; min-height: 0; }
.rp__main-scroll > * { flex-shrink: 0; }

/* Toggle */
.rp__toggle-panel { display: flex; align-items: center; justify-content: center; width: 28px; height: 28px; border: 1px solid var(--v2-border-1); border-radius: var(--v2-radius-md); background: var(--v2-bg-card); color: var(--v2-text-3); cursor: pointer; transition: all var(--v2-trans-fast); }
.rp__toggle-panel:hover { color: var(--v2-text-1); }
.rp__toggle-panel--active { background: var(--v2-text-1); color: #fff; border-color: var(--v2-text-1); }

/* Templates */
.rp__tpls { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--v2-space-3); margin-bottom: var(--v2-space-4); }
.rp__tpl { display: flex; align-items: center; gap: var(--v2-space-3); padding: var(--v2-space-3) var(--v2-space-4); border: 2px solid var(--v2-border-2); border-radius: var(--v2-radius-lg); cursor: pointer; transition: all var(--v2-trans-fast); position: relative; }
.rp__tpl:hover { border-color: var(--v2-brand-hover); }
.rp__tpl--active { border-color: var(--v2-brand-primary); background: var(--v2-brand-bg); }
.rp__tpl-icon { font-size: 24px; flex-shrink: 0; }
.rp__tpl-body { min-width: 0; }
.rp__tpl-name { font-size: var(--v2-text-sm); font-weight: var(--v2-font-semibold); color: var(--v2-text-1); }
.rp__tpl-desc { font-size: var(--v2-text-xs); color: var(--v2-text-3); }
.rp__tpl-check { position: absolute; top: 6px; right: 8px; font-size: var(--v2-text-xs); color: var(--v2-brand-primary); font-weight: var(--v2-font-bold); }

.rp__preview { padding: var(--v2-space-4); background: var(--v2-bg-sunken); border-radius: var(--v2-radius-lg); }
.rp__preview-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--v2-space-2); }
.rp__preview-title { font-size: var(--v2-text-md); font-weight: var(--v2-font-semibold); color: var(--v2-text-1); }
.rp__preview-modules { display: flex; flex-wrap: wrap; gap: var(--v2-space-1); margin-bottom: var(--v2-space-2); }
.rp__preview-mod { font-size: var(--v2-text-xs); padding: 1px 8px; background: var(--v2-brand-bg); color: var(--v2-brand-primary); border-radius: var(--v2-radius-sm); }
.rp__preview-desc { font-size: var(--v2-text-sm); color: var(--v2-text-2); line-height: var(--v2-leading-relaxed); margin: 0; }

/* Config + Jobs */
.rp__body { display: grid; grid-template-columns: 420px 1fr; gap: var(--v2-space-4); }

.rp__job { display: flex; align-items: center; gap: var(--v2-space-3); padding: var(--v2-space-3) var(--v2-space-4); border-bottom: 1px solid var(--v2-border-2); cursor: pointer; transition: background var(--v2-trans-fast); }
.rp__job:last-child { border-bottom: none; }
.rp__job:hover { background: var(--v2-bg-hover); }
.rp__job-status { display: flex; align-items: center; gap: var(--v2-space-2); width: 80px; flex-shrink: 0; }
.rp__job-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--v2-gray-300); flex-shrink: 0; }
.rp__job-dot--done { background: var(--v2-success); } .rp__job-dot--running { background: var(--v2-brand-primary); animation: pulse 1.2s infinite; } .rp__job-dot--queued { background: var(--v2-warning); } .rp__job-dot--failed { background: var(--v2-error); }
@keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:.4; } }
.rp__job-state { font-size: var(--v2-text-xs); color: var(--v2-text-3); }
.rp__job-info { flex: 1; min-width: 0; }
.rp__job-title { font-size: var(--v2-text-sm); font-weight: var(--v2-font-medium); color: var(--v2-text-1); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rp__job-meta { font-size: var(--v2-text-xs); color: var(--v2-text-4); }
.rp__job-actions { flex-shrink: 0; }
.rp__job-progress { font-size: var(--v2-text-xs); color: var(--v2-brand-primary); font-weight: var(--v2-font-semibold); font-variant-numeric: tabular-nums; }

/* Detail */
.rp__detail { display: flex; flex-direction: column; gap: var(--v2-space-3); padding: 12px; overflow-y: auto; }
.rp__detail h4 { font-size: 12px; font-weight: 600; color: #71717a; text-transform: uppercase; letter-spacing: .5px; margin: 0 0 8px; padding-bottom: 6px; border-bottom: 1px solid rgba(0,0,0,0.06); }
.rp__dl { display: flex; justify-content: space-between; padding: 3px 0; font-size: 13px; }
.rp__dl > span:first-child { color: #71717a; } .rp__dl > span:last-child { color: #18181b; }
.rp__detail-ask { display: flex; align-items: center; justify-content: center; gap: 6px; padding: 8px; border: 1px solid rgba(0,0,0,0.08); border-radius: 8px; background: #fff; font-size: 12px; font-weight: 500; color: #18181b; cursor: pointer; transition: all 0.15s; font-family: inherit; margin-top: 4px; }
.rp__detail-ask:hover { background: #f4f4f5; border-color: rgba(0,0,0,0.15); }

@media (max-width: 1200px) {
  .rp__tpls { grid-template-columns: repeat(2, 1fr); }
  .rp__body { grid-template-columns: 1fr; }
}
</style>
