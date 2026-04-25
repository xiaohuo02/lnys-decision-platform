<template>
  <div class="so page-enter-active">
    <PageHeaderV2 title="舆情总览" desc="情感分布 · 话题聚类 · AI 联动分析">
      <template #actions>
        <span class="so__time">{{ currentTime }}</span>
        <router-link to="/sentiment/analyze" class="so__link-btn">
          <Zap :size="13" /> 进入分析工具
        </router-link>
        <button class="so__refresh" @click="refreshAll" :disabled="loading">
          <RefreshCw :size="14" :class="{ 'is-spin': loading }" /> 刷新
        </button>
        <button class="so__toggle-panel" :class="{ 'so__toggle-panel--active': showRight }" @click="showRight = !showRight" title="AI 面板">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="3"/><line x1="15" y1="3" x2="15" y2="21"/></svg>
        </button>
      </template>
    </PageHeaderV2>

    <SplitInspector :hide-right="!showRight">
      <template #main>
        <div class="so__main-scroll">
          <!-- ── KPI Strip ── -->
          <div class="so__kpi">
            <ClickToAsk v-for="k in kpis" :key="k.key" :question="k.question || k.label" @ask="onAskAI">
              <div class="kpi" :class="k.colorClass">
                <div class="kpi__val">
                  <Odometer :value="k.value" :decimals="k.decimals || 0" />
                  <span v-if="k.suffix" class="kpi__suffix">{{ k.suffix }}</span>
                </div>
                <div class="kpi__label">{{ k.label }}</div>
                <div class="kpi__sub" :class="k.subClass">{{ k.sub }}</div>
              </div>
            </ClickToAsk>
          </div>

    <!-- ── Charts: Distribution + Trend ── -->
    <div class="so__main">
      <div class="so__card">
        <div class="so__card-hd">
          <span class="so__sec-title">情感分布</span>
        </div>
        <div class="so__card-body">
          <v-chart v-if="overview" :option="distOption" autoresize />
          <div v-else class="so__empty">暂无数据</div>
        </div>
      </div>
      <div class="so__card so__card--wide">
        <div class="so__card-hd">
          <span class="so__sec-title">近 30 天情感趋势</span>
          <span class="so__chart-legend">
            <span class="legend__dot legend__dot--solid"></span> 均分
          </span>
        </div>
        <div class="so__card-body">
          <v-chart v-if="trendData.length" :option="trendOption" autoresize />
          <div v-else class="so__empty">暂无趋势</div>
        </div>
      </div>
    </div>

    <!-- ── Topics ── -->
    <div class="so__card so__card--full">
      <div class="so__card-hd">
        <span class="so__sec-title">LDA 话题聚类</span>
        <span class="so__sec-sub">{{ topics.length }} 个话题</span>
      </div>
      <div class="so__topics" v-if="topics.length">
        <div v-for="t in topics" :key="t.id" class="topic" :class="'topic--' + catClass(t.category)">
          <div class="topic__hd">
            <span class="topic__id">{{ t.id }}</span>
            <span class="topic__name">{{ t.label }}</span>
            <span class="topic__cat" :class="'topic__cat--' + catClass(t.category)">{{ t.category }}</span>
          </div>
          <div class="topic__kws">
            <span v-for="kw in t.keywords" :key="kw" class="topic__kw">{{ kw }}</span>
          </div>
        </div>
      </div>
      <div v-else class="so__empty">暂无话题数据</div>
    </div>

          <!-- ── AI Insight (static summary) ── -->
          <div class="so__insight" v-if="insightText">
            <div class="so__insight-hd">
              <Sparkles :size="12" />
              <span>AI 舆情洞察</span>
            </div>
            <p class="so__insight-text">{{ insightText }}</p>
          </div>
        </div><!-- .so__main-scroll -->
      </template>

      <template #right>
        <PageAICopilotPanel
          ref="aiPanel"
          :ai="ai"
          welcome-title="AI 舆情助手"
          welcome-desc="解读情感指标、挖掘话题、跨客群分析"
          collection="sentiment"
          command-bar-placeholder="询问舆情相关问题...  @ 选择智能体"
          :quick-questions="quickQuestions"
          :mention-catalog="mentionCatalog"
        >
          <template #detail>
            <div v-if="overview" class="so__detail">
              <h4>情感指标摘要</h4>
              <div class="so__dl"><span>7日均分</span><span>{{ overview.avg_score_7d?.toFixed(2) ?? '-' }}</span></div>
              <div class="so__dl"><span>正面占比</span><span>{{ overview.positive_pct?.toFixed(1) ?? '-' }}%</span></div>
              <div class="so__dl"><span>负面占比</span><span>{{ overview.negative_pct?.toFixed(1) ?? '-' }}%</span></div>
              <div class="so__dl"><span>中性占比</span><span>{{ overview.neutral_pct?.toFixed(1) ?? '-' }}%</span></div>
              <div class="so__dl"><span>话题数</span><span>{{ topics.length }}</span></div>
              <div v-if="overview.alert" class="so__detail-alert">
                <AlertTriangle :size="12" /> 舆情预警已触发
              </div>
              <button class="so__detail-ask" @click="askCrossCustomer">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
                分析负面话题（跨客群）
              </button>
              <button class="so__detail-ask" @click="aiPanel?.askAndSwitch('生成一份本周舆情简报')">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                生成本周舆情简报
              </button>
            </div>
            <div v-else class="so__empty-detail">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
              <p>加载数据后查看指标摘要</p>
            </div>
          </template>
        </PageAICopilotPanel>
      </template>
    </SplitInspector>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { RefreshCw, Sparkles, Zap, AlertTriangle } from 'lucide-vue-next'
