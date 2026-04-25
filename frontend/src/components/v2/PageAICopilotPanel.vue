<template>
  <div class="pcp">
    <!-- ── Tab Bar ── -->
    <div class="pcp__tabs">
      <button
        v-for="t in normalizedTabs"
        :key="t.id"
        class="pcp__tab"
        :class="{ 'pcp__tab--active': activeTab === t.id }"
        @click="activeTab = t.id"
      >
        <span v-if="t.icon" v-html="t.icon" class="pcp__tab-icon"></span>
        {{ t.label }}
      </button>
      <button
        v-if="ai?.openInFullCopilot"
        class="pcp__tab pcp__tab--open"
        title="在 Copilot 中打开"
        @click="ai.openInFullCopilot(router)"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3"/></svg>
      </button>
    </div>

    <!-- ── AI Tab ── -->
    <div v-show="activeTab === 'ai'" class="pcp__body">
      <!-- Thread selector -->
      <div class="pcp__thread-bar" v-if="ai?.threadHistory?.value?.length">
        <select
          class="pcp__thread-select"
          :value="ai.currentThreadId.value"
          @change="onThreadChange($event.target.value)"
        >
          <option value="">新对话</option>
          <option
            v-for="t in ai.threadHistory.value"
            :key="t.id"
            :value="t.id"
          >{{ t.title || t.id.slice(0, 8) + '...' }}</option>
        </select>
      </div>

      <!-- Messages -->
      <div class="pcp__messages" ref="messagesRef">
        <!-- Welcome state -->
        <div class="pcp__welcome" v-if="!ai?.messages?.value?.length && !ai?.streaming?.value">
          <div class="pcp__welcome-icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
          </div>
          <p class="pcp__welcome-title">{{ welcomeTitle }}</p>
          <p class="pcp__welcome-desc" v-if="welcomeDesc">{{ welcomeDesc }}</p>
          <div class="pcp__chips" v-if="quickQuestions.length">
            <button
              v-for="q in quickQuestions"
              :key="q"
              class="pcp__chip"
              @click="ai.ask(q)"
            >{{ q }}</button>
          </div>
        </div>

        <!-- Message list -->
        <template v-for="(msg, i) in ai?.messages?.value" :key="i">
          <!-- User message -->
          <div v-if="msg.role === 'user'" class="pcp__msg pcp__msg--user">
            <div class="pcp__msg-bubble">{{ msg.content }}</div>
          </div>
          <!-- Assistant message -->
          <div v-else class="pcp__msg pcp__msg--assistant">
            <div class="pcp__msg-skill" v-if="msg.skill">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/></svg>
              {{ msg.skill }}
            </div>
            <CopilotArtifactRenderer
              v-for="(art, ai2) in (msg.artifacts || [])"
              :key="ai2"
              :artifact="art"
            />
            <CopilotMarkdownRenderer
              v-if="msg.content"
              :text="msg.content"
              :streaming="false"
            />
            <CopilotSuggestions
              v-if="msg.suggestions?.length"
              :items="msg.suggestions"
              @select="ai.handleSuggestion"
            />
            <!-- Sources -->
            <div class="pcp__sources" v-if="msg.sources?.length">
              <button class="pcp__sources-btn" @click="msg._showSources = !msg._showSources">
                {{ msg._showSources ? '隐藏' : '查看' }}来源 ({{ msg.sources.length }})
              </button>
              <div v-if="msg._showSources" class="pcp__sources-list">
                <span v-for="(s, si) in msg.sources" :key="si" class="pcp__source-chip">
                  {{ s.title || s.name || 'Source ' + (si+1) }}
                  <span v-if="s.score" class="pcp__source-score">{{ (s.score*100).toFixed(0) }}%</span>
                </span>
              </div>
            </div>
            <!-- Feedback -->
            <div class="pcp__feedback" v-if="msg.content">
              <button
                :class="['pcp__fb-btn', { 'pcp__fb-btn--on': msg.feedback === 1 }]"
                @click="ai.setFeedback(msg, 1)"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 9V5a3 3 0 00-3-3l-4 9v11h11.28a2 2 0 002-1.7l1.38-9a2 2 0 00-2-2.3H14z"/></svg>
              </button>
              <button
                :class="['pcp__fb-btn', { 'pcp__fb-btn--on': msg.feedback === -1 }]"
                @click="ai.setFeedback(msg, -1)"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M10 15V19a3 3 0 003 3l4-9V2H5.72a2 2 0 00-2 1.7l-1.38 9a2 2 0 002 2.3H10z"/></svg>
              </button>
            </div>
          </div>
        </template>

        <!-- Live streaming -->
        <div class="pcp__msg pcp__msg--assistant" v-if="ai?.streaming?.value">
          <div class="pcp__msg-skill" v-if="ai.activeSkill?.value?.name">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/></svg>
            {{ ai.activeSkill.value.displayName || ai.activeSkill.value.name }}
            <span class="pcp__skill-dot"></span>
          </div>
          <CopilotArtifactRenderer
            v-for="(art, ai3) in ai.artifacts?.value"
            :key="ai3"
            :artifact="art"
          />
          <CopilotMarkdownRenderer
            v-if="ai.text?.value"
            :text="ai.text.value"
            :streaming="true"
          />
        </div>

        <!-- Error -->
        <div class="pcp__error" v-if="ai?.error?.value">{{ ai.error.value }}</div>
      </div>

      <!-- Command Bar -->
      <PageCommandBar
        :placeholder="commandBarPlaceholder"
        :mention-catalog="mentionCatalog"
        :disabled="ai?.streaming?.value"
        @send="onCommandSend"
      />
    </div>

    <!-- ── Detail Tab ── -->
    <div v-show="activeTab === 'detail'" class="pcp__body">
      <slot name="detail">
        <div class="pcp__empty-tab">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1"><path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/></svg>
          <p>选择数据行查看详情</p>
        </div>
      </slot>
    </div>

    <!-- ── KB Tab ── -->
    <div v-show="activeTab === 'kb'" class="pcp__body">
      <slot name="kb">
        <KBSearchPanelV2
          :collection="collection"
          @doc-click="onKbDocClick"
        />
      </slot>
    </div>

    <!-- ── Extra tabs via slot ── -->
    <template v-for="t in extraTabs" :key="t.id">
      <div v-show="activeTab === t.id" class="pcp__body">
        <slot :name="'tab-' + t.id" />
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import CopilotArtifactRenderer from '@/components/copilot/CopilotArtifactRenderer.vue'
import CopilotMarkdownRenderer from '@/components/copilot/CopilotMarkdownRenderer.vue'
import CopilotSuggestions from '@/components/copilot/CopilotSuggestions.vue'
import PageCommandBar from './PageCommandBar.vue'
import KBSearchPanelV2 from './KBSearchPanelV2.vue'

