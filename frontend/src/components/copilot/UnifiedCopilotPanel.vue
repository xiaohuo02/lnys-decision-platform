<template>
  <div class="ucp" :class="{ 'ucp--hist-open': showHistory }">
    <!-- History Side Panel -->
    <Transition name="ucp-hist-slide">
      <div class="ucp__hist" v-show="showHistory">
        <CopilotHistoryPanel
          :threads="threads"
          :active-thread-id="currentThreadId"
          @new-thread="startNewThread"
          @select-thread="loadThread"
          @toggle-pin="togglePin"
        />
      </div>
    </Transition>

    <!-- Main Chat Area -->
    <div class="ucp__main">
      <!-- Toolbar -->
      <div class="ucp__toolbar">
        <button class="ucp__icon-btn" @click="showHistory = !showHistory" title="History">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 8v4l3 3"/><circle cx="12" cy="12" r="10"/></svg>
        </button>
        <div class="ucp__toolbar-center">
          <h2 class="ucp__title">{{ modeLabel }}</h2>
          <div class="ucp__mode-switch">
            <button
              v-for="m in thinkModes" :key="m.key"
              :class="['ucp__mode-opt', { active: thinkMode === m.key }]"
              @click="thinkMode = m.key"
              :title="m.desc"
            >{{ m.label }}</button>
          </div>
        </div>
        <button class="ucp__icon-btn" @click="startNewThread" title="New chat">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 5v14M5 12h14"/></svg>
        </button>
      </div>

      <!-- Messages -->
      <div class="ucp__messages" ref="messagesRef">
        <!-- Welcome (empty state) -->
        <div class="ucp__welcome" v-if="!messages.length && !copilot.streaming.value">
          <div class="ucp__welcome-title">{{ modeLabel }}</div>
          <div class="ucp__welcome-sub">{{ mode === 'ops' ? '平台运维、系统健康、日志追踪' : '客户洞察、销售预测、舆情分析' }}</div>
          <div class="ucp__quick-grid">
            <button v-for="q in quickQuestions" :key="q" class="ucp__quick-btn" @click="ask(q)">{{ q }}</button>
          </div>
        </div>

        <!-- Message list -->
        <template v-for="(msg, i) in messages" :key="i">
          <!-- User message -->
          <div v-if="msg.role === 'user'" class="ucp__msg ucp__msg--user">
            <div class="ucp__msg-bubble">{{ msg.content }}</div>
          </div>

          <!-- Assistant message -->
          <div v-else class="ucp__msg ucp__msg--assistant">
            <!-- Thinking -->
            <CopilotThinkingBlock
              v-if="msg.thinking"
              :text="msg.thinking"
              :active="false"
            />

            <!-- Active Skill indicator -->
            <div class="ucp__skill-tag" v-if="msg.skill">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/></svg>
              {{ msg.skill }}
            </div>

            <!-- Artifacts -->
            <CopilotArtifactRenderer
              v-for="(art, ai) in msg.artifacts"
              :key="ai"
              :artifact="art"
            />

            <!-- Text content (markdown) -->
            <CopilotMarkdownRenderer
              v-if="msg.content"
              :text="msg.content"
              :streaming="false"
            />

            <!-- Fact Check: Sources -->
            <div class="ucp__sources" v-if="msg.sources?.length">
              <button class="ucp__sources-btn" @click="msg._showSources = !msg._showSources">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
                {{ msg._showSources ? 'Hide' : 'View' }} data sources ({{ msg.sources.length }})
              </button>
              <div v-if="msg._showSources" class="ucp__sources-list">
                <a v-for="(src, si) in msg.sources" :key="si" class="ucp__source-chip" :href="src.url || '#'" target="_blank">
                  {{ src.title || src.name || src.collection || 'Source ' + (si + 1) }}
                  <span v-if="src.score" class="ucp__source-score">{{ (src.score * 100).toFixed(0) }}%</span>
                </a>
              </div>
            </div>

            <!-- Governance toggle for committed messages -->
            <div v-if="msg._gov && (msg._gov.decisionSteps?.length || msg._gov.securityChecks?.length || msg._gov.contextStatus)" class="ucp__gov-toggle-wrap">
              <button class="ucp__gov-toggle" @click="msg._showGov = !msg._showGov">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                {{ msg._showGov ? '隐藏' : '查看' }}决策链
                <span class="ucp__gov-count">{{ msg._gov.decisionSteps?.length || 0 }} 步</span>
              </button>
              <Transition name="ucp-gov-fade">
                <div v-if="msg._showGov" class="ucp__gov ucp__gov--committed">
                  <CopilotSecurityBadge :checks="msg._gov.securityChecks" />
                  <CopilotContextGauge :ctx="msg._gov.contextStatus" />
                  <CopilotDecisionChain :steps="msg._gov.decisionSteps" />
                </div>
              </Transition>
            </div>

            <!-- Suggestions -->
            <CopilotSuggestions
              v-if="msg.suggestions?.length"
              :items="msg.suggestions"
              @select="handleSuggestion"
            />

            <!-- Feedback -->
            <div class="ucp__feedback" v-if="msg.content && !copilot.streaming.value">
              <button class="ucp__fb-btn" :class="{ 'ucp__fb-btn--active': msg.feedback === 1 }" @click="setFeedback(msg, 1)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 9V5a3 3 0 00-3-3l-4 9v11h11.28a2 2 0 002-1.7l1.38-9a2 2 0 00-2-2.3H14z"/></svg>
              </button>
              <button class="ucp__fb-btn" :class="{ 'ucp__fb-btn--active': msg.feedback === -1 }" @click="setFeedback(msg, -1)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M10 15V19a3 3 0 003 3l4-9V2H5.72a2 2 0 00-2 1.7l-1.38 9a2 2 0 002 2.3H10z"/></svg>
              </button>
            </div>
          </div>
        </template>

        <!-- Live streaming message -->
        <div class="ucp__msg ucp__msg--assistant" v-if="copilot.streaming.value">
          <!-- Governance Strip: Decision Chain + Context Gauge + Security -->
          <div class="ucp__gov" v-if="copilot.decisionSteps.value.length || copilot.contextStatus.value || copilot.securityChecks.value.length">
            <CopilotSecurityBadge :checks="copilot.securityChecks.value" />
            <CopilotContextGauge :ctx="copilot.contextStatus.value" />
            <CopilotDecisionChain :steps="copilot.decisionSteps.value" />
          </div>

          <CopilotThinkingBlock
            v-if="copilot.thinking.value"
            :text="copilot.thinking.value"
            :active="copilot.isThinking.value"
          />
          <div class="ucp__skill-tag" v-if="copilot.activeSkill.value?.name">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/></svg>
            {{ copilot.activeSkill.value.displayName || copilot.activeSkill.value.name }}
            <span class="ucp__skill-loading" v-if="copilot.activeSkill.value.loading"></span>
          </div>
          <CopilotArtifactRenderer
            v-for="(art, ai) in copilot.artifacts.value"
            :key="ai"
            :artifact="art"
          />
          <CopilotMarkdownRenderer
            v-if="copilot.text.value"
            :text="copilot.text.value"
            :streaming="copilot.streaming.value"
          />
        </div>

        <!-- Error -->
        <div class="ucp__error" v-if="copilot.error.value">{{ copilot.error.value }}</div>
      </div>

      <!-- Composer -->
      <div class="ucp__composer">
        <!-- @ Mention Autocomplete -->
        <Transition name="ucp-mention-fade">
          <div class="ucp__mention-popup" v-if="mentionOpen && mentionItems.length">
            <button
              v-for="item in mentionItems" :key="item.id"
              class="ucp__mention-item"
              @click="insertMention(item)"
            >
              <span class="ucp__mention-icon">{{ item.icon }}</span>
              <span class="ucp__mention-label">{{ item.label }}</span>
              <span class="ucp__mention-type">{{ item.type }}</span>
            </button>
          </div>
        </Transition>
        <div class="ucp__composer-inner">
          <!-- Context Pills -->
          <div class="ucp__pills" v-if="contextPills.length">
            <span v-for="(pill, pi) in contextPills" :key="pi" class="ucp__pill">
              @{{ pill.label }}
              <button class="ucp__pill-x" @click="removePill(pi)">&times;</button>
            </span>
          </div>
          <textarea
            ref="inputRef"
            v-model="input"
            class="ucp__input"
            :placeholder="placeholder"
            rows="1"
            @keydown.enter.exact.prevent="ask(input)"
            @input="onInputChange"
            @keydown.escape="mentionOpen = false"
          ></textarea>
          <button
            v-if="copilot.streaming.value"
            class="ucp__stop"
            @click="stopStreaming"
            title="停止生成"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>
          </button>
          <button
            v-else
            class="ucp__send"
            :disabled="!input.trim()"
            @click="ask(input)"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>
          </button>
        </div>
        <div class="ucp__composer-meta" v-if="copilot.elapsedMs.value">
          {{ copilot.elapsedMs.value }}ms
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, nextTick, onMounted, watch, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useCopilotStream } from '@/composables/useCopilotStream'
import { listThreads, getThreadMessages, submitFeedback, pinThread, unpinThread, executeAction, COPILOT_STREAM_URL } from '@/api/admin/copilot'
import CopilotArtifactRenderer from './CopilotArtifactRenderer.vue'
import CopilotThinkingBlock from './CopilotThinkingBlock.vue'
import CopilotSuggestions from './CopilotSuggestions.vue'
import CopilotHistoryPanel from './CopilotHistoryPanel.vue'
import CopilotMarkdownRenderer from './CopilotMarkdownRenderer.vue'
import CopilotDecisionChain from './CopilotDecisionChain.vue'
import CopilotContextGauge from './CopilotContextGauge.vue'
import CopilotSecurityBadge from './CopilotSecurityBadge.vue'

