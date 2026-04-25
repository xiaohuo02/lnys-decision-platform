<template>
  <div class="sa page-enter-active">
    <PageHeaderV2 title="舆情分析" desc="Cascade 推理 · Chain-of-Thought · HITL 审核">
      <template #actions>
        <router-link to="/sentiment" class="sa__back-btn">
          <ArrowLeft :size="13" /> 返回总览
        </router-link>
        <button class="sa__toggle-panel" :class="{ 'sa__toggle-panel--active': showRight }" @click="showRight = !showRight" title="AI 面板">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="3"/><line x1="15" y1="3" x2="15" y2="21"/></svg>
        </button>
      </template>
    </PageHeaderV2>

    <SplitInspector :hide-right="!showRight">
      <template #main>
        <div class="sa__main-scroll">
    <!-- ── Composer: Analysis Input ── -->
    <div class="sa__composer">
      <div class="sa__composer-inner">
        <textarea
          ref="textareaRef"
          v-model="inputText"
          class="sa__textarea"
          placeholder="输入评论文本进行情感分析…"
          rows="1"
          @input="autoResize"
          @keydown.ctrl.enter="runAnalyze"
        ></textarea>
        <div class="sa__composer-bar">
          <span class="sa__hint">Ctrl+Enter 分析</span>
          <button class="sa__send-btn" :disabled="!inputText.trim() || analyzing" @click="runAnalyze">
            <Loader2 v-if="analyzing" :size="14" class="is-spin" />
            <Send v-else :size="14" />
            分析
          </button>
        </div>
      </div>
    </div>

    <!-- ── Analysis Result (always visible once triggered) ── -->
    <div v-if="showResult" class="sa__result">
      <!-- Left: Verdict -->
      <div class="sa__verdict" :class="result ? 'sa__verdict--' + labelClass(result.label) : ''">
        <template v-if="analyzing && !result">
          <div class="sa__verdict-label sa__verdict-label--loading">分析中…</div>
          <div class="sa__verdict-conf sa__verdict-conf--skel">
            <div class="sa__skel sa__skel--lg"></div>
          </div>
          <div class="sa__skel sa__skel--sm"></div>
          <div class="sa__skel sa__skel--sm" style="width:60%"></div>
          <div class="sa__aspects">
            <div class="sa__aspects-title">维度分析</div>
            <div v-for="n in 4" :key="n" class="sa__aspect-row">
              <span class="sa__skel sa__skel--xs"></span>
              <span class="sa__skel sa__skel--xs" style="width:40px"></span>
            </div>
          </div>
        </template>
        <template v-else-if="result">
          <div class="sa__verdict-label" :class="'sa__verdict-label--' + labelClass(result.label)">
            {{ result.label }}
          </div>
          <div class="sa__verdict-conf" :class="'sa__verdict-conf--' + labelClass(result.label)">
            <Odometer :value="(result.confidence * 100)" :decimals="1" />
            <span class="sa__conf-pct">%</span>
          </div>
          <div class="sa__verdict-model">{{ result.model_used }}</div>
          <div v-if="result.cascade_tier" class="sa__verdict-tier">
            Tier {{ result.cascade_tier }}
          </div>
          <div v-if="result.needs_review" class="sa__verdict-review">
            <AlertTriangle :size="12" /> 待人工审核
          </div>

          <!-- Entity Sentiments (ASTE) -->
          <div v-if="result.entity_sentiments?.length" class="sa__entities">
            <div class="sa__entities-title">实体级情感</div>
            <div class="sa__entity-table">
              <div v-for="(es, i) in result.entity_sentiments" :key="i" class="sa__entity-row">
                <span class="sa__entity-name">{{ es.entity }}</span>
                <span class="sa__entity-aspect">{{ es.aspect }}</span>
                <span class="sa__entity-opinion">{{ es.opinion }}</span>
                <span class="sa__entity-sent" :class="'sa__entity-sent--' + labelClass(es.sentiment)">{{ es.sentiment }}</span>
              </div>
            </div>
          </div>

          <!-- Legacy Aspects fallback -->
          <div v-else-if="result.aspects && Object.keys(result.aspects).length" class="sa__aspects">
            <div class="sa__aspects-title">维度分析</div>
            <div v-for="(val, key) in result.aspects" :key="key" class="sa__aspect-row">
              <span class="sa__aspect-key">{{ key }}</span>
              <span class="sa__aspect-val" :class="'sa__aspect-val--' + labelClass(val)">{{ val }}</span>
            </div>
          </div>

          <!-- Intent Tags -->
          <div v-if="result.intent_tags?.length" class="sa__intents">
            <div class="sa__intents-title">业务意图</div>
            <div class="sa__intents-list">
              <span v-for="tag in result.intent_tags" :key="tag" class="sa__intent-tag">{{ formatIntent(tag) }}</span>
            </div>
          </div>

          <!-- Key Phrases -->
          <div v-if="result.key_phrases?.length" class="sa__phrases">
            <div class="sa__phrases-title">关键短语</div>
            <div class="sa__phrases-list">
              <span v-for="p in result.key_phrases" :key="p" class="sa__phrase">{{ p }}</span>
            </div>
          </div>
        </template>
      </div>

      <!-- Right: Reasoning Chain (progressive reveal) -->
      <div class="sa__reasoning">
        <div class="sa__reasoning-hd">
          <BrainCircuit :size="14" />
          <span>推理链</span>
          <span v-if="analyzing" class="sa__reasoning-status">
            <Loader2 :size="12" class="is-spin" /> 推理中…
          </span>
        </div>

        <!-- Loading skeleton -->
        <div v-if="analyzing && !visibleTrace.length && !visibleCoT.length" class="sa__trace">
          <div v-for="n in 2" :key="n" class="sa__trace-step sa__trace-step--skel">
            <div class="sa__trace-dot sa__trace-dot--pulse"></div>
            <div class="sa__trace-content">
              <div class="sa__skel sa__skel--md"></div>
              <div class="sa__skel sa__skel--lg" style="margin-top:4px"></div>
            </div>
          </div>
        </div>

        <!-- Cascade Trace (progressive) -->
        <div v-if="visibleTrace.length" class="sa__trace">
          <transition-group name="step-reveal">
            <div v-for="(t, i) in visibleTrace" :key="'t'+i" class="sa__trace-step">
              <div class="sa__trace-dot" :class="traceClass(t)"></div>
              <div class="sa__trace-content">
                <div class="sa__trace-head">
                  <span class="sa__trace-tier">Tier {{ t.tier }}</span>
                  <span class="sa__trace-model">{{ t.model }}</span>
                  <span class="sa__trace-ms" v-if="t.ms != null">{{ t.ms }}ms</span>
                </div>
                <div class="sa__trace-decision">{{ formatDecision(t) }}</div>
                <div v-if="t.label" class="sa__trace-label" :class="'sa__trace-label--' + labelClass(t.label)">
                  → {{ t.label }} <span v-if="t.confidence">({{ (t.confidence * 100).toFixed(1) }}%)</span>
                </div>
              </div>
            </div>
          </transition-group>
        </div>

        <!-- CoT Reasoning Steps (progressive) -->
        <div v-if="visibleCoT.length" class="sa__cot" :class="result ? 'sa__cot--' + labelClass(result.label) : ''">
          <div class="sa__cot-title">思维链</div>
          <transition-group name="step-reveal">
            <div v-for="(r, i) in visibleCoT" :key="'c'+i" class="sa__cot-step">
              <div class="sa__cot-idx">{{ i + 1 }}</div>
              <div class="sa__cot-body">
                <div class="sa__cot-name">{{ r.step }}</div>
                <div class="sa__cot-detail">{{ r.detail }}</div>
              </div>
            </div>
          </transition-group>
        </div>

        <!-- Fallback -->
        <div v-if="result && !result.reasoning?.length && !result.cascade_trace?.length && !analyzing" class="sa__cot">
          <div class="sa__cot-step">
            <div class="sa__cot-idx">1</div>
            <div class="sa__cot-body">
              <div class="sa__cot-name">模型推断</div>
              <div class="sa__cot-detail">使用 {{ result.model_used }} 模型，判定为「{{ result.label }}」，置信度 {{ (result.confidence * 100).toFixed(1) }}%。</div>
            </div>
          </div>
        </div>

        <!-- Agent Signals Dispatch -->
        <div v-if="result?.agent_signals?.length" class="sa__signals">
          <div class="sa__signals-title">
            <Zap :size="12" />
            <span>情报分发</span>
          </div>
          <div v-for="(sig, i) in result.agent_signals" :key="i" class="sa__signal-row">
            <div class="sa__signal-head">
              <span class="sa__signal-agent">{{ formatAgent(sig.target_agent) }}</span>
              <span class="sa__signal-type">{{ signalTypeLabel(sig.signal_type) }}</span>
              <span class="sa__signal-sev" :class="'sa__signal-sev--' + sig.severity">{{ severityLabel(sig.severity) }}</span>
            </div>
            <div class="sa__signal-suggestion">{{ sig.suggestion }}</div>
            <div v-if="sig.entity" class="sa__signal-entity">关联实体：{{ sig.entity }}</div>
          </div>
        </div>

        <!-- Similar Reviews from KB -->
        <div v-if="similarReviews.length" class="sa__similar">
          <div class="sa__similar-title">
            <Database :size="12" />
            <span>知识库相似评论</span>
            <span class="sa__similar-badge" v-if="result?.kb_id">已入库</span>
          </div>
          <div v-for="(sr, i) in similarReviews" :key="i" class="sa__similar-row">
            <span class="sa__similar-score">{{ (sr.similarity * 100).toFixed(0) }}%</span>
            <span class="sa__similar-text">{{ sr.text }}</span>
            <span class="sa__similar-label" :class="'sa__similar-label--' + labelClass(sr.label)">{{ sr.label }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- ── HITL Review Queue ── -->
    <div class="sa__hitl">
      <div class="sa__hitl-hd">
        <div class="sa__hitl-left">
          <ClipboardCheck :size="14" />
          <span class="sa__sec-title">人工审核队列</span>
          <span class="sa__hitl-count" v-if="reviewQueue.length">{{ reviewQueue.length }}</span>
        </div>
        <button class="sa__refresh-sm" @click="loadReviews">
          <RefreshCw :size="12" />
        </button>
      </div>

      <div v-if="reviewQueue.length" class="sa__hitl-list">
        <div v-for="item in reviewQueue" :key="item.id" class="sa__review-row">
          <div class="sa__review-id">{{ item.id }}</div>
          <div class="sa__review-text">{{ item.text }}</div>
          <div class="sa__review-auto">
            <span class="sa__review-label" :class="'sa__review-label--' + labelClass(item.auto_label)">{{ item.auto_label }}</span>
            <span class="sa__review-conf">{{ (item.confidence * 100).toFixed(0) }}%</span>
          </div>
          <div class="sa__review-actions">
            <button class="sa__rv-btn sa__rv-btn--pos" @click="resolveReview(item.id, '正面')">正面</button>
            <button class="sa__rv-btn sa__rv-btn--neg" @click="resolveReview(item.id, '负面')">负面</button>
            <button class="sa__rv-btn sa__rv-btn--neu" @click="resolveReview(item.id, '中性')">中性</button>
          </div>
        </div>
      </div>
      <div v-else class="sa__hitl-empty">
        <CheckCircle2 :size="16" />
        <span>队列已清空，暂无待审核项</span>
      </div>
    </div>
        </div><!-- .sa__main-scroll -->
      </template>

      <template #right>
        <PageAICopilotPanel
          ref="aiPanel"
          :ai="ai"
          welcome-title="AI 舆情分析助手"
          welcome-desc="解读判定依据、给出回复话术、关联客户画像"
          collection="sentiment"
          command-bar-placeholder="询问当前分析或舆情话题...  @ 选择智能体"
          :quick-questions="quickQuestions"
          :mention-catalog="mentionCatalog"
        >
          <template #detail>
            <div v-if="result" class="sa__detail">
              <h4>分析结果摘要</h4>
              <div class="sa__dl"><span>判定</span><span>{{ result.label }}</span></div>
              <div class="sa__dl"><span>置信度</span><span>{{ (result.confidence * 100).toFixed(1) }}%</span></div>
              <div class="sa__dl"><span>模型</span><span>{{ result.model_used }}</span></div>
              <div v-if="result.cascade_tier" class="sa__dl"><span>Tier</span><span>{{ result.cascade_tier }}</span></div>
              <div v-if="result.intent_tags?.length" class="sa__dl"><span>意图标签</span><span>{{ result.intent_tags.length }} 项</span></div>
              <div v-if="result.entity_sentiments?.length" class="sa__dl"><span>实体级</span><span>{{ result.entity_sentiments.length }} 项</span></div>
              <div v-if="result.needs_review" class="sa__detail-alert">
                <AlertTriangle :size="12" /> 待人工审核
              </div>
              <button class="sa__detail-ask" @click="askReplyScript">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
                建议回复话术
              </button>
              <button class="sa__detail-ask" @click="askReviewCustomer">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M16 21v-2a4 4 0 00-4-4H6a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/></svg>
                关联客户画像（跨客群）
              </button>
            </div>
            <div v-else class="sa__empty-detail">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
              <p>运行分析后查看结果详情</p>
            </div>
          </template>
        </PageAICopilotPanel>
      </template>
    </SplitInspector>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, watch } from 'vue'
