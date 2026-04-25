<template>
  <div class="oc-layout">
    <!-- Left Sidebar: Session List (Minimalist Twitter-like) -->
    <aside class="oc-sidebar" :class="{ 'is-hidden': !showSidebar }">
      <div class="oc-sidebar__hd">
        <h2 class="oc-sidebar__title">对话</h2>
        <button class="v2-btn v2-btn--ghost oc-sidebar__new" @click="startNewSession">
          <el-icon><Edit3 /></el-icon>
        </button>
      </div>
      
      <div class="oc-sidebar__list" v-loading="loadingList">
        <div v-if="sessions.length === 0 && !loadingList" class="oc-empty-state">暂无对话记录</div>
        <div 
          v-for="s in sessions" :key="s.id"
          class="oc-session v2-magnetic"
          :class="{ 'is-active': s.id === currentSessionId }"
          @click="switchSession(s.id)"
        >
          <div class="oc-session__title v2-truncate">{{ s.title || '新对话' }}</div>
          <div class="oc-session__meta v2-mono-meta">{{ formatTime(s.created_at) }}</div>
        </div>
      </div>
    </aside>

    <!-- Main Chat Area: Immersive Composer (ChatGPT Style) -->
    <main class="oc-main">
      <header class="oc-main__hd">
        <button class="v2-btn v2-btn--ghost oc-sidebar-toggle" @click="showSidebar = !showSidebar">
          <el-icon><PanelLeft /></el-icon>
        </button>
        <div class="oc-model-info">
          OpenClaw v1.0 <span class="oc-model-badge">BERT + FAQ</span>
        </div>
        <div class="oc-main__actions">
          <button class="v2-btn v2-btn--ghost" title="清除历史" @click="clearHistory">
            <el-icon><Trash2 /></el-icon>
          </button>
        </div>
      </header>

      <!-- Message Feed -->
      <div class="oc-feed" ref="feedRef">
        <!-- Empty State / Suggestion Chips -->
        <div v-if="!loadingHistory && messages.length === 0" class="oc-hero">
          <div class="oc-hero__icon"><el-icon :size="48"><Sparkles /></el-icon></div>
          <h1 class="oc-hero__title">今天我能帮您什么？</h1>
          
          <div class="oc-suggestions">
            <button class="oc-chip v2-magnetic" @click="useSuggestion('查询我的最近订单')">
              查询我的最近订单
            </button>
            <button class="oc-chip v2-magnetic" @click="useSuggestion('查看退款状态')">
              查看退款状态
            </button>
            <button class="oc-chip v2-magnetic" @click="useSuggestion('推荐热门商品')">
              推荐热门商品
            </button>
          </div>
        </div>

        <!-- Chat Bubbles -->
        <div class="oc-message" v-for="(msg, idx) in messages" :key="idx" :class="`oc-message--${msg.role}`">
          
          <!-- Avatar -->
          <div class="oc-avatar" v-if="msg.role === 'assistant'">
            <el-icon><Sparkles /></el-icon>
          </div>

          <!-- Content Wrapper -->
          <div class="oc-content-wrapper">
            <!-- User Bubble -->
            <div v-if="msg.role === 'user'" class="oc-bubble oc-bubble--user">
              {{ msg.content }}
            </div>

            <!-- Assistant Output -->
            <div v-else class="oc-assistant-output">
              
              <!-- Thinking Artifact -->
              <div v-if="msg.thinking" class="oc-thinking">
                <el-icon class="oc-spin"><Loader2 /></el-icon> 正在分析意图与上下文...
              </div>

              <!-- Tool Call Card (GenUI) -->
              <div v-if="msg.tool_call" class="oc-tool-card v2-magnetic">
                <el-icon><Settings /></el-icon> 正在执行 {{ msg.tool_call }}... <el-icon class="oc-success-icon"><CheckCircle2 /></el-icon>
              </div>

              <!-- Markdown Stream/Content -->
              <MarkdownRenderer 
                v-if="msg.content" 
                :content="msg.content" 
                :streaming="msg.streaming" 
                class="oc-markdown"
              />

              <!-- Context Tags (Intent / Confidence) -->
              <div v-if="msg.intent && !msg.streaming" class="oc-meta-tags">
                <span class="v2-badge v2-badge--purple">{{ msg.intent }}</span>
                <span class="v2-mono-meta">置信度: {{ (msg.confidence * 100).toFixed(1) }}%</span>
                <span v-if="msg.handoff" class="v2-badge v2-badge--error">需要人工介入</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Composer (Input Area) -->
      <div class="oc-composer-wrap">
        <div class="oc-composer">
          <!-- Context Pills -->
          <div class="oc-composer__pills" v-if="selectedCustomer">
            <div class="oc-pill">
              <el-icon><User /></el-icon> {{ selectedCustomer }}
              <button @click="selectedCustomer = ''"><el-icon><X /></el-icon></button>
            </div>
          </div>

          <div class="oc-composer__input-row">
            <textarea
              ref="inputRef"
              v-model="inputContent"
              class="oc-textarea"
              placeholder="输入消息..."
              rows="1"
              @keydown.enter.prevent="handleEnter"
              @input="autoResize"
              :disabled="isGenerating"
            ></textarea>
            
            <button 
              class="oc-send-btn" 
              :class="{ 'is-active': inputContent.trim().length > 0 }"
              :disabled="!inputContent.trim() || isGenerating"
              @click="sendMessage"
            >
              <el-icon><ArrowUp /></el-icon>
            </button>
          </div>
        </div>
        <div class="oc-composer__footer">
          <span class="v2-mono-meta">OpenClaw 可能会犯错，请核实重要信息。</span>
        </div>
      </div>
    </main>

    <!-- Right Sidebar: Context & Artifacts Split View (Slide In) -->
    <aside class="oc-artifacts" :class="{ 'is-open': showArtifacts }">
      <div class="oc-artifacts__hd">
        <h3 class="oc-sidebar__title">工件</h3>
        <button class="v2-btn v2-btn--ghost" @click="showArtifacts = false">
          <el-icon><X /></el-icon>
        </button>
      </div>
      <div class="oc-artifacts__body">
        <!-- Trace / Knowledge references go here -->
        <div class="oc-empty-state" style="margin-top: 100px;">
          本轮对话暂无工件生成。
        </div>
      </div>
    </aside>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted } from 'vue'