const props = defineProps({
  mode: { type: String, default: 'ops' },
})

const copilot = useCopilotStream()

const input = ref('')
const messages = ref([])
const currentThreadId = ref('')
const threads = ref([])
const showHistory = ref(false)
const messagesRef = ref(null)
const inputRef = ref(null)

const modeLabel = props.mode === 'ops' ? '运维助手' : '运营助手'

// ── Mode Switch (Auto/Think/Research) ──
const thinkModes = [
  { key: 'auto', label: 'Auto', desc: 'Automatic routing to the best skill' },
  { key: 'think', label: 'Think', desc: 'Deep reasoning with visible chain-of-thought' },
  { key: 'research', label: 'Research', desc: 'Multi-step investigation with sources' },
]
const thinkMode = ref('auto')

// ── @ Mention ──
const mentionOpen = ref(false)
const mentionQuery = ref('')
const contextPills = ref([])

const mentionCatalog = computed(() => {
  const items = [
    { id: 'inventory', label: 'Inventory', type: 'skill', icon: '\u{1F4E6}' },
    { id: 'forecast', label: 'Sales Forecast', type: 'skill', icon: '\u{1F4C8}' },
    { id: 'sentiment', label: 'Sentiment', type: 'skill', icon: '\u{1F4AC}' },
    { id: 'customer', label: 'Customer Intel', type: 'skill', icon: '\u{1F465}' },
    { id: 'fraud', label: 'Fraud Scoring', type: 'skill', icon: '\u{1F6E1}' },
    { id: 'association', label: 'Association Mining', type: 'skill', icon: '\u{1F517}' },
    { id: 'kb_rag', label: 'Knowledge Base', type: 'collection', icon: '\u{1F4DA}' },
    { id: 'trace', label: 'Trace Logs', type: 'data', icon: '\u{1F50D}' },
    { id: 'system', label: 'System Health', type: 'data', icon: '\u{2699}' },
  ]
  if (props.mode === 'biz') return items.filter(i => !['fraud', 'trace', 'system'].includes(i.id))
  return items
})