import { ArrowLeft, Send, Loader2, RefreshCw, AlertTriangle, BrainCircuit, ClipboardCheck, CheckCircle2, Zap, Database } from 'lucide-vue-next'
import { sentimentApi } from '@/api/business'
import {
  PageHeaderV2, SplitInspector, PageAICopilotPanel, Odometer,
} from '@/components/v2'
import { usePageCopilot } from '@/composables/usePageCopilot'

// ── AI Copilot ──
const ai = usePageCopilot('sentiment', ['sentiment', 'kb_rag'])
const aiPanel = ref(null)
const showRight = ref(true)

const quickQuestions = [
  '解读当前分析的判定依据和置信度含义',
  '针对这条评论产出一段合理的回复话术',
  '相似舆情在知识库里有哪些历史案例？',
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

function askReplyScript() {
  if (!result.value) return
  showRight.value = true
  aiPanel.value?.askAndSwitch(
    `针对这条「${result.value.label}」评论（模型 ${result.value.model_used} 置信度 ${(result.value.confidence * 100).toFixed(1)}%），生成一条合理的回复话术`
  )
}

function askReviewCustomer() {
  if (!result.value) return
  showRight.value = true
  ai.askCrossAgent('customer_intel', '这条舆情可能关联哪些客户画像？他们最近的行为模式有什么特征？', {
    sentiment_label: result.value.label,
    confidence: result.value.confidence,
    entity_count: result.value.entity_sentiments?.length ?? 0,
  })
  aiPanel.value?.switchTab('ai')
}

const textareaRef = ref(null)
const inputText = ref('')
const analyzing = ref(false)
const result = ref(null)
const showResult = ref(false)
const reviewQueue = ref([])
const similarReviews = ref([])

const visibleTrace = ref([])
const visibleCoT = ref([])
let revealTimers = []

// ── Auto-resize textarea ──
function autoResize() {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 200) + 'px'
}

