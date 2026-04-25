<template>
  <div class="cp">
    <!-- Messages area -->
    <div class="cp__messages" ref="messagesRef">
      <div v-if="!messages.length" class="cp__empty">
        <el-icon :size="32" class="cp__empty-icon"><ChatLineRound /></el-icon>
        <p>{{ emptyText }}</p>
      </div>

      <div
        v-for="msg in messages"
        :key="msg.id"
        class="cp__msg"
        :class="[`cp__msg--${msg.role}`]"
      >
        <!-- Avatar -->
        <span class="cp__avatar" :class="`cp__avatar--${msg.role}`">
          {{ msg.role === 'user' ? 'U' : 'AI' }}
        </span>

        <!-- Body -->
        <div class="cp__bubble">
          <div class="cp__content" v-html="msg.html || escapeHtml(msg.content || '')" />

          <!-- Streaming cursor -->
          <span v-if="msg.streaming" class="cp__cursor" />

          <!-- Meta -->
          <div v-if="msg.intent || msg.confidence || msg.timestamp" class="cp__meta">
            <span v-if="msg.intent" class="cp__intent">
              {{ msg.intent }}
              <span v-if="msg.confidence" class="cp__conf">{{ Math.round(msg.confidence * 100) }}%</span>
            </span>
            <span v-if="msg.timestamp" class="cp__time">{{ formatTime(msg.timestamp) }}</span>
          </div>
        </div>
      </div>

      <!-- Typing indicator -->
      <div v-if="loading" class="cp__msg cp__msg--assistant">
        <span class="cp__avatar cp__avatar--assistant">AI</span>
        <div class="cp__bubble">
          <div class="cp__typing">
            <span /><span /><span />
          </div>
        </div>
      </div>
    </div>

    <!-- Input area -->
    <div v-if="showInput" class="cp__input-area">
      <div class="cp__input-wrap">
        <textarea
          ref="inputRef"
          class="cp__input"
          v-model="inputText"
          :placeholder="placeholder"
          :disabled="disabled || loading"
          rows="1"
          @keydown.enter.exact.prevent="handleSend"
          @input="autoResize"
        />
        <button
          class="cp__send"
          :disabled="!inputText.trim() || disabled || loading"
          @click="handleSend"
          title="发送"
        >
          <el-icon :size="16"><Promotion /></el-icon>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, watch, onMounted } from 'vue'
import { ChatLineRound, Promotion } from '@element-plus/icons-vue'

const props = defineProps({
  messages:    { type: Array, default: () => [] },
  loading:     { type: Boolean, default: false },
  disabled:    { type: Boolean, default: false },
  showInput:   { type: Boolean, default: true },
  placeholder: { type: String, default: '输入消息…' },
  emptyText:   { type: String, default: '开始对话' },
})

const emit = defineEmits(['send'])

const inputText   = ref('')
const inputRef    = ref(null)
const messagesRef = ref(null)

function handleSend() {
  const text = inputText.value.trim()
  if (!text || props.disabled || props.loading) return
  emit('send', text)
  inputText.value = ''
  nextTick(() => autoResize())
}

function autoResize() {
  const el = inputRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 120) + 'px'
}

function scrollToBottom() {
  nextTick(() => {
    const el = messagesRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\n/g, '<br>')
}

function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

watch(() => props.messages.length, () => scrollToBottom())
watch(() => props.loading, () => scrollToBottom())

onMounted(() => scrollToBottom())

defineExpose({ scrollToBottom })
</script>

<style scoped>
.cp {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

/* ── Messages ────────────────────────────────────────── */
.cp__messages {
  flex: 1;
  overflow-y: auto;
  padding: var(--v2-space-4);
  display: flex;
  flex-direction: column;
  gap: var(--v2-space-4);
}

.cp__empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--v2-space-2);
  color: var(--v2-text-4);
  font-size: var(--v2-text-sm);
}
.cp__empty-icon { color: var(--v2-text-4); }

/* ── Message row ─────────────────────────────────────── */
.cp__msg {
  display: flex;
  gap: var(--v2-space-2);
  max-width: 85%;
}
.cp__msg--user {
  align-self: flex-end;
  flex-direction: row-reverse;
}
.cp__msg--assistant {
  align-self: flex-start;
}