import { 
  Sparkles, Edit3, PanelLeft, Trash2, ArrowUp, Loader2, Settings, CheckCircle2, User, X
} from 'lucide-vue-next'
import MarkdownRenderer from '@/components/v2/MarkdownRenderer.vue'
import { chatApi } from '@/api/business/chat'

// UI State
const showSidebar = ref(true)
const showArtifacts = ref(false) // Triggered when complex data needs displaying
const feedRef = ref(null)
const inputRef = ref(null)

// Data State
const sessions = ref([])
const currentSessionId = ref(null)
const messages = ref([])
const inputContent = ref('')
const isGenerating = ref(false)
const selectedCustomer = ref('') // Example Context Pill
const loadingHistory = ref(false)
const loadingList = ref(false)

// Formatting
function formatTime(isoStr) {
  if(!isoStr) return ''
  const d = new Date(isoStr)
  return `${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`
}

function autoResize() {
  if (!inputRef.value) return
  const el = inputRef.value
  el.style.height = 'auto'
  // Max height corresponds to ~50vh
  const newHeight = Math.min(el.scrollHeight, window.innerHeight * 0.5)
  el.style.height = newHeight + 'px'
}

function handleEnter(e) {
  if (e.shiftKey) {
    // Normal newline
    return
  }
  sendMessage()
}