// ── Progressive reveal ──
function clearReveal() {
  revealTimers.forEach(t => clearTimeout(t))
  revealTimers = []
  visibleTrace.value = []
  visibleCoT.value = []
}

function revealSteps(data) {
  clearReveal()
  const trace = data?.cascade_trace || []
  const cot = data?.reasoning || []
  let delay = 0
  const BASE = 300

  trace.forEach((t, i) => {
    const tid = setTimeout(() => { visibleTrace.value.push(t) }, delay)
    revealTimers.push(tid)
    delay += BASE
  })

  delay += 200

  cot.forEach((r, i) => {
    const tid = setTimeout(() => { visibleCoT.value.push(r) }, delay)
    revealTimers.push(tid)
    delay += BASE + 100
  })
}

// ── Analyze ──
async function runAnalyze() {
  if (!inputText.value.trim() || analyzing.value) return
  analyzing.value = true
  showResult.value = true
  result.value = null
  clearReveal()
  try {
    const res = await sentimentApi.analyze({ text: inputText.value.trim() })
    result.value = res
    revealSteps(res)
    await loadReviews()
    loadSimilar(inputText.value.trim())
    // 同步分析结果到 AI Copilot 上下文
    if (res) {
      ai.setContext({
        last_text: inputText.value.trim().slice(0, 120),
        label: res.label,
        confidence: res.confidence,
        model_used: res.model_used,
        cascade_tier: res.cascade_tier,
        intent_count: res.intent_tags?.length ?? 0,
        entity_count: res.entity_sentiments?.length ?? 0,
        needs_review: !!res.needs_review,
      })
    }
  } catch (e) {
    console.error('[SentimentAnalyze] error:', e)
  } finally {
    analyzing.value = false
  }
}

