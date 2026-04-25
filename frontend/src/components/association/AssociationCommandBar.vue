<template>
  <div class="acb">
    <!-- Context pills -->
    <div v-if="pills.length" class="acb__pills">
      <span v-for="p in pills" :key="p.key" class="acb__pill">
        {{ p.label }}
        <button class="acb__pill-x" @click="$emit('remove-pill', p.key)">×</button>
      </span>
    </div>

    <div class="acb__row">
      <textarea
        ref="inputRef"
        v-model="text"
        class="acb__input"
        :placeholder="placeholder"
        :disabled="disabled"
        rows="1"
        @keydown.enter.exact.prevent="send"
        @input="autoResize"
        @keydown="onKeydown"
      />
      <button class="acb__send" :disabled="!text.trim() || disabled" @click="send">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
      </button>
    </div>

    <!-- @ mention popup -->
    <div v-if="showMention" class="acb__mention">
      <div
        v-for="s in filteredSkills"
        :key="s.id"
        class="acb__mention-item"
        :class="{ 'acb__mention-item--active': mentionIdx === filteredSkills.indexOf(s) }"
        @mousedown.prevent="insertMention(s)"
      >
        <span class="acb__mention-name">@{{ s.id }}</span>
        <span class="acb__mention-desc">{{ s.desc }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  disabled:    { type: Boolean, default: false },
  placeholder: { type: String,  default: '输入关联分析问题… (⌘K 聚焦)' },
  pills:       { type: Array,   default: () => [] },
})

const emit = defineEmits(['send', 'remove-pill'])

const text = ref('')
const inputRef = ref(null)
const showMention = ref(false)
const mentionIdx = ref(0)
const mentionQuery = ref('')

const SKILLS = [
  { id: 'association_skill', desc: '关联分析' },
  { id: 'inventory_skill',   desc: '库存管理' },
  { id: 'forecast',          desc: '销售预测' },
  { id: 'customer_intel',    desc: '客户分析' },
  { id: 'sentiment',         desc: '舆情分析' },
  { id: 'kb_rag',            desc: '知识库' },
  { id: 'fraud',             desc: '欺诈检测' },
]

const filteredSkills = computed(() => {
  const q = mentionQuery.value.toLowerCase()
  return SKILLS.filter(s => s.id.includes(q) || s.desc.includes(q))
})

function autoResize() {
  const el = inputRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 100) + 'px'
}

function send() {
  const q = text.value.trim()
  if (!q || props.disabled) return
  // Extract mentions
  const mentions = []
  const mentionRe = /@(\w+)/g
  let match
  while ((match = mentionRe.exec(q)) !== null) {
    const skill = SKILLS.find(s => s.id === match[1])
    if (skill) mentions.push({ type: 'skill', id: skill.id })
  }
  emit('send', q, mentions)
  text.value = ''
  nextTick(autoResize)
}

function onKeydown(ev) {
  // @ mention trigger
  if (ev.key === '@' || (showMention.value && ['ArrowUp', 'ArrowDown', 'Enter', 'Escape'].includes(ev.key))) {
    if (ev.key === '@') {
      showMention.value = true
      mentionQuery.value = ''
      mentionIdx.value = 0
      return
    }
    if (ev.key === 'Escape') { showMention.value = false; return }
    if (ev.key === 'ArrowDown') { ev.preventDefault(); mentionIdx.value = Math.min(mentionIdx.value + 1, filteredSkills.value.length - 1); return }
    if (ev.key === 'ArrowUp') { ev.preventDefault(); mentionIdx.value = Math.max(mentionIdx.value - 1, 0); return }
    if (ev.key === 'Enter' && showMention.value && filteredSkills.value.length) {
      ev.preventDefault()
      insertMention(filteredSkills.value[mentionIdx.value])
      return
    }
  }
  if (showMention.value) {
    nextTick(() => {
      const cursor = text.value.lastIndexOf('@')
      mentionQuery.value = cursor >= 0 ? text.value.slice(cursor + 1) : ''
      mentionIdx.value = 0
    })
  }
}

function insertMention(skill) {
  const cursor = text.value.lastIndexOf('@')
  text.value = text.value.slice(0, cursor) + `@${skill.id} `
  showMention.value = false
  nextTick(() => inputRef.value?.focus())
}

// ⌘K shortcut
function onGlobalKey(ev) {
  if ((ev.metaKey || ev.ctrlKey) && ev.key === 'k') {
    ev.preventDefault()
    inputRef.value?.focus()
  }
}

onMounted(() => document.addEventListener('keydown', onGlobalKey))
onUnmounted(() => document.removeEventListener('keydown', onGlobalKey))

function focus() { inputRef.value?.focus() }
defineExpose({ focus })
</script>

<style scoped>
.acb { position: relative; padding: var(--v2-space-3) var(--v2-space-4); background: var(--v2-bg-card); border-top: 1px solid var(--v2-border-2); }
.acb__pills { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: var(--v2-space-2); }
.acb__pill { display: inline-flex; align-items: center; gap: 4px; font-size: 10px; padding: 1px 8px; border-radius: var(--v2-radius-full); background: var(--v2-bg-sunken); color: var(--v2-text-2); border: 1px solid var(--v2-border-2); }
.acb__pill-x { background: none; border: none; font-size: 12px; color: var(--v2-text-4); cursor: pointer; padding: 0; margin-left: 2px; line-height: 1; }
.acb__row { display: flex; align-items: flex-end; gap: var(--v2-space-2); border: 1px solid var(--v2-border-1); border-radius: var(--v2-radius-lg); padding: var(--v2-space-2) var(--v2-space-3); background: var(--v2-bg-sunken); transition: border-color var(--v2-trans-fast); }
.acb__row:focus-within { border-color: var(--v2-brand-primary); }
.acb__input { flex: 1; border: none; outline: none; background: transparent; color: var(--v2-text-1); font-size: var(--v2-text-sm); font-family: var(--v2-font-sans); line-height: 1.5; resize: none; max-height: 100px; }
.acb__input::placeholder { color: var(--v2-text-4); }
.acb__input:disabled { opacity: .5; cursor: not-allowed; }
.acb__send { display: flex; align-items: center; justify-content: center; width: 28px; height: 28px; border: none; border-radius: var(--v2-radius-md); background: var(--v2-text-1); color: #fff; cursor: pointer; flex-shrink: 0; transition: opacity var(--v2-trans-fast); }
.acb__send:hover:not(:disabled) { opacity: .8; }
.acb__send:disabled { opacity: .3; cursor: not-allowed; }
.acb__mention { position: absolute; bottom: 100%; left: var(--v2-space-4); right: var(--v2-space-4); background: var(--v2-bg-elevated, var(--v2-bg-card)); border: 1px solid var(--v2-border-1); border-radius: var(--v2-radius-md); box-shadow: 0 -4px 16px rgba(0,0,0,0.08); max-height: 200px; overflow-y: auto; z-index: 20; }
.acb__mention-item { display: flex; align-items: center; gap: var(--v2-space-2); padding: 6px 12px; cursor: pointer; transition: background var(--v2-trans-fast); }
.acb__mention-item:hover, .acb__mention-item--active { background: var(--v2-bg-sunken); }
.acb__mention-name { font-size: var(--v2-text-xs); font-weight: 600; font-family: 'Geist Mono', monospace; color: var(--v2-brand-primary); }
.acb__mention-desc { font-size: var(--v2-text-xs); color: var(--v2-text-3); }
</style>