function useSuggestion(text) {
  inputContent.value = text
  sendMessage()
}

async function scrollToBottom() {
  await nextTick()
  if (feedRef.value) {
    feedRef.value.scrollTo({ top: feedRef.value.scrollHeight, behavior: 'smooth' })
  }
}

// Real SSE streaming via /api/chat/stream
async function sendMessage() {
  if (!inputContent.value.trim() || isGenerating.value) return
  
  const text = inputContent.value.trim()
  inputContent.value = ''
  autoResize()

  // Add User Message
  messages.value.push({ role: 'user', content: text })
  scrollToBottom()

  isGenerating.value = true
  
  // Add Empty Assistant Message (Thinking state)
  const assistantMsg = {
    role: 'assistant',
    content: '',
    thinking: true,
    streaming: false,
    tool_call: null
  }
  messages.value.push(assistantMsg)
  scrollToBottom()

  try {
    const token = localStorage.getItem('token') || ''
    const response = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        session_id: currentSessionId.value,
        message: text,
        customer_id: selectedCustomer.value || undefined,
      }),
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    assistantMsg.thinking = false
    assistantMsg.streaming = true

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      let currentEvent = ''
      for (const line of lines) {
        if (line.startsWith('event:')) {
          currentEvent = line.slice(6).trim()
        } else if (line.startsWith('data:')) {
          const raw = line.slice(5).trim()
          if (!raw) continue
          try {
            const data = JSON.parse(raw)
            if (currentEvent === 'token' || (!currentEvent && data.content)) {
              assistantMsg.content += data.content
              scrollToBottom()
            } else if (currentEvent === 'done') {
              assistantMsg.intent = data.intent
              assistantMsg.confidence = data.confidence
              if (data.intent) assistantMsg.tool_call = data.intent
            } else if (currentEvent === 'error') {
              assistantMsg.content += `\n\n⚠️ ${data.message || '对话异常'}`
            }
          } catch { /* ignore non-JSON */ }
          currentEvent = ''
        }
      }
    }

    assistantMsg.streaming = false
  } catch (e) {
    console.error('[OpenClaw] stream error:', e)
    assistantMsg.thinking = false
    assistantMsg.streaming = false
    if (!assistantMsg.content) {
      assistantMsg.content = '抱歉，连接服务时出现了问题，请稍后重试。'
    }
  } finally {
    isGenerating.value = false
    if (inputRef.value) inputRef.value.focus()
  }
}

async function startNewSession() {
  currentSessionId.value = Date.now().toString()
  messages.value = []
  if (inputRef.value) inputRef.value.focus()
}

function clearHistory() {
  messages.value = []
}

async function switchSession(id) {
  currentSessionId.value = id
  messages.value = []
  loadingHistory.value = true
  try {
    const res = await chatApi.getHistory(id)
    const history = res?.messages ?? res?.items ?? []
    messages.value = history.map(m => ({
      role: m.role,
      content: m.content || m.message || '',
      intent: m.intent,
      confidence: m.confidence,
    }))
  } catch (e) {
    console.warn('[OpenClaw] load history failed:', e)
  } finally {
    loadingHistory.value = false
    scrollToBottom()
  }
}

onMounted(() => {
  currentSessionId.value = Date.now().toString()
  sessions.value = [
    { id: currentSessionId.value, title: '新会话', created_at: new Date().toISOString() }
  ]
})
</script>

<style scoped>
.oc-layout {
  display: flex;
  height: calc(100vh - var(--v2-header-height));
  width: 100vw;
  margin-left: calc(var(--v2-space-6) * -1);
  margin-top: calc(var(--v2-space-6) * -1);
  background: var(--v2-bg-page);
  overflow: hidden;
}