// ── HITL ──
async function loadReviews() {
  try {
    const res = await sentimentApi.getReviewQueue()
    reviewQueue.value = res?.items ?? []
  } catch (e) {
    console.warn('[SentimentAnalyze] loadReviews error:', e)
  }
}

async function resolveReview(reviewId, humanLabel) {
  try {
    await sentimentApi.resolveReview({ review_id: reviewId, human_label: humanLabel })
    reviewQueue.value = reviewQueue.value.filter(i => i.id !== reviewId)
  } catch (e) {
    console.error('[SentimentAnalyze] resolveReview error:', e)
  }
}

// ── KB: similar reviews ──
async function loadSimilar(query) {
  similarReviews.value = []
  try {
    const res = await sentimentApi.searchSimilar({ query, top_k: 3 })
    similarReviews.value = (res?.items ?? []).filter(r => r.similarity > 0.3)
  } catch (e) {
    // KB may not be available yet
  }
}

// ── Helpers ──
const labelClass = (l) => ({ '正面': 'pos', '负面': 'neg', '中性': 'neu', '无关': 'neu' }[l] || 'neu')

const _INTENT_LABELS = {
  quality_complaint: '质量投诉', defect_report: '缺陷反馈',
  repurchase_likely: '复购意愿强', repurchase_unlikely: '复购意愿弱',
  cross_product_compare: '多产品比较', service_praise: '服务好评',
  service_complaint: '服务投诉', price_sensitive: '价格敏感',
  logistics_praise: '物流好评', logistics_complaint: '物流投诉',
}
const formatIntent = (tag) => _INTENT_LABELS[tag] || tag

const _AGENT_LABELS = {
  inventory: '库存优化', customer: '客户分析',
  association: '关联分析', operation: '经营分析',
}
const formatAgent = (agent) => _AGENT_LABELS[agent] || agent

const _SIGNAL_TYPE_LABELS = {
  risk_alert: '风险警报', opportunity: '机会提示', adjustment: '调整建议',
  insight: '洞察', action_required: '需要操作', info: '信息通知',
}
const signalTypeLabel = (t) => _SIGNAL_TYPE_LABELS[t] || t

const _SEVERITY_LABELS = { critical: '紧急', high: '高', medium: '中', low: '低', info: '信息' }
const severityLabel = (s) => _SEVERITY_LABELS[s] || s

function traceClass(t) {
  if (t.decision === 'direct_return' || t.decision === 'agree_with_bert') return 'sa__trace-dot--ok'
  if (t.decision === 'failed' || t.decision === 'no_majority' || t.decision === 'mark_uncertain') return 'sa__trace-dot--warn'
  return ''
}

function formatDecision(t) {
  const map = {
    'direct_return': 'BERT 高置信直出',
    'defer_to_llm': 'BERT 置信度不足，交由 LLM',
    'not_available': 'BERT 不可用',
    'agree_with_bert': 'LLM 与 BERT 判定一致',
    'override_bert': 'LLM 覆盖 BERT 判定',
    'low_conf_defer': 'LLM 置信度不足，升级投票',
    'failed': '调用失败',
    'majority_vote': '三路投票多数一致',
    'no_majority': '投票无多数一致',
    'mark_uncertain': '标记为不确定，进入人工审核',
  }
  return map[t.decision] || t.decision
}

onMounted(async () => {
  loadReviews()
  nextTick(() => textareaRef.value?.focus())
  await ai.init()
})
</script>

<style scoped>
.sa { display: flex; flex-direction: column; gap: var(--v2-space-3); height: 100%; }
.sa__main-scroll { display: flex; flex-direction: column; gap: var(--v2-space-4); padding: var(--v2-space-3); overflow-y: auto; min-height: 0; }
.sa__main-scroll > * { flex-shrink: 0; }

/* ── Header ── */
.sa__hd { display: flex; justify-content: space-between; align-items: center; }
.sa__hd-left { display: flex; align-items: baseline; gap: 12px; }
.sa__title { font-size: var(--v2-text-xl); font-weight: var(--v2-font-semibold); color: var(--v2-text-1); margin: 0; letter-spacing: -0.02em; }
.sa__desc { font-family: var(--v2-font-mono); font-size: var(--v2-text-xs); color: var(--v2-text-4); }
.sa__back-btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 6px 14px; border: var(--v2-border-width) solid var(--v2-border-1);
  border-radius: var(--v2-radius-btn); background: var(--v2-bg-card);
  color: var(--v2-text-2); font-size: var(--v2-text-sm); cursor: pointer;
  text-decoration: none; transition: var(--v2-trans-fast);
}
.sa__back-btn:hover { background: var(--v2-bg-hover); color: var(--v2-text-1); }