const mentionItems = computed(() => {
  if (!mentionQuery.value) return mentionCatalog.value
  const q = mentionQuery.value.toLowerCase()
  return mentionCatalog.value.filter(i => i.label.toLowerCase().includes(q) || i.id.includes(q))
})

function onInputChange() {
  autoResize()
  // Detect @ trigger
  const val = input.value
  const lastAt = val.lastIndexOf('@')
  if (lastAt >= 0 && lastAt === val.length - 1) {
    mentionOpen.value = true
    mentionQuery.value = ''
  } else if (lastAt >= 0) {
    const after = val.slice(lastAt + 1)
    if (!after.includes(' ') && after.length < 20) {
      mentionOpen.value = true
      mentionQuery.value = after
    } else {
      mentionOpen.value = false
    }
  } else {
    mentionOpen.value = false
  }
}

function insertMention(item) {
  const lastAt = input.value.lastIndexOf('@')
  if (lastAt >= 0) input.value = input.value.slice(0, lastAt)
  contextPills.value.push({ id: item.id, label: item.label, type: item.type })
  mentionOpen.value = false
  inputRef.value?.focus()
}

function removePill(index) {
  contextPills.value.splice(index, 1)
}

const placeholder = props.mode === 'ops'
  ? '询问系统健康、追踪日志、智能体、评测...'
  : '询问客户分析、销售预测、库存优化、舆情...'