/* ── Sidebar ── */
.oc-sidebar {
  width: 260px;
  background: var(--v2-bg-card); /* White/Zinc 950 */
  border-right: var(--v2-border-width) solid var(--v2-border-2);
  display: flex;
  flex-direction: column;
  transition: var(--v2-trans-spring);
  flex-shrink: 0;
}
.oc-sidebar.is-hidden {
  width: 0;
  border-right-width: 0;
  opacity: 0;
}
.oc-sidebar__hd {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  height: 60px;
  flex-shrink: 0;
}
.oc-sidebar__title {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
  color: var(--v2-text-1);
}
.oc-sidebar__new {
  padding: 6px;
  border-radius: var(--v2-radius-btn);
  color: var(--v2-text-1);
}
.oc-sidebar__list {
  flex: 1;
  overflow-y: auto;
  padding: 8px 12px;
}
.oc-session {
  padding: 10px 12px;
  border-radius: var(--v2-radius-btn);
  cursor: pointer;
  margin-bottom: 4px;
  /* Twitter-style Active/Hover (No backgrounds, just text bolding and subtle indicators) */
  color: var(--v2-text-3);
  transition: color 0.15s;
}
.oc-session:hover { color: var(--v2-text-1); }
.oc-session.is-active {
  background: var(--v2-bg-hover);
  color: var(--v2-text-1);
}
.oc-session__title {
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 2px;
}
.oc-session__meta {
  font-size: 11px;
}

/* ── Main Chat Area ── */
.oc-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  position: relative;
  min-width: 0;
}
.oc-main__hd {
  height: 60px;
  display: flex;
  align-items: center;
  padding: 0 16px;
  justify-content: space-between;
  flex-shrink: 0;
}
.oc-model-info {
  font-size: 14px;
  font-weight: 500;
  color: var(--v2-text-1);
  display: flex;
  align-items: center;
  gap: 8px;
}
.oc-model-badge {
  font-family: var(--v2-font-mono);
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--v2-bg-hover);
  color: var(--v2-text-3);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* ── Feed & Messages ── */
.oc-feed {
  flex: 1;
  overflow-y: auto;
  padding: 24px 0 120px; /* Padding bottom for composer */
  scroll-behavior: smooth;
  /* Narrower max-width for better reading measure, ChatGPT style */
  display: flex;
  flex-direction: column;
  align-items: center;
}

/* Hero / Empty State */
.oc-hero {
  margin-top: 10vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  width: 100%;
  max-width: 700px;
}
.oc-hero__icon {
  width: 64px; height: 64px;
  background: var(--v2-bg-card);
  border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-full);
  display: flex; align-items: center; justify-content: center;
  color: var(--v2-text-1);
  margin-bottom: 24px;
}
.oc-hero__title {
  font-size: 28px;
  font-weight: 600;
  letter-spacing: -0.03em;
  color: var(--v2-text-1);
  margin-bottom: 32px;
}
.oc-suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  justify-content: center;
}
.oc-chip {
  padding: 10px 16px;
  background: var(--v2-bg-card);
  border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-pill);
  font-size: 13px;
  color: var(--v2-text-2);
  cursor: pointer;
  transition: var(--v2-trans-spring);
}
.oc-chip:hover {
  background: var(--v2-bg-hover);
  color: var(--v2-text-1);
  border-color: var(--v2-text-3);
}

/* Message Bubbles */
.oc-message {
  width: 100%;
  max-width: 768px; /* Strict reading measure */
  padding: 24px;
  display: flex;
  gap: 16px;
}
.oc-message--user {
  justify-content: flex-end;
}

.oc-avatar {
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  border-radius: 6px;
  background: var(--v2-bg-card);
  border: var(--v2-border-width) solid var(--v2-border-2);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--v2-text-1);
}

.oc-content-wrapper {
  max-width: 85%;
  display: flex;
  flex-direction: column;
}

.oc-bubble--user {
  background: var(--v2-bg-hover); /* Subtle gray instead of bright primary */
  color: var(--v2-text-1);
  padding: 12px 16px;
  border-radius: 18px 18px 4px 18px; /* Classic chat bubble radius */
  font-size: 15px;
  line-height: 1.5;
}

