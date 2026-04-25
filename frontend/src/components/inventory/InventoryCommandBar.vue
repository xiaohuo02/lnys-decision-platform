<template>
  <div class="icb">
    <div class="icb__inner" :class="{ 'icb__inner--focus': focused }">
      <!-- Context Pills -->
      <div class="icb__pills" v-if="contextPills.length">
        <span v-for="(pill, i) in contextPills" :key="i" class="icb__pill">
          @{{ pill.label }}
          <button class="icb__pill-x" @click="removePill(i)">&times;</button>
        </span>
      </div>

      <!-- @ Mention Popup -->
      <Transition name="icb-mention">
        <div class="icb__mention-popup" v-if="mentionOpen && filteredMentions.length">
          <button
            v-for="item in filteredMentions"
            :key="item.id"
            class="icb__mention-item"
            @click="insertMention(item)"
          >
            <span class="icb__mention-icon">{{ item.icon }}</span>
            <span class="icb__mention-label">{{ item.label }}</span>
            <span class="icb__mention-type">{{ item.type }}</span>
          </button>
        </div>
      </Transition>

      <svg class="icb__icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>

      <textarea
        ref="inputRef"
        v-model="input"
        class="icb__input"
        placeholder="询问库存相关问题...  输入 @ 选择智能体"
        rows="1"
        @keydown.enter.exact.prevent="submit"
        @input="onInputChange"
        @focus="focused = true"
        @blur="onBlur"
        @keydown.escape="mentionOpen = false"
      ></textarea>

      <button
        class="icb__send"
        :disabled="!input.trim()"
        @click="submit"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'

const emit = defineEmits(['send'])

const props = defineProps({
  mentionCatalog: {
    type: Array,
    default: () => [
      { id: 'inventory', label: '库存分析', type: 'skill', icon: '\u{1F4E6}' },
      { id: 'forecast', label: '销售预测', type: 'skill', icon: '\u{1F4C8}' },
      { id: 'association', label: '关联分析', type: 'skill', icon: '\u{1F517}' },
      { id: 'kb_rag', label: '知识库', type: 'collection', icon: '\u{1F4DA}' },
      { id: 'sentiment', label: '舆情分析', type: 'skill', icon: '\u{1F4AC}' },
    ],
  },
})

const input = ref('')
const inputRef = ref(null)
const focused = ref(false)
const contextPills = ref([])
const mentionOpen = ref(false)
const mentionQuery = ref('')

const filteredMentions = computed(() => {
  if (!mentionQuery.value) return props.mentionCatalog
  const q = mentionQuery.value.toLowerCase()
  return props.mentionCatalog.filter(
    i => i.label.toLowerCase().includes(q) || i.id.includes(q)
  )
})

function onInputChange() {
  autoResize()
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

function submit() {
  const q = input.value.trim()
  if (!q) return
  const mentions = contextPills.value.map(p => ({ type: p.type, id: p.id }))
  emit('send', { question: q, mentions })
  input.value = ''
  contextPills.value = []
  autoResize()
}

function autoResize() {
  nextTick(() => {
    if (inputRef.value) {
      inputRef.value.style.height = 'auto'
      inputRef.value.style.height = Math.min(inputRef.value.scrollHeight, 80) + 'px'
    }
  })
}

function onBlur() {
  setTimeout(() => {
    focused.value = false
    mentionOpen.value = false
  }, 150)
}

defineExpose({ focus: () => inputRef.value?.focus() })
</script>

<style scoped>
.icb {
  padding: 8px 16px 12px;
  flex-shrink: 0;
}

.icb__inner {
  position: relative;
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 8px 12px;
  border: 1px solid rgba(0,0,0,0.08);
  border-radius: 12px;
  background: #fff;
  transition: border-color 0.15s;
}
.icb__inner--focus {
  border-color: rgba(0,0,0,0.2);
}

.icb__icon { color: #a1a1aa; flex-shrink: 0; margin-bottom: 2px; }

.icb__input {
  flex: 1;
  border: none;
  outline: none;
  font-size: 13px;
  line-height: 1.5;
  resize: none;
  min-height: 22px;
  max-height: 80px;
  background: transparent;
  font-family: inherit;
  color: #18181b;
}
.icb__input::placeholder { color: #a1a1aa; }

.icb__send {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  border: none;
  background: #18181b;
  color: #fff;
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.15s;
}
.icb__send:hover { background: #27272a; }
.icb__send:disabled { background: #e4e4e7; color: #a1a1aa; cursor: not-allowed; }

.icb__pills {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding-bottom: 2px;
  width: 100%;
}
.icb__pill {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 11px;
  font-weight: 500;
  color: #18181b;
  padding: 1px 7px;
  background: rgba(0,0,0,0.04);
  border-radius: 4px;
}
.icb__pill-x {
  border: none;
  background: none;
  cursor: pointer;
  color: #a1a1aa;
  font-size: 13px;
  padding: 0 1px;
}
.icb__pill-x:hover { color: #18181b; }

.icb__mention-popup {
  position: absolute;
  bottom: 100%;
  left: 0;
  right: 0;
  margin-bottom: 4px;
  background: #fff;
  border: 1px solid rgba(0,0,0,0.1);
  border-radius: 10px;
  max-height: 200px;
  overflow-y: auto;
  z-index: 10;
  box-shadow: 0 4px 12px rgba(0,0,0,0.08);
}
.icb__mention-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  width: 100%;
  border: none;
  background: none;
  cursor: pointer;
  font-size: 12px;
  color: #18181b;
  transition: background 0.1s;
  font-family: inherit;
}
.icb__mention-item:hover { background: #f4f4f5; }
.icb__mention-icon { font-size: 14px; width: 20px; text-align: center; }
.icb__mention-label { flex: 1; text-align: left; }
.icb__mention-type { font-size: 10px; color: #a1a1aa; padding: 1px 6px; background: rgba(0,0,0,0.04); border-radius: 3px; }

.icb-mention-enter-active { transition: opacity 0.12s, transform 0.12s; }
.icb-mention-leave-active { transition: opacity 0.08s; }
.icb-mention-enter-from { opacity: 0; transform: translateY(4px); }
.icb-mention-leave-to { opacity: 0; }
</style>