/* Avatar */
.cp__avatar {
  width: 28px; height: 28px;
  border-radius: var(--v2-radius-full);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--v2-text-2xs);
  font-weight: var(--v2-font-bold);
  flex-shrink: 0;
}
.cp__avatar--user {
  background: var(--v2-brand-primary);
  color: #fff;
}
.cp__avatar--assistant {
  background: var(--v2-ai-purple-bg);
  color: var(--v2-ai-purple);
}

/* Bubble */
.cp__bubble {
  padding: var(--v2-space-2) var(--v2-space-3);
  border-radius: var(--v2-radius-lg);
  font-size: var(--v2-text-sm);
  line-height: var(--v2-leading-normal);
  min-width: 0;
}
.cp__msg--user .cp__bubble {
  background: var(--v2-brand-primary);
  color: #fff;
  border-bottom-right-radius: var(--v2-radius-sm);
}
.cp__msg--assistant .cp__bubble {
  background: var(--v2-bg-elevated);
  color: var(--v2-text-1);
  border: 1px solid var(--v2-border-2);
  border-bottom-left-radius: var(--v2-radius-sm);
}

.cp__content {
  word-break: break-word;
}

/* Streaming cursor */
.cp__cursor {
  display: inline-block;
  width: 2px; height: 14px;
  background: var(--v2-text-1);
  margin-left: 2px;
  vertical-align: text-bottom;
  animation: cp-blink 1s step-end infinite;
}

/* Meta row */
.cp__meta {
  display: flex;
  align-items: center;
  gap: var(--v2-space-2);
  margin-top: 4px;
  font-size: var(--v2-text-2xs);
}
.cp__msg--user .cp__meta { color: rgba(255,255,255,.7); }
.cp__msg--assistant .cp__meta { color: var(--v2-text-4); }

.cp__intent {
  display: flex;
  align-items: center;
  gap: 4px;
}
.cp__conf {
  padding: 0 4px;
  border-radius: 3px;
  background: var(--v2-tag-purple);
  color: var(--v2-tag-purple-text);
  font-size: var(--v2-text-2xs);
}
.cp__time { margin-left: auto; }

/* ── Typing indicator ────────────────────────────────── */
.cp__typing {
  display: flex;
  gap: 4px;
  padding: 4px 0;
}
.cp__typing span {
  width: 6px; height: 6px;
  border-radius: var(--v2-radius-full);
  background: var(--v2-text-4);
  animation: cp-bounce .6s ease-in-out infinite;
}
.cp__typing span:nth-child(2) { animation-delay: .15s; }
.cp__typing span:nth-child(3) { animation-delay: .3s; }

/* ── Input area ──────────────────────────────────────── */
.cp__input-area {
  border-top: 1px solid var(--v2-border-2);
  padding: var(--v2-space-3);
  background: var(--v2-bg-card);
}
.cp__input-wrap {
  display: flex;
  align-items: flex-end;
  gap: var(--v2-space-2);
  border: 1px solid var(--v2-border-1);
  border-radius: var(--v2-radius-lg);
  padding: var(--v2-space-2) var(--v2-space-3);
  background: var(--v2-bg-sunken);
  transition: border-color var(--v2-trans-fast);
}
.cp__input-wrap:focus-within {
  border-color: var(--v2-brand-primary);
}

.cp__input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  color: var(--v2-text-1);
  font-size: var(--v2-text-sm);
  font-family: var(--v2-font-sans);
  line-height: var(--v2-leading-normal);
  resize: none;
  max-height: 120px;
}
.cp__input::placeholder { color: var(--v2-text-4); }
.cp__input:disabled { opacity: .5; cursor: not-allowed; }

.cp__send {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px; height: 32px;
  border: none;
  border-radius: var(--v2-radius-md);
  background: var(--v2-brand-primary);
  color: #fff;
  cursor: pointer;
  flex-shrink: 0;
  transition: all var(--v2-trans-fast);
}
.cp__send:hover:not(:disabled) { background: var(--v2-brand-primary-h); }
.cp__send:disabled { opacity: .4; cursor: not-allowed; }

/* ── Animations ──────────────────────────────────────── */
@keyframes cp-blink {
  50% { opacity: 0; }
}
@keyframes cp-bounce {
  0%, 100% { transform: translateY(0); }
  50%      { transform: translateY(-4px); }
}
</style>