.oc-assistant-output {
  font-size: 15px;
  line-height: 1.6;
  color: var(--v2-text-1);
  min-width: 300px;
}

.oc-thinking {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--v2-text-3);
  font-family: var(--v2-font-mono);
}
.oc-spin { animation: spin 1s linear infinite; }
@keyframes spin { 100% { transform: rotate(360deg); } }

/* Tool Call Card (GenUI style) */
.oc-tool-card {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  margin-bottom: 12px;
  background: var(--v2-bg-card);
  border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-btn);
  font-family: var(--v2-font-mono);
  font-size: 12px;
  color: var(--v2-text-2);
}
.oc-success-icon { color: var(--v2-text-1); }

.oc-meta-tags {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
}

/* ── Composer (Bottom Input Area) ── */
.oc-composer-wrap {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 0 24px 24px;
  background: linear-gradient(to top, var(--v2-bg-page) 60%, transparent);
  display: flex;
  flex-direction: column;
  align-items: center;
}
.oc-composer {
  width: 100%;
  max-width: 768px;
  background: var(--v2-bg-card);
  border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: 24px; /* Large, plush rounded corners like ChatGPT */
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  /* The zero-shadow rule is respected, we only use border and bg color */
  transition: border-color var(--v2-trans-fast);
}
.oc-composer:focus-within {
  border-color: var(--v2-border-1); /* Darken border on focus */
}

/* Context Pills above text */
.oc-composer__pills {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}
.oc-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  background: var(--v2-bg-hover);
  border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-btn);
  font-size: 12px;
  font-weight: 500;
  color: var(--v2-text-2);
}
.oc-pill button {
  background: none; border: none; padding: 0; display: flex; align-items: center; cursor: pointer; color: var(--v2-text-3);
}
.oc-pill button:hover { color: var(--v2-text-1); }

.oc-composer__input-row {
  display: flex;
  align-items: flex-end;
  gap: 12px;
}
.oc-textarea {
  flex: 1;
  border: none;
  background: transparent;
  color: var(--v2-text-1);
  font-family: var(--v2-font-sans);
  font-size: 15px;
  line-height: 1.5;
  resize: none;
  outline: none;
  max-height: 50vh; /* Auto-grows up to half the screen smoothly */
  padding: 4px 0;
}
.oc-textarea::placeholder { color: var(--v2-text-4); }

/* The Arrow Send Button */
.oc-send-btn {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: none;
  background: var(--v2-bg-hover);
  color: var(--v2-text-4);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all var(--v2-trans-fast);
}
.oc-send-btn.is-active {
  background: var(--v2-text-1);
  color: var(--v2-bg-page);
}
.oc-send-btn:disabled { cursor: not-allowed; }

.oc-composer__footer {
  margin-top: 8px;
  text-align: center;
}

/* ── Artifacts Split View ── */
.oc-artifacts {
  width: 0;
  background: var(--v2-bg-card);
  border-left: 0px solid var(--v2-border-2);
  transition: var(--v2-trans-spring);
  display: flex;
  flex-direction: column;
}
.oc-artifacts.is-open {
  width: 400px; /* Expands smoothly using spring physics */
  border-left-width: var(--v2-border-width);
}
.oc-artifacts__hd {
  height: 60px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 16px;
  border-bottom: var(--v2-border-width) solid var(--v2-border-2);
}
.oc-artifacts__body {
  flex: 1;
  overflow-y: auto;
}

@media (max-width: 768px) {
  .oc-sidebar { display: none; }
  .oc-message { padding: 16px; }
  .oc-composer-wrap { padding: 0 16px 16px; }
  .oc-artifacts.is-open { width: 100vw; position: absolute; right: 0; top: 0; bottom: 0; z-index: 50; }
}
</style>