import { useTheme } from '@/composables/useTheme'
import { sentimentApi } from '@/api/business'
import { toSentimentOverview, toSentimentTopics } from '@/adapters/sentiment'
import {
  PageHeaderV2, SplitInspector, PageAICopilotPanel, ClickToAsk, Odometer,
} from '@/components/v2'
import { usePageCopilot } from '@/composables/usePageCopilot'

const { isDark } = useTheme()
const loading = ref(false)

// ── AI Copilot ──
const ai = usePageCopilot('sentiment', ['sentiment', 'kb_rag'])
const aiPanel = ref(null)
const showRight = ref(true)

const quickQuestions = [
  '过去 7 天舆情整体趋势和异常',
  '负面评论主要集中在哪些话题？',
  '哪些客户可能受到负面舆情影响？',
]

const mentionCatalog = [
  { id: 'sentiment', label: '舆情分析', type: 'skill', icon: '💬' },
  { id: 'customer_intel', label: '客群洞察', type: 'skill', icon: '👥' },
  { id: 'kb_rag', label: '知识库', type: 'collection', icon: '📚' },
]

function onAskAI({ question }) {
  showRight.value = true
  aiPanel.value?.askAndSwitch(question)
}

function askCrossCustomer() {
  showRight.value = true
  ai.askCrossAgent('customer_intel', '负面舆情的话题分布和对应客户群', {
    negative_pct: overview.value?.negative_pct,
  })
  aiPanel.value?.switchTab('ai')
}