const quickQuestions = props.mode === 'ops'
  ? [
      '当前系统健康状态',
      '最近有失败的运行吗？',
      '最慢的 5 次运行',
      '当前加载了哪些智能体？',
    ]
  : [
      '客户流失风险概览',
      '未来 7 天销售预测',
      '有库存预警吗？',
      '当前舆情分析',
    ]

// ── Methods ──

async function ask(question) {
  const q = (typeof question === 'string' ? question : input.value).trim()
  if (!q) return
  if (copilot.streaming.value) {
    copilot.stop()
    await nextTick()
  }
  input.value = ''
  autoResize()

  messages.value.push({ role: 'user', content: q })
  scrollToBottom()

  const url = COPILOT_STREAM_URL[props.mode] || COPILOT_STREAM_URL.ops

  // Build page_context with @ mentions and think mode
  const pageCtx = {
    page: window.location.pathname,
    think_mode: thinkMode.value,
    mentions: contextPills.value.map(p => ({ type: p.type, id: p.id })),
  }
  contextPills.value = []

  await copilot.send(url, {
    question: q,
    thread_id: currentThreadId.value || undefined,
    mode: props.mode,
    page_context: pageCtx,
  }, {
    onDone: (result) => {
      if (result.threadId && !currentThreadId.value) {
        currentThreadId.value = result.threadId
      }
      // Commit assistant message
      const govSnap = {
        decisionSteps: [...copilot.decisionSteps.value],
        contextStatus: copilot.contextStatus.value ? { ...copilot.contextStatus.value } : null,
        securityChecks: [...copilot.securityChecks.value],
        memoryLayers: [...copilot.memoryLayers.value],
      }
      messages.value.push(reactive({
        role: 'assistant',
        content: copilot.text.value,
        thinking: copilot.thinking.value,
        skill: copilot.activeSkill.value?.displayName || copilot.activeSkill.value?.name || '',
        artifacts: [...copilot.artifacts.value],
        suggestions: [...copilot.suggestions.value],
        sources: [...copilot.sources.value],
        feedback: null,
        messageId: null,
        _showSources: false,
        // Governance snapshot
        _gov: govSnap,
        _showGov: false,
      }))
      // Refresh history
      fetchThreads()
    },
  })
}

function stopStreaming() {
  copilot.stop()
  // Commit whatever was streamed so far
  if (copilot.text.value) {
    messages.value.push(reactive({
      role: 'assistant',
      content: copilot.text.value,
      thinking: copilot.thinking.value,
      skill: copilot.activeSkill.value?.displayName || copilot.activeSkill.value?.name || '',
      artifacts: [...copilot.artifacts.value],
      suggestions: [],
      sources: [...copilot.sources.value],
      feedback: null,
      messageId: null,
      _showSources: false,
    }))
  }
}

function handleSuggestion(item) {
  if (item.type === 'question') {
    ask(item.label)
  } else if (item.type === 'action') {
    confirmAction(item)
  }
}

async function confirmAction(item) {
  const confirmed = window.confirm(`Execute action: ${item.label}?`)
  if (!confirmed) return
  try {
    await executeAction(
      item.action,
      item.payload?.group || item.payload?.target || '',
      item.payload,
      currentThreadId.value,
    )
  } catch (e) {
    console.error('[action]', e)
  }
}