/* ── Composer ── */
.sa__composer {
  border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-card); background: var(--v2-bg-card);
  padding: 14px 16px;
}
.sa__composer-inner { display: flex; flex-direction: column; gap: 8px; }
.sa__textarea {
  width: 100%; border: none; outline: none; resize: none;
  font-size: var(--v2-text-md); line-height: 1.6; color: var(--v2-text-1);
  background: transparent; font-family: inherit;
  min-height: 24px; max-height: 200px;
}
.sa__textarea::placeholder { color: var(--v2-text-4); }
.sa__composer-bar { display: flex; justify-content: space-between; align-items: center; }
.sa__hint { font-family: var(--v2-font-mono); font-size: 10px; color: var(--v2-text-4); }
.sa__send-btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 6px 16px; border: none; border-radius: var(--v2-radius-btn);
  background: var(--v2-text-1); color: var(--v2-bg-1);
  font-size: var(--v2-text-sm); font-weight: var(--v2-font-medium);
  cursor: pointer; transition: var(--v2-trans-fast);
}
.sa__send-btn:hover { opacity: 0.85; }
.sa__send-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.is-spin { animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Result: Verdict + Reasoning ── */
.sa__result { display: grid; grid-template-columns: 280px 1fr; gap: 16px; }

/* Verdict card */
.sa__verdict {
  display: flex; flex-direction: column; gap: 12px;
  border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-card); background: var(--v2-bg-card);
  padding: 20px 18px;
}
.sa__verdict-label {
  font-size: 28px; font-weight: var(--v2-font-bold); letter-spacing: -0.02em;
  color: var(--v2-text-1);
}
.sa__verdict-label--pos { color: #16a34a; }
.sa__verdict-label--neg { color: #dc2626; }
.sa__verdict-label--neu { color: var(--v2-text-3); }
.sa__verdict-label--loading { color: var(--v2-text-4); font-size: 18px; }
:root[data-theme='dark'] .sa__verdict-label--pos { color: #4ade80; }
:root[data-theme='dark'] .sa__verdict-label--neg { color: #f87171; }
.sa__verdict-conf {
  display: flex; align-items: baseline; gap: 1px;
  font-size: 36px; font-weight: var(--v2-font-bold);
  font-variant-numeric: tabular-nums; letter-spacing: -0.03em;
  color: var(--v2-text-1); line-height: 1;
}
.sa__verdict-conf--pos { color: #16a34a; }
.sa__verdict-conf--neg { color: #dc2626; }
.sa__verdict-conf--neu { color: var(--v2-text-3); }
.sa__verdict-conf--skel { height: 40px; }
:root[data-theme='dark'] .sa__verdict-conf--pos { color: #4ade80; }
:root[data-theme='dark'] .sa__verdict-conf--neg { color: #f87171; }
.sa__conf-pct { font-size: 16px; color: var(--v2-text-3); }
.sa__verdict-model { font-family: var(--v2-font-mono); font-size: 11px; color: var(--v2-text-4); }
.sa__verdict-tier { font-family: var(--v2-font-mono); font-size: 10px; color: var(--v2-text-4); padding: 2px 8px; background: var(--v2-bg-hover); border-radius: var(--v2-radius-sm); display: inline-block; }
.sa__verdict-review {
  display: flex; align-items: center; gap: 4px;
  font-size: 11px; color: var(--v2-warning-text);
  padding: 4px 8px; background: var(--v2-warning-bg); border-radius: var(--v2-radius-sm);
}
.sa__verdict--pos { border-top: 2px solid #16a34a; }
.sa__verdict--neg { border-top: 2px solid #dc2626; }
.sa__verdict--neu { border-top: 2px solid #a1a1aa; }
:root[data-theme='dark'] .sa__verdict--pos { border-top-color: #4ade80; }
:root[data-theme='dark'] .sa__verdict--neg { border-top-color: #f87171; }

/* Aspects */
.sa__aspects { border-top: var(--v2-border-width) solid var(--v2-border-2); padding-top: 12px; }
.sa__aspects-title { font-family: var(--v2-font-mono); font-size: 10px; color: var(--v2-text-4); text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 8px; }
.sa__aspect-row { display: flex; justify-content: space-between; align-items: center; padding: 3px 0; }
.sa__aspect-key { font-size: 12px; color: var(--v2-text-2); }
.sa__aspect-val { font-family: var(--v2-font-mono); font-size: 11px; color: var(--v2-text-3); }
.sa__aspect-val--pos { color: #16a34a; font-weight: var(--v2-font-medium); }
.sa__aspect-val--neg { color: #dc2626; font-weight: var(--v2-font-medium); }
:root[data-theme='dark'] .sa__aspect-val--pos { color: #4ade80; }
:root[data-theme='dark'] .sa__aspect-val--neg { color: #f87171; }

/* Key Phrases */
.sa__phrases { border-top: var(--v2-border-width) solid var(--v2-border-2); padding-top: 12px; }
.sa__phrases-title { font-family: var(--v2-font-mono); font-size: 10px; color: var(--v2-text-4); text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 8px; }
.sa__phrases-list { display: flex; flex-wrap: wrap; gap: 4px; }
.sa__phrase { font-size: 11px; padding: 2px 8px; border-radius: var(--v2-radius-sm); background: var(--v2-bg-hover); color: var(--v2-text-2); }
.sa__verdict--pos .sa__phrase { background: rgba(16,185,129,0.08); color: #059669; border: 1px solid rgba(16,185,129,0.12); }
.sa__verdict--neg .sa__phrase { background: rgba(244,63,94,0.08); color: #e11d48; border: 1px solid rgba(244,63,94,0.12); }
:root[data-theme='dark'] .sa__verdict--pos .sa__phrase { background: rgba(52,211,153,0.10); color: #6ee7b7; border-color: rgba(52,211,153,0.15); }
:root[data-theme='dark'] .sa__verdict--neg .sa__phrase { background: rgba(251,113,133,0.10); color: #fda4af; border-color: rgba(251,113,133,0.15); }

/* ── Reasoning Panel ── */
.sa__reasoning {
  display: flex; flex-direction: column; gap: 12px;
  border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-card); background: var(--v2-bg-card);
  padding: 18px 20px; overflow-y: auto; max-height: 600px;
}
.sa__reasoning-hd {
  display: flex; align-items: center; gap: 6px;
  font-family: var(--v2-font-mono); font-size: 11px; letter-spacing: 0.03em;
  color: var(--v2-text-3); text-transform: uppercase;
}

/* Cascade Trace */
.sa__trace { display: flex; flex-direction: column; gap: 0; }
.sa__trace-step {
  display: flex; gap: 12px; padding: 10px 6px;
  border-bottom: var(--v2-border-width) solid var(--v2-border-1);
  border-radius: var(--v2-radius-sm); margin: 0 -6px; transition: var(--v2-trans-fast);
}
.sa__trace-step:last-child { border-bottom: none; }
.sa__trace-step:hover { background: var(--v2-bg-hover); }
.sa__trace-dot {
  width: 8px; height: 8px; border-radius: 50%; margin-top: 5px; flex-shrink: 0;
  background: var(--v2-text-4);
}
.sa__trace-dot--ok { background: #16a34a; }
.sa__trace-dot--warn { background: #dc2626; }
.sa__trace-dot--pulse { animation: dot-pulse 1.2s ease-in-out infinite; background: var(--v2-text-4); }
:root[data-theme='dark'] .sa__trace-dot--ok { background: #4ade80; }
:root[data-theme='dark'] .sa__trace-dot--warn { background: #f87171; }
@keyframes dot-pulse { 0%,100% { opacity: 0.3; } 50% { opacity: 1; } }
.sa__trace-step--skel { opacity: 0.5; }
.sa__trace-label--pos { color: #16a34a; }
.sa__trace-label--neg { color: #dc2626; }
:root[data-theme='dark'] .sa__trace-label--pos { color: #4ade80; }
:root[data-theme='dark'] .sa__trace-label--neg { color: #f87171; }
.sa__trace-content { flex: 1; }
.sa__trace-head { display: flex; align-items: center; gap: 8px; margin-bottom: 2px; }
.sa__trace-tier { font-family: var(--v2-font-mono); font-size: 10px; color: var(--v2-text-4); }
.sa__trace-model { font-family: var(--v2-font-mono); font-size: 11px; color: var(--v2-text-2); font-weight: var(--v2-font-medium); }
.sa__trace-ms { font-family: var(--v2-font-mono); font-size: 10px; color: var(--v2-text-4); margin-left: auto; }
.sa__trace-decision { font-size: 12px; color: var(--v2-text-3); }
.sa__trace-label { font-family: var(--v2-font-mono); font-size: 11px; color: var(--v2-text-2); margin-top: 2px; }

/* CoT Steps */
.sa__cot { border-top: var(--v2-border-width) solid var(--v2-border-2); padding-top: 12px; }
.sa__cot-title { font-family: var(--v2-font-mono); font-size: 10px; color: var(--v2-text-4); text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 10px; }
.sa__cot-step { display: flex; gap: 12px; margin-bottom: 12px; }
.sa__cot-step:last-child { margin-bottom: 0; }
.sa__cot-idx {
  width: 22px; height: 22px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-family: var(--v2-font-mono); font-size: 10px; font-weight: var(--v2-font-semibold);
  background: var(--v2-bg-hover); color: var(--v2-text-2); transition: var(--v2-trans-fast);
}
.sa__cot--pos .sa__cot-idx { background: rgba(16,185,129,0.12); color: #059669; }
.sa__cot--neg .sa__cot-idx { background: rgba(244,63,94,0.12); color: #e11d48; }
:root[data-theme='dark'] .sa__cot--pos .sa__cot-idx { background: rgba(52,211,153,0.10); color: #34d399; }
:root[data-theme='dark'] .sa__cot--neg .sa__cot-idx { background: rgba(251,113,133,0.10); color: #fb7185; }
.sa__cot-body { flex: 1; }
.sa__cot-name { font-size: 12px; font-weight: var(--v2-font-semibold); color: var(--v2-text-1); margin-bottom: 3px; }
.sa__cot-detail { font-size: 12px; line-height: 1.7; color: var(--v2-text-2); }

/* ── HITL Queue ── */
.sa__hitl {
  border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-card); background: var(--v2-bg-card);
  padding: 14px 16px;
}
.sa__hitl-hd { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.sa__hitl-left { display: flex; align-items: center; gap: 8px; }
.sa__sec-title { font-family: var(--v2-font-mono); font-size: 11px; letter-spacing: 0.03em; color: var(--v2-text-3); text-transform: uppercase; }
.sa__hitl-count {
  font-family: var(--v2-font-mono); font-size: 10px; padding: 1px 6px;
  border-radius: var(--v2-radius-pill); background: var(--v2-text-1); color: var(--v2-bg-1);
}
.sa__refresh-sm {
  width: 28px; height: 28px; border: var(--v2-border-width) solid var(--v2-border-1);
  border-radius: var(--v2-radius-btn); background: transparent; color: var(--v2-text-3);
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: var(--v2-trans-fast);
}
.sa__refresh-sm:hover { background: var(--v2-bg-hover); color: var(--v2-text-1); }
.sa__hitl-list { display: flex; flex-direction: column; gap: 1px; }
.sa__review-row {
  display: grid; grid-template-columns: 64px 1fr 100px auto;
  align-items: center; gap: 12px; padding: 10px 8px;
  border-radius: var(--v2-radius-sm); transition: var(--v2-trans-fast);
}
.sa__review-row:hover { background: var(--v2-bg-hover); }
.sa__review-id { font-family: var(--v2-font-mono); font-size: 11px; color: var(--v2-text-4); }
.sa__review-text { font-size: 12px; color: var(--v2-text-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sa__review-auto { display: flex; align-items: center; gap: 6px; }
.sa__review-label { font-family: var(--v2-font-mono); font-size: 11px; }
.sa__review-label--pos { color: #16a34a; }
.sa__review-label--neg { color: #dc2626; }
.sa__review-label--neu { color: var(--v2-text-4); }
:root[data-theme='dark'] .sa__review-label--pos { color: #4ade80; }
:root[data-theme='dark'] .sa__review-label--neg { color: #f87171; }
.sa__review-conf { font-family: var(--v2-font-mono); font-size: 10px; color: var(--v2-text-4); }
.sa__review-actions { display: flex; gap: 4px; }
.sa__rv-btn {
  padding: 4px 10px; border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-sm); background: transparent;
  font-size: 11px; cursor: pointer; color: var(--v2-text-3);
  transition: var(--v2-trans-fast);
}
.sa__rv-btn:hover { background: var(--v2-bg-hover); color: var(--v2-text-1); }
.sa__rv-btn--pos:hover { background: #16a34a; color: #fff; border-color: #16a34a; }
.sa__rv-btn--neg:hover { background: #dc2626; color: #fff; border-color: #dc2626; }
.sa__rv-btn--neu:hover { background: var(--v2-border-3); color: var(--v2-bg-1); }
.sa__hitl-empty {
  display: flex; align-items: center; gap: 6px; justify-content: center;
  padding: 20px; color: var(--v2-text-4); font-size: var(--v2-text-sm);
}

/* ── Skeleton ── */
.sa__skel {
  background: var(--v2-bg-hover); border-radius: var(--v2-radius-sm);
  animation: skel-pulse 1.5s ease-in-out infinite;
}
.sa__skel--xs { display: inline-block; width: 60px; height: 12px; }
.sa__skel--sm { display: block; width: 80%; height: 14px; margin-bottom: 6px; }
.sa__skel--md { display: block; width: 50%; height: 14px; }
.sa__skel--lg { display: block; width: 100%; height: 16px; }
@keyframes skel-pulse { 0%,100% { opacity: 0.4; } 50% { opacity: 0.8; } }

/* ── Entity Sentiments (ASTE) ── */
.sa__entities { border-top: var(--v2-border-width) solid var(--v2-border-2); padding-top: 12px; }
.sa__entities-title { font-family: var(--v2-font-mono); font-size: 10px; color: var(--v2-text-4); text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 8px; }
.sa__entity-table { display: flex; flex-direction: column; gap: 2px; }
.sa__entity-row {
  display: grid; grid-template-columns: 1fr 1fr 1fr auto; gap: 4px;
  padding: 5px 6px; border-radius: var(--v2-radius-sm); transition: var(--v2-trans-fast);
}
.sa__entity-row:hover { background: var(--v2-bg-hover); }
.sa__entity-name { font-size: 12px; font-weight: var(--v2-font-medium); color: var(--v2-text-1); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sa__entity-aspect { font-family: var(--v2-font-mono); font-size: 11px; color: var(--v2-text-3); }
.sa__entity-opinion { font-size: 11px; color: var(--v2-text-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sa__entity-sent { font-family: var(--v2-font-mono); font-size: 11px; text-align: right; min-width: 32px; }
.sa__entity-sent--pos { color: #16a34a; }
.sa__entity-sent--neg { color: #dc2626; }
.sa__entity-sent--neu { color: var(--v2-text-4); }
:root[data-theme='dark'] .sa__entity-sent--pos { color: #4ade80; }
:root[data-theme='dark'] .sa__entity-sent--neg { color: #f87171; }

/* ── Intent Tags ── */
.sa__intents { border-top: var(--v2-border-width) solid var(--v2-border-2); padding-top: 12px; }
.sa__intents-title { font-family: var(--v2-font-mono); font-size: 10px; color: var(--v2-text-4); text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 8px; }
.sa__intents-list { display: flex; flex-wrap: wrap; gap: 4px; }
.sa__intent-tag {
  font-family: var(--v2-font-mono); font-size: 10px; padding: 2px 8px;
  border-radius: var(--v2-radius-sm); border: var(--v2-border-width) solid var(--v2-border-2);
  background: var(--v2-bg-hover); color: var(--v2-text-3); transition: var(--v2-trans-fast);
}
.sa__intent-tag:hover { color: var(--v2-text-1); border-color: var(--v2-border-3); }

/* ── Agent Signals Dispatch ── */
.sa__signals {
  border-top: var(--v2-border-width) solid var(--v2-border-2); padding-top: 12px;
  display: flex; flex-direction: column; gap: 8px;
}
.sa__signals-title {
  display: flex; align-items: center; gap: 5px;
  font-family: var(--v2-font-mono); font-size: 10px; color: var(--v2-text-4);
  text-transform: uppercase; letter-spacing: 0.04em;
}
.sa__signal-row {
  padding: 10px; border: var(--v2-border-width) solid var(--v2-border-1);
  border-radius: var(--v2-radius-sm); transition: var(--v2-trans-fast);
}
.sa__signal-row:hover { border-color: var(--v2-border-2); background: var(--v2-bg-hover); }
.sa__signal-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.sa__signal-agent {
  font-size: 11px; font-weight: var(--v2-font-semibold); color: var(--v2-text-1);
  padding: 1px 6px; background: var(--v2-bg-hover); border-radius: var(--v2-radius-sm);
}
.sa__signal-type { font-family: var(--v2-font-mono); font-size: 10px; color: var(--v2-text-4); }
.sa__signal-sev {
  font-family: var(--v2-font-mono); font-size: 10px; padding: 1px 6px;
  border-radius: var(--v2-radius-sm); margin-left: auto;
}
.sa__signal-sev--low { background: var(--v2-bg-hover); color: var(--v2-text-4); }
.sa__signal-sev--medium { background: rgba(234,179,8,0.08); color: #ca8a04; }
.sa__signal-sev--high { background: rgba(220,38,38,0.08); color: #dc2626; }
:root[data-theme='dark'] .sa__signal-sev--medium { background: rgba(250,204,21,0.08); color: #fbbf24; }
:root[data-theme='dark'] .sa__signal-sev--high { background: rgba(248,113,113,0.08); color: #f87171; }
.sa__signal-suggestion { font-size: 12px; color: var(--v2-text-2); line-height: 1.6; }
.sa__signal-entity { font-family: var(--v2-font-mono); font-size: 10px; color: var(--v2-text-4); margin-top: 4px; }

/* ── Similar Reviews (KB) ── */
.sa__similar {
  border-top: var(--v2-border-width) solid var(--v2-border-2); padding-top: 12px;
  display: flex; flex-direction: column; gap: 6px;
}
.sa__similar-title {
  display: flex; align-items: center; gap: 5px;
  font-family: var(--v2-font-mono); font-size: 10px; color: var(--v2-text-4);
  text-transform: uppercase; letter-spacing: 0.04em;
}
.sa__similar-badge {
  font-size: 9px; padding: 1px 5px; margin-left: 4px;
  border-radius: var(--v2-radius-sm); background: rgba(13,148,136,0.08); color: #0d9488;
}
:root[data-theme='dark'] .sa__similar-badge { background: rgba(45,212,191,0.08); color: #2dd4bf; }
.sa__similar-row {
  display: grid; grid-template-columns: 40px 1fr auto; gap: 8px; align-items: center;
  padding: 6px; border-radius: var(--v2-radius-sm); transition: var(--v2-trans-fast);
}
.sa__similar-row:hover { background: var(--v2-bg-hover); }
.sa__similar-score {
  font-family: var(--v2-font-mono); font-size: 10px; color: var(--v2-text-4);
  text-align: center; padding: 1px 4px; background: var(--v2-bg-hover); border-radius: var(--v2-radius-sm);
}
.sa__similar-text { font-size: 12px; color: var(--v2-text-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sa__similar-label { font-family: var(--v2-font-mono); font-size: 11px; }
.sa__similar-label--pos { color: #16a34a; }
.sa__similar-label--neg { color: #dc2626; }
.sa__similar-label--neu { color: var(--v2-text-4); }
:root[data-theme='dark'] .sa__similar-label--pos { color: #4ade80; }
:root[data-theme='dark'] .sa__similar-label--neg { color: #f87171; }

/* ── Step reveal animation ── */
.step-reveal-enter-active { transition: all 0.4s ease-out; }
.step-reveal-enter-from { opacity: 0; transform: translateY(8px); }
.step-reveal-enter-to { opacity: 1; transform: translateY(0); }

/* ── Reasoning status ── */
.sa__reasoning-status {
  display: inline-flex; align-items: center; gap: 4px; margin-left: auto;
  font-size: 10px; color: var(--v2-text-4);
}

/* ── Responsive ── */
@media (max-width: 1024px) {
  .sa__result { grid-template-columns: 1fr; }
}

/* ── Toggle AI Panel Button ── */
.sa__toggle-panel { display: flex; align-items: center; justify-content: center; width: 28px; height: 28px; border: 1px solid var(--v2-border-1); border-radius: var(--v2-radius-md); background: var(--v2-bg-card); color: var(--v2-text-3); cursor: pointer; transition: all var(--v2-trans-fast); }
.sa__toggle-panel:hover { color: var(--v2-text-1); }
.sa__toggle-panel--active { background: var(--v2-text-1); color: #fff; border-color: var(--v2-text-1); }

/* ── Right Detail Panel ── */
.sa__detail { display: flex; flex-direction: column; gap: var(--v2-space-3); padding: 12px; overflow-y: auto; }
.sa__detail h4 { font-size: 12px; font-weight: 600; color: var(--v2-text-3); text-transform: uppercase; letter-spacing: .5px; margin: 0 0 8px; padding-bottom: 6px; border-bottom: 1px solid var(--v2-border-2); }
.sa__dl { display: flex; justify-content: space-between; padding: 3px 0; font-size: 13px; }
.sa__dl > span:first-child { color: var(--v2-text-3); }
.sa__dl > span:last-child { color: var(--v2-text-1); font-variant-numeric: tabular-nums; }
.sa__detail-alert { display: inline-flex; align-items: center; gap: 6px; padding: 6px 10px; margin-top: 4px; font-size: 12px; color: var(--v2-danger); background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.16); border-radius: 8px; }
.sa__detail-ask { display: flex; align-items: center; justify-content: center; gap: 6px; padding: 8px; border: 1px solid var(--v2-border-1); border-radius: 8px; background: var(--v2-bg-card); font-size: 12px; font-weight: 500; color: var(--v2-text-1); cursor: pointer; transition: all 0.15s; font-family: inherit; margin-top: 4px; }
.sa__detail-ask:hover { background: var(--v2-bg-hover); }
.sa__empty-detail { display: flex; flex-direction: column; align-items: center; justify-content: center; flex: 1; gap: 8px; padding: 24px; color: var(--v2-text-4); }
.sa__empty-detail p { font-size: 12px; margin: 0; }
</style>