// ── Time ──
const currentTime = ref('')
let timer = null
function updateTime() {
  const d = new Date()
  const pad = n => String(n).padStart(2, '0')
  currentTime.value = `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// ── Data ──
const overview = ref(null)
const trendData = ref([])
const topics = ref([])

const kpis = computed(() => {
  const o = overview.value
  if (!o) return Array.from({ length: 5 }, (_, i) => ({ key: i, label: '--', value: 0, sub: '--' }))
  return [
    { key: 'avg', label: '7日均分', value: o.avg_score_7d ?? 0, decimals: 2, sub: '情感均值', subClass: '', colorClass: '',
      question: '解读当前 7 日情感均分的含义和近期变化' },
    { key: 'pos', label: '正面占比', value: o.positive_pct ?? 0, decimals: 1, suffix: '%', sub: '正面评论', subClass: 'is-up', colorClass: 'kpi--pos',
      question: '正面评论的主要话题和高频关键词' },
    { key: 'neg', label: '负面占比', value: o.negative_pct ?? 0, decimals: 1, suffix: '%', sub: '负面评论', subClass: o?.negative_pct > 30 ? 'is-warn' : '', colorClass: 'kpi--neg',
      question: '负面评论集中在哪些话题？关联哪些客户群？' },
    { key: 'neu', label: '中性占比', value: o.neutral_pct ?? 0, decimals: 1, suffix: '%', sub: '中性评论', subClass: '', colorClass: '',
      question: '中性评论常见场景分析' },
    { key: 'topics', label: '话题数', value: topics.value.length, sub: 'LDA 聚类', subClass: '', colorClass: '',
      question: '按情感倾向排序所有话题并给出影响力评估' },
  ]
})

// ── Charts ──
const catClass = (c) => ({ '正面': 'pos', '负面': 'neg', '中性': 'neu' }[c] || 'neu')

const distOption = computed(() => {
  const o = overview.value
  if (!o) return {}
  const txt = isDark.value ? '#a1a1aa' : '#71717a'
  return {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item', backgroundColor: isDark.value ? '#18181b' : '#fff', borderColor: isDark.value ? '#27272a' : '#e5e7eb', textStyle: { color: isDark.value ? '#fafafa' : '#09090b', fontSize: 11, fontFamily: 'Geist Mono, monospace' }, extraCssText: 'border-radius: 6px;' },
    color: isDark.value ? ['#4ade80', '#f87171', '#52525b'] : ['#16a34a', '#dc2626', '#a1a1aa'],
    series: [{
      type: 'pie', radius: ['48%', '74%'], center: ['50%', '50%'],
      label: { fontSize: 11, color: txt, fontFamily: 'Geist Mono', formatter: '{b}\n{d}%' },
      labelLine: { lineStyle: { color: isDark.value ? '#3f3f46' : '#d4d4d8' } },
      data: [
        { name: '正面', value: o.positive_pct },
        { name: '负面', value: o.negative_pct },
        { name: '中性', value: o.neutral_pct },
      ],
      emphasis: { scaleSize: 4 },
      itemStyle: { borderColor: isDark.value ? '#09090b' : '#ffffff', borderWidth: 2 },
    }],
  }
})

const trendOption = computed(() => {
  const txt = isDark.value ? '#a1a1aa' : '#71717a'
  const grid = isDark.value ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.05)'
  const pri = isDark.value ? '#2dd4bf' : '#0d9488'
  return {
    backgroundColor: 'transparent',
    grid: { top: 20, right: 8, bottom: 4, left: 8, containLabel: true },
    tooltip: { trigger: 'axis', backgroundColor: isDark.value ? '#18181b' : '#fff', borderColor: isDark.value ? '#27272a' : '#e5e7eb', textStyle: { color: isDark.value ? '#fafafa' : '#09090b', fontSize: 11, fontFamily: 'Geist Mono, monospace' }, extraCssText: 'border-radius: 6px;' },
    xAxis: { type: 'category', data: trendData.value.map(d => d.date?.slice(5)), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: txt, fontFamily: 'Geist Mono', fontSize: 10 } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: grid, type: 'dashed' } }, axisLabel: { color: txt, fontFamily: 'Geist Mono', fontSize: 10 } },
    series: [{ type: 'line', data: trendData.value.map(d => d.avg_score), smooth: 0.3, lineStyle: { width: 2, color: pri }, itemStyle: { color: pri }, showSymbol: false, areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: isDark.value ? 'rgba(45,212,191,0.12)' : 'rgba(13,148,136,0.08)' }, { offset: 1, color: 'transparent' }] } } }],
  }
})

const insightText = computed(() => {
  const p = []
  if (overview.value) p.push(`近 7 天情感均分 ${overview.value.avg_score_7d?.toFixed(2)}，正面占比 ${overview.value.positive_pct?.toFixed(1)}%。`)
  if (overview.value?.alert) p.push('⚠ 舆情预警已触发，负面占比偏高。')
  if (topics.value.length) p.push(`共发现 ${topics.value.length} 个话题聚类。`)
  return p.join('') || '数据加载中…'
})

// ── Load ──
async function refreshAll() {
  loading.value = true
  try {
    const [ovRes, topRes] = await Promise.allSettled([
      sentimentApi.getOverview(),
      sentimentApi.getTopics(),
    ])
    if (ovRes.status === 'fulfilled' && ovRes.value) {
      const a = toSentimentOverview(ovRes.value)
      overview.value = a
      trendData.value = a?.trend_30d ?? []
    }
    if (topRes.status === 'fulfilled' && topRes.value) {
      topics.value = toSentimentTopics(topRes.value)
    }
    // 同步到 AI Copilot 上下文，让左侧数据被右侧提问感知
    if (overview.value) {
      ai.setContext({
        positive_pct: overview.value.positive_pct,
        negative_pct: overview.value.negative_pct,
        avg_score_7d: overview.value.avg_score_7d,
        topic_count: topics.value.length,
        alert: overview.value.alert,
      })
    }
  } catch (e) {
    console.warn('[SentimentOverview] load error:', e)
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  updateTime()
  timer = setInterval(updateTime, 60000)
  await refreshAll()
  await ai.init()
})
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.so { display: flex; flex-direction: column; gap: var(--v2-space-3); height: 100%; }
.so__main-scroll { display: flex; flex-direction: column; gap: var(--v2-space-4); padding: var(--v2-space-3); overflow-y: auto; min-height: 0; }
.so__main-scroll > * { flex-shrink: 0; }

/* ── Header ── */
.so__hd { display: flex; justify-content: space-between; align-items: center; }
.so__hd-left { display: flex; align-items: baseline; gap: 12px; }
.so__hd-right { display: flex; align-items: center; gap: 8px; }
.so__title {
  font-size: var(--v2-text-xl); font-weight: var(--v2-font-semibold);
  color: var(--v2-text-1); margin: 0; letter-spacing: -0.02em;
}
.so__time { font-family: var(--v2-font-mono); font-size: var(--v2-text-xs); color: var(--v2-text-4); }
.so__link-btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 6px 14px; border: var(--v2-border-width) solid var(--v2-border-1);
  border-radius: var(--v2-radius-btn); background: var(--v2-bg-card);
  color: var(--v2-text-2); font-size: var(--v2-text-sm); cursor: pointer;
  text-decoration: none; transition: var(--v2-trans-fast);
}
.so__link-btn:hover { background: var(--v2-bg-hover); color: var(--v2-text-1); }
.so__refresh {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 14px; border: var(--v2-border-width) solid var(--v2-border-1);
  border-radius: var(--v2-radius-btn); background: var(--v2-bg-card);
  color: var(--v2-text-2); font-size: var(--v2-text-sm); cursor: pointer;
  transition: var(--v2-trans-fast);
}
.so__refresh:hover { background: var(--v2-bg-hover); color: var(--v2-text-1); }
.so__refresh:disabled { opacity: 0.5; cursor: not-allowed; }
.is-spin { animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ── KPI Strip ── */
.so__kpi {
  display: grid; grid-template-columns: repeat(5, 1fr); gap: 1px;
  background: var(--v2-border-2); border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-card); overflow: hidden;
}
.kpi { padding: 12px 14px; background: var(--v2-bg-card); display: flex; flex-direction: column; gap: 2px; }
.kpi__val {
  font-size: 22px; font-weight: var(--v2-font-semibold); color: var(--v2-text-1);
  font-variant-numeric: tabular-nums; letter-spacing: -0.02em; line-height: 1.2;
  display: flex; align-items: baseline;
}
.kpi__suffix { font-size: 11px; color: var(--v2-text-3); margin-left: 2px; }
.kpi__label { font-family: var(--v2-font-mono); font-size: 10px; letter-spacing: 0.03em; color: var(--v2-text-3); }
.kpi__sub { font-size: 11px; color: var(--v2-text-4); }
.kpi__sub.is-up { color: #16a34a; }
.kpi__sub.is-warn { color: #dc2626; }
.kpi--pos .kpi__val { color: #16a34a; }
.kpi--neg .kpi__val { color: #dc2626; }
:root[data-theme='dark'] .kpi--pos .kpi__val { color: #4ade80; }
:root[data-theme='dark'] .kpi--neg .kpi__val { color: #f87171; }
:root[data-theme='dark'] .kpi__sub.is-up { color: #4ade80; }
:root[data-theme='dark'] .kpi__sub.is-warn { color: #f87171; }
.kpi--pos { background: rgba(16,185,129,0.03); }
.kpi--neg { background: rgba(244,63,94,0.03); }
:root[data-theme='dark'] .kpi--pos { background: rgba(52,211,153,0.05); }
:root[data-theme='dark'] .kpi--neg { background: rgba(251,113,133,0.05); }

/* ── Charts ── */
.so__main { display: grid; grid-template-columns: 1fr 2fr; gap: 16px; min-height: 280px; }
.so__card {
  display: flex; flex-direction: column;
  border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-card); background: var(--v2-bg-card);
  padding: 14px 16px; min-height: 0;
}
.so__card--wide { min-height: 0; }
.so__card--full { min-height: 0; }
.so__card-hd { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-shrink: 0; }
.so__sec-title { font-family: var(--v2-font-mono); font-size: 11px; letter-spacing: 0.03em; color: var(--v2-text-3); text-transform: uppercase; }
.so__sec-sub { font-family: var(--v2-font-mono); font-size: 10px; color: var(--v2-text-4); }
.so__chart-legend { display: flex; align-items: center; gap: 10px; font-size: 10px; color: var(--v2-text-4); }
.legend__dot { display: inline-block; width: 16px; height: 0; margin-right: 3px; vertical-align: middle; }
.legend__dot--solid { border-top: 2px solid #0d9488; }
:root[data-theme='dark'] .legend__dot--solid { border-top-color: #2dd4bf; }
.so__card-body { flex: 1; min-height: 0; }
.so__empty { display: flex; align-items: center; justify-content: center; height: 100%; color: var(--v2-text-4); font-size: var(--v2-text-sm); }

/* ── Topics ── */
.so__topics { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; }
.topic {
  padding: 12px 14px; background: var(--v2-bg-sunken);
  border-radius: var(--v2-radius-md); border: var(--v2-border-width) solid var(--v2-border-2);
  border-left: 3px solid var(--v2-border-2);
}
.topic--pos { border-left-color: #16a34a; }
.topic--neg { border-left-color: #dc2626; }
.topic--neu { border-left-color: var(--v2-border-3); }
:root[data-theme='dark'] .topic--pos { border-left-color: #4ade80; }
:root[data-theme='dark'] .topic--neg { border-left-color: #f87171; }
.topic__hd { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.topic__id { font-family: var(--v2-font-mono); font-size: 10px; color: var(--v2-text-4); min-width: 16px; }
.topic__name { font-size: var(--v2-text-sm); font-weight: var(--v2-font-semibold); color: var(--v2-text-1); flex: 1; }
.topic__cat {
  font-family: var(--v2-font-mono); font-size: 10px; padding: 1px 6px;
  border-radius: var(--v2-radius-pill); border: var(--v2-border-width) solid var(--v2-border-2);
  color: var(--v2-text-3);
}
.topic__cat--pos { color: #16a34a; border-color: #16a34a40; background: #16a34a0d; }
.topic__cat--neg { color: #dc2626; border-color: #dc262640; background: #dc26260d; }
:root[data-theme='dark'] .topic__cat--pos { color: #4ade80; border-color: #4ade8040; background: #4ade800d; }
:root[data-theme='dark'] .topic__cat--neg { color: #f87171; border-color: #f8717140; background: #f871710d; }
.topic__kws { display: flex; flex-wrap: wrap; gap: 4px; }
.topic__kw {
  font-size: 11px; padding: 2px 8px; border-radius: var(--v2-radius-sm);
  background: var(--v2-bg-hover); color: var(--v2-text-2); transition: var(--v2-trans-fast);
}
.topic--pos .topic__kw { background: rgba(16,185,129,0.08); color: #059669; }
.topic--neg .topic__kw { background: rgba(244,63,94,0.08); color: #e11d48; }
:root[data-theme='dark'] .topic--pos .topic__kw { background: rgba(52,211,153,0.10); color: #6ee7b7; }
:root[data-theme='dark'] .topic--neg .topic__kw { background: rgba(251,113,133,0.10); color: #fda4af; }

/* ── AI Insight ── */
.so__insight {
  padding: 14px 16px; border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-card); background: var(--v2-bg-card);
  border-left: 2px solid #0d9488;
}
:root[data-theme='dark'] .so__insight { border-left-color: #2dd4bf; }
.so__insight-hd {
  display: flex; align-items: center; gap: 6px;
  font-family: var(--v2-font-mono); font-size: 10px; letter-spacing: 0.04em;
  color: var(--v2-text-3); text-transform: uppercase; margin-bottom: 6px;
}
.so__insight-text { font-size: 12px; line-height: 1.6; color: var(--v2-text-3); margin: 0; }

/* ── Responsive ── */
@media (max-width: 1200px) { .so__kpi { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 1024px) {
  .so__main { grid-template-columns: 1fr; }
  .so__kpi { grid-template-columns: repeat(2, 1fr); }
}

/* ── Toggle AI Panel Button ── */
.so__toggle-panel { display: flex; align-items: center; justify-content: center; width: 28px; height: 28px; border: 1px solid var(--v2-border-1); border-radius: var(--v2-radius-md); background: var(--v2-bg-card); color: var(--v2-text-3); cursor: pointer; transition: all var(--v2-trans-fast); }
.so__toggle-panel:hover { color: var(--v2-text-1); }
.so__toggle-panel--active { background: var(--v2-text-1); color: #fff; border-color: var(--v2-text-1); }

/* ── Right Detail Panel ── */
.so__detail { display: flex; flex-direction: column; gap: var(--v2-space-3); padding: 12px; overflow-y: auto; }
.so__detail h4 { font-size: 12px; font-weight: 600; color: var(--v2-text-3); text-transform: uppercase; letter-spacing: .5px; margin: 0 0 8px; padding-bottom: 6px; border-bottom: 1px solid var(--v2-border-2); }
.so__dl { display: flex; justify-content: space-between; padding: 3px 0; font-size: 13px; }
.so__dl > span:first-child { color: var(--v2-text-3); }
.so__dl > span:last-child { color: var(--v2-text-1); font-variant-numeric: tabular-nums; }
.so__detail-alert { display: inline-flex; align-items: center; gap: 6px; padding: 6px 10px; margin-top: 4px; font-size: 12px; color: var(--v2-danger); background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.16); border-radius: 8px; }
.so__detail-ask { display: flex; align-items: center; justify-content: center; gap: 6px; padding: 8px; border: 1px solid var(--v2-border-1); border-radius: 8px; background: var(--v2-bg-card); font-size: 12px; font-weight: 500; color: var(--v2-text-1); cursor: pointer; transition: all 0.15s; font-family: inherit; margin-top: 4px; }
.so__detail-ask:hover { background: var(--v2-bg-hover); border-color: var(--v2-border-hover, var(--v2-border-2)); }
.so__empty-detail { display: flex; flex-direction: column; align-items: center; justify-content: center; flex: 1; gap: 8px; padding: 24px; color: var(--v2-text-4); }
.so__empty-detail p { font-size: 12px; margin: 0; }
</style>