const props = defineProps({
  ai: { type: Object, required: true },
  tabs: {
    type: Array,
    default: () => [
      { id: 'ai', label: 'AI', icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>' },
      { id: 'detail', label: '详情', icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/></svg>' },
      { id: 'kb', label: '知识库', icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/></svg>' },
    ],
  },
  quickQuestions: { type: Array, default: () => [] },
  welcomeTitle: { type: String, default: 'AI 助手' },
  welcomeDesc: { type: String, default: '' },
  collection: { type: String, default: '' },
  commandBarPlaceholder: { type: String, default: '输入问题...  @ 选择智能体' },
  mentionCatalog: {
    type: Array,
    default: () => [
      { id: 'customer_intel', label: '客群洞察', type: 'skill', icon: '👥' },
      { id: 'forecast', label: '销售预测', type: 'skill', icon: '📈' },
      { id: 'fraud', label: '风控中心', type: 'skill', icon: '🛡️' },
      { id: 'sentiment', label: '舆情分析', type: 'skill', icon: '💬' },
      { id: 'association', label: '关联分析', type: 'skill', icon: '🔗' },
      { id: 'inventory_skill', label: '库存管理', type: 'skill', icon: '📦' },
      { id: 'kb_rag', label: '知识库', type: 'collection', icon: '📚' },
    ],
  },
})

const emit = defineEmits(['tab-change', 'kb-doc-click'])
const router = useRouter()
const messagesRef = ref(null)
const activeTab = ref('ai')

const normalizedTabs = computed(() => props.tabs)
const extraTabs = computed(() => props.tabs.filter(t => !['ai', 'detail', 'kb'].includes(t.id)))

watch(activeTab, (v) => emit('tab-change', v))

function scrollMessages() {
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

watch(() => props.ai?.text?.value, scrollMessages)
watch(() => props.ai?.artifacts?.value, scrollMessages, { deep: true })

function onThreadChange(threadId) {
  if (threadId) {
    props.ai?.switchThread?.(threadId)
  } else {
    props.ai?.startNewThread?.()
  }
}

function onCommandSend({ question, mentions }) {
  activeTab.value = 'ai'
  props.ai?.ask?.(question, mentions)
  scrollMessages()
}

function onKbDocClick(doc) {
  emit('kb-doc-click', doc)
  activeTab.value = 'ai'
  props.ai?.ask?.(`关于「${doc.title || doc.name}」，请总结关键内容`, [{ type: 'collection', id: 'kb_rag' }])
}

function switchTab(tabId) {
  activeTab.value = tabId
}

function askAndSwitch(question, mentions) {
  activeTab.value = 'ai'
  props.ai?.ask?.(question, mentions)
  scrollMessages()
}

defineExpose({ switchTab, askAndSwitch, scrollMessages })
</script>

<style scoped>
.pcp { display: flex; flex-direction: column; height: 100%; background: var(--v2-bg-card, #fff); }

/* ── Tabs ── */
.pcp__tabs { display: flex; border-bottom: 1px solid rgba(0,0,0,0.06); flex-shrink: 0; }
.pcp__tab {
  flex: 1;
  display: flex; align-items: center; justify-content: center; gap: 5px;
  padding: 10px 8px;
  border: none; background: none;
  font-size: 12px; font-weight: 500; color: #a1a1aa;
  cursor: pointer; transition: all 0.15s; font-family: inherit;
  border-bottom: 2px solid transparent;
}
.pcp__tab:hover { color: #18181b; }
.pcp__tab--active { color: #18181b; border-bottom-color: #18181b; }
.pcp__tab--open { flex: 0; padding: 10px 8px; margin-left: auto; color: #a1a1aa; }
.pcp__tab--open:hover { color: #18181b; }
.pcp__tab-icon { display: flex; align-items: center; }

/* ── Body ── */
.pcp__body { flex: 1; min-height: 0; overflow: hidden; display: flex; flex-direction: column; }

/* ── Thread bar ── */
.pcp__thread-bar { display: flex; align-items: center; gap: 6px; padding: 8px 12px; border-bottom: 1px solid rgba(0,0,0,0.04); flex-shrink: 0; }
.pcp__thread-select { flex: 1; border: 1px solid rgba(0,0,0,0.08); border-radius: 6px; padding: 4px 8px; font-size: 11px; background: #fff; color: #18181b; font-family: inherit; outline: none; }
.pcp__thread-select:focus { border-color: rgba(0,0,0,0.2); }

/* ── Messages ── */
.pcp__messages { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 10px; }

/* ── Welcome ── */
.pcp__welcome { display: flex; flex-direction: column; align-items: center; justify-content: center; flex: 1; gap: 10px; }
.pcp__welcome-icon { color: #a1a1aa; }
.pcp__welcome-title { font-size: 14px; font-weight: 600; color: #18181b; margin: 0; }
.pcp__welcome-desc { font-size: 12px; color: #71717a; margin: 0; text-align: center; }
.pcp__chips { display: flex; flex-wrap: wrap; gap: 6px; justify-content: center; margin-top: 4px; }
.pcp__chip {
  padding: 6px 12px; border: 1px solid rgba(0,0,0,0.08); border-radius: 999px;
  background: #fff; font-size: 12px; color: #18181b; cursor: pointer;
  transition: all 0.15s; font-family: inherit;
}
.pcp__chip:hover { background: #f4f4f5; border-color: rgba(0,0,0,0.15); }

/* ── Messages ── */
.pcp__msg { max-width: 100%; }
.pcp__msg--user { align-self: flex-end; }
.pcp__msg-bubble { background: #f4f4f5; color: #18181b; padding: 8px 14px; border-radius: 16px; font-size: 13px; line-height: 1.5; word-break: break-word; }
.pcp__msg--assistant { align-self: flex-start; }
.pcp__msg--assistant :deep(code) { font-family: 'Geist Mono', monospace; font-size: 12px; }

.pcp__msg-skill {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 11px; color: #71717a;
  padding: 3px 8px; background: rgba(0,0,0,0.03); border-radius: 5px;
  margin-bottom: 6px;
}
.pcp__skill-dot { width: 5px; height: 5px; border-radius: 50%; background: #18181b; animation: pcp-pulse 1s infinite; }
@keyframes pcp-pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }

/* ── Sources ── */
.pcp__sources { margin-top: 6px; }
.pcp__sources-btn { font-size: 11px; color: #71717a; background: none; border: 1px solid rgba(0,0,0,0.08); border-radius: 5px; padding: 2px 8px; cursor: pointer; font-family: inherit; }
.pcp__sources-btn:hover { color: #18181b; border-color: rgba(0,0,0,0.15); }
.pcp__sources-list { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
.pcp__source-chip { font-size: 10px; padding: 2px 8px; background: #fafafa; border: 1px solid rgba(0,0,0,0.06); border-radius: 4px; color: #18181b; }
.pcp__source-score { color: #a1a1aa; margin-left: 4px; }

/* ── Feedback ── */
.pcp__feedback { display: flex; gap: 3px; margin-top: 6px; }
.pcp__fb-btn {
  width: 24px; height: 24px;
  display: flex; align-items: center; justify-content: center;
  border: 1px solid rgba(0,0,0,0.06); border-radius: 5px;
  background: #fff; cursor: pointer; color: #a1a1aa; transition: all 0.15s;
}
.pcp__fb-btn:hover { color: #18181b; background: #f4f4f5; }
.pcp__fb-btn--on { color: #18181b; background: rgba(0,0,0,0.06); }

/* ── Error ── */
.pcp__error { font-size: 12px; color: #dc2626; padding: 6px 10px; background: rgba(220,38,38,0.04); border-radius: 5px; }

/* ── Empty tab ── */
.pcp__empty-tab {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  flex: 1; gap: 8px; color: #a1a1aa; padding: 20px;
}
.pcp__empty-tab p { font-size: 12px; margin: 0; }
</style>