async function setFeedback(msg, value) {
  msg.feedback = value
  if (msg.messageId) {
    try { await submitFeedback(msg.messageId, value) } catch { /* silent */ }
  }
}

function startNewThread() {
  currentThreadId.value = ''
  messages.value = []
  copilot.reset()
}

async function fetchThreads() {
  try {
    const res = await listThreads({ mode: props.mode, limit: 50 })
    threads.value = res.data?.threads || res.threads || []
  } catch { threads.value = [] }
}

async function loadThread(threadId) {
  currentThreadId.value = threadId
  try {
    const res = await getThreadMessages(threadId, { limit: 100 })
    const rawMsgs = res.data?.messages || res.messages || []
    messages.value = rawMsgs.map(m => ({
      role: m.role,
      content: m.content,
      thinking: m.thinking || '',
      skill: m.skills_used?.[0] || '',
      artifacts: m.artifacts || [],
      suggestions: m.suggestions || [],
      feedback: m.feedback,
      messageId: m.id,
    }))
    scrollToBottom()
  } catch { messages.value = [] }
}

async function togglePin(threadId, value) {
  try {
    if (value) await pinThread(threadId)
    else await unpinThread(threadId)
    await fetchThreads()
  } catch { /* silent */ }
}

function autoResize() {
  nextTick(() => {
    if (inputRef.value) {
      inputRef.value.style.height = 'auto'
      inputRef.value.style.height = Math.min(inputRef.value.scrollHeight, 160) + 'px'
    }
  })
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

// Auto-scroll on streaming
watch(() => copilot.text.value, () => scrollToBottom())
watch(() => copilot.artifacts.value, () => scrollToBottom(), { deep: true })

const route = useRoute()

onMounted(() => {
  fetchThreads()
  if (route.query.thread_id) {
    loadThread(route.query.thread_id)
  }
  inputRef.value?.focus()
})

defineExpose({ ask, startNewThread })
</script>

<style scoped>
.ucp { display: flex; height: 100%; background: #fff; overflow: hidden; }
.ucp--hist-open .ucp__hist { width: 260px; }

/* History panel */
.ucp__hist { width: 0; border-right: 1px solid rgba(0,0,0,0.06); overflow: hidden; transition: width 0.25s ease; flex-shrink: 0; background: #fafafa; }
.ucp-hist-slide-enter-active, .ucp-hist-slide-leave-active { transition: width 0.25s ease; }

/* Main */
.ucp__main { flex: 1; display: flex; flex-direction: column; min-width: 0; }

/* Toolbar */
.ucp__toolbar { display: flex; align-items: center; gap: 12px; padding: 12px 20px; border-bottom: 1px solid rgba(0,0,0,0.06); flex-shrink: 0; }
.ucp__toolbar-center { flex: 1; display: flex; align-items: center; gap: 8px; justify-content: center; }
.ucp__title { font-size: 14px; font-weight: 600; color: #18181b; margin: 0; }
.ucp__mode-badge { font-size: 10px; padding: 2px 8px; border-radius: 999px; background: rgba(0,0,0,0.04); color: #71717a; font-weight: 500; text-transform: uppercase; letter-spacing: 0.5px; }
.ucp__icon-btn { width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; border: 1px solid rgba(0,0,0,0.06); border-radius: 8px; background: #fff; cursor: pointer; color: #71717a; transition: all 0.15s; }
.ucp__icon-btn:hover { background: #f4f4f5; color: #18181b; }

/* Messages */
.ucp__messages { flex: 1; overflow-y: auto; padding: 24px 20px; display: flex; flex-direction: column; gap: 16px; }

/* Welcome */
.ucp__welcome { display: flex; flex-direction: column; align-items: center; justify-content: center; flex: 1; gap: 12px; }
.ucp__welcome-title { font-size: 24px; font-weight: 600; color: #18181b; }
.ucp__welcome-sub { font-size: 14px; color: #71717a; }
.ucp__quick-grid { display: flex; flex-wrap: wrap; gap: 8px; max-width: 480px; margin-top: 16px; justify-content: center; }
.ucp__quick-btn { padding: 8px 16px; border: 1px solid rgba(0,0,0,0.08); border-radius: 999px; background: #fff; font-size: 13px; color: #18181b; cursor: pointer; transition: all 0.15s; }
.ucp__quick-btn:hover { background: #f4f4f5; border-color: rgba(0,0,0,0.15); }

/* Messages */
.ucp__msg { max-width: 720px; width: 100%; }
.ucp__msg--user { align-self: flex-end; max-width: 85%; }
.ucp__msg--user .ucp__msg-bubble { background: #f4f4f5; color: #18181b; padding: 10px 16px; border-radius: 20px; font-size: 14px; line-height: 1.6; word-break: break-word; }
.ucp__msg--assistant { align-self: flex-start; }
.ucp__msg--assistant .ucp__msg-content { font-size: 14px; line-height: 1.7; color: #18181b; }
.ucp__msg--assistant .ucp__msg-content :deep(code) { font-family: 'Geist Mono', monospace; font-size: 13px; padding: 1px 6px; background: rgba(0,0,0,0.04); border-radius: 4px; }
.ucp__msg--assistant .ucp__msg-content :deep(strong) { font-weight: 600; }

/* Skill tag */
.ucp__skill-tag { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: #71717a; padding: 4px 10px; background: rgba(0,0,0,0.03); border-radius: 6px; margin-bottom: 8px; }
.ucp__skill-loading { width: 6px; height: 6px; border-radius: 50%; background: #18181b; animation: pulse 1s infinite; }

@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }

/* Error */
.ucp__error { font-size: 13px; color: #dc2626; padding: 8px 12px; background: rgba(220,38,38,0.04); border-radius: 6px; }

/* Feedback */
.ucp__feedback { display: flex; gap: 4px; margin-top: 8px; }
.ucp__fb-btn { width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; border: 1px solid rgba(0,0,0,0.06); border-radius: 6px; background: #fff; cursor: pointer; color: #a1a1aa; transition: all 0.15s; }
.ucp__fb-btn:hover { color: #18181b; background: #f4f4f5; }
.ucp__fb-btn--active { color: #18181b; background: rgba(0,0,0,0.06); }

/* Composer */
.ucp__composer { padding: 12px 20px 20px; border-top: 1px solid rgba(0,0,0,0.06); flex-shrink: 0; position: relative; }
.ucp__composer-inner { display: flex; align-items: flex-end; gap: 8px; border: 1px solid rgba(0,0,0,0.1); border-radius: 12px; padding: 8px 12px; background: #fff; transition: border-color 0.15s; }
.ucp__composer-inner:focus-within { border-color: rgba(0,0,0,0.25); }
.ucp__input { flex: 1; border: none; outline: none; font-size: 14px; line-height: 1.5; resize: none; font-family: inherit; min-height: 24px; max-height: 160px; background: transparent; }
.ucp__input::placeholder { color: #a1a1aa; }
.ucp__send { width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; border-radius: 8px; border: none; background: #18181b; color: #fff; cursor: pointer; flex-shrink: 0; transition: all 0.15s; }
.ucp__send:hover { background: #27272a; }
.ucp__send:disabled { background: #e4e4e7; color: #a1a1aa; cursor: not-allowed; }
.ucp__stop { width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; border-radius: 8px; border: 1.5px solid rgba(0,0,0,0.15); background: #fff; color: #18181b; cursor: pointer; flex-shrink: 0; transition: all 0.15s; }
.ucp__stop:hover { background: #f4f4f5; border-color: rgba(0,0,0,0.25); }
.ucp__composer-meta { font-size: 11px; color: #a1a1aa; text-align: right; margin-top: 4px; font-variant-numeric: tabular-nums; }

/* Mode Switch */
.ucp__mode-switch { display: flex; gap: 0; background: rgba(0,0,0,0.04); border-radius: 6px; padding: 2px; }
.ucp__mode-opt {
  padding: 4px 12px; font-size: 11px; font-weight: 500; color: #71717a;
  background: none; border: none; border-radius: 4px; cursor: pointer;
  transition: all 0.15s; letter-spacing: 0.3px;
}
.ucp__mode-opt:hover { color: #18181b; }
.ucp__mode-opt.active { background: #fff; color: #18181b; box-shadow: 0 1px 2px rgba(0,0,0,0.06); }

/* @ Mention Popup */
.ucp__mention-popup {
  position: absolute; bottom: 100%; left: 12px; right: 12px;
  background: #fff; border: 1px solid rgba(0,0,0,0.1); border-radius: 10px;
  max-height: 240px; overflow-y: auto; z-index: 10;
  box-shadow: 0 4px 12px rgba(0,0,0,0.08);
}
.ucp__mention-item {
  display: flex; align-items: center; gap: 8px; padding: 8px 14px;
  width: 100%; border: none; background: none; cursor: pointer;
  font-size: 13px; color: #18181b; transition: background 0.1s;
}
.ucp__mention-item:hover { background: #f4f4f5; }
.ucp__mention-icon { font-size: 15px; width: 22px; text-align: center; }
.ucp__mention-label { flex: 1; text-align: left; }
.ucp__mention-type { font-size: 11px; color: #a1a1aa; padding: 1px 6px; background: rgba(0,0,0,0.04); border-radius: 3px; }
.ucp-mention-fade-enter-active, .ucp-mention-fade-leave-active { transition: opacity 0.15s, transform 0.15s; }
.ucp-mention-fade-enter-from, .ucp-mention-fade-leave-to { opacity: 0; transform: translateY(4px); }

/* Context Pills */
.ucp__pills { display: flex; flex-wrap: wrap; gap: 4px; padding-bottom: 4px; width: 100%; }
.ucp__pill {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 12px; font-weight: 500; color: #18181b;
  padding: 2px 8px; background: rgba(0,0,0,0.04); border-radius: 4px;
}
.ucp__pill-x { border: none; background: none; cursor: pointer; color: #a1a1aa; font-size: 14px; padding: 0 2px; }
.ucp__pill-x:hover { color: #18181b; }

/* Fact Check Sources */
.ucp__sources { margin-top: 8px; }
.ucp__sources-btn {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; color: #71717a; background: none; border: 1px solid rgba(0,0,0,0.08);
  border-radius: 6px; padding: 4px 10px; cursor: pointer; transition: all 0.15s;
}
.ucp__sources-btn:hover { color: #18181b; border-color: rgba(0,0,0,0.15); }
.ucp__sources-list { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.ucp__source-chip {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 12px; color: #18181b; padding: 4px 10px;
  background: #fafafa; border: 1px solid rgba(0,0,0,0.06);
  border-radius: 6px; text-decoration: none; transition: all 0.15s;
}
.ucp__source-chip:hover { background: #f4f4f5; border-color: rgba(0,0,0,0.12); }
.ucp__source-score { font-size: 10px; color: #a1a1aa; font-variant-numeric: tabular-nums; }

/* Governance Strip */
.ucp__gov {
  display: flex; flex-direction: column; gap: 6px;
  padding: 8px 10px; margin-bottom: 8px;
  background: rgba(0,0,0,0.02); border: 1px solid rgba(0,0,0,0.06);
  border-radius: 8px;
}
.ucp__gov--committed { margin-top: 4px; }

.ucp__gov-toggle-wrap { margin-top: 6px; }
.ucp__gov-toggle {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 11px; color: #71717a; background: none; border: 1px solid rgba(0,0,0,0.08);
  border-radius: 6px; padding: 3px 10px; cursor: pointer; transition: all 0.15s;
}
.ucp__gov-toggle:hover { color: #18181b; border-color: rgba(0,0,0,0.15); }
.ucp__gov-count { font-size: 10px; color: #a1a1aa; margin-left: 2px; }

.ucp-gov-fade-enter-active, .ucp-gov-fade-leave-active { transition: opacity 0.2s, max-height 0.25s ease; overflow: hidden; }
.ucp-gov-fade-enter-from, .ucp-gov-fade-leave-to { opacity: 0; max-height: 0; }
.ucp-gov-fade-enter-to, .ucp-gov-fade-leave-from { opacity: 1; max-height: 400px; }
</style>
