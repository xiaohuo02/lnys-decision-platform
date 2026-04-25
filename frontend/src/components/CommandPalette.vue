<template>
  <transition name="cmd-fade">
    <div class="cmd-overlay" v-show="visible" @click.self="close">
      <div class="cmd-box" @click.stop>
        <!-- The Input -->
        <div class="cmd-header">
          <svg class="cmd-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input
            ref="inputRef"
            type="text"
            v-model="query"
            class="cmd-input"
            :placeholder="isAskMode ? '向 AI 提问...' : '搜索页面、AI 技能、命令...  输入 ? 切换 AI 问答'"
            @keydown.down.prevent="selectNext"
            @keydown.up.prevent="selectPrev"
            @keydown.enter.prevent="executeSelected"
            @keydown.esc.prevent="close"
          />
          <span v-if="isAskMode" class="cmd-mode-badge">AI</span>
          <button class="cmd-esc" @click="close">ESC</button>
        </div>

        <!-- AI Ask Mode hint -->
        <div v-if="isAskMode && query.length > 1" class="cmd-ask-hint">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
          按 Enter 将问题发送给 AI 助手
        </div>

        <!-- Grouped Result List -->
        <div class="cmd-body" v-if="!isAskMode && groupedResults.length > 0">
          <template v-for="group in groupedResults" :key="group.label">
            <div class="cmd-group-label">{{ group.label }}</div>
            <div
              v-for="cmd in group.items" :key="cmd._idx"
              class="cmd-item"
              :class="{ 'is-active': selectedIndex === cmd._idx }"
              @mouseover="selectedIndex = cmd._idx"
              @click="executeSelected"
            >
              <span class="cmd-item__icon">{{ cmd.emoji }}</span>
              <div class="cmd-item__body">
                <span class="cmd-item__title" v-html="highlight(cmd.title, query)"></span>
                <span v-if="cmd.desc" class="cmd-item__desc">{{ cmd.desc }}</span>
              </div>
              <span v-if="cmd.shortcut" class="cmd-item__shortcut">{{ cmd.shortcut }}</span>
              <span v-if="cmd.badge" class="cmd-item__badge">{{ cmd.badge }}</span>
            </div>
          </template>
        </div>

        <!-- Empty State -->
        <div class="cmd-empty" v-else-if="!isAskMode && query">
          <span>未找到 "{{ query }}" 的结果</span>
        </div>

        <!-- Footer -->
        <div class="cmd-footer">
          <div class="cmd-footer-cmds">
            <span><kbd>↑</kbd><kbd>↓</kbd> 导航</span>
            <span><kbd>↵</kbd> {{ isAskMode ? '提问' : '选择' }}</span>
            <span><kbd>?</kbd> AI 问答</span>
          </div>
          <div class="cmd-footer-brand">⌘K</div>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useTheme } from '@/composables/useTheme'
import { useHotkeys } from '@/composables/useHotkeys'
import { useCopilotStore } from '@/stores/useCopilotStore'
import businessRoutes from '@/router/modules/business'
import consoleRoutes from '@/router/modules/console'

const router = useRouter()
const copilotStore = useCopilotStore()
const { toggle: toggleTheme } = useTheme()
const visible = ref(false)
const query = ref('')
const inputRef = ref(null)
const selectedIndex = ref(0)

const isAskMode = computed(() => query.value.startsWith('?'))

// ── Build commands from routes + skills + actions ──
const allCommands = computed(() => {
  const cmds = []

  // Pages — Business
  businessRoutes.filter(r => r.meta?.title && !r.meta?.hidden).forEach(r => {
    cmds.push({
      title: r.meta.title,
      desc: r.meta.desc || '',
      emoji: '📄',
      group: '页面',
      action: () => router.push('/' + r.path),
    })
  })

  // Pages — Console
  consoleRoutes.filter(r => r.meta?.title && !r.meta?.hidden).forEach(r => {
    cmds.push({
      title: r.meta.title,
      desc: r.meta.desc || '',
      emoji: '⚙️',
      group: '控制台',
      action: () => router.push('/console/' + r.path),
    })
  })

  // AI Skills
  const skills = [
    { title: '客群洞察', desc: '客户 RFM、CLV、流失分析', emoji: '👥', route: '/customer' },
    { title: '销售预测', desc: '多模型融合销售预测', emoji: '📈', route: '/forecast' },
    { title: '欺诈风控', desc: '实时欺诈检测和评分', emoji: '🛡️', route: '/fraud' },
    { title: '舆情分析', desc: '情感识别与话题发现', emoji: '💬', route: '/sentiment' },
    { title: '关联分析', desc: '商品关联规则和推荐', emoji: '🔗', route: '/association' },
    { title: '库存优化', desc: 'ABC-XYZ 分类与补货', emoji: '📦', route: '/inventory' },
    { title: '知识库搜索', desc: '搜索企业知识库', emoji: '📚', route: '/copilot' },
  ]
  skills.forEach(s => {
    cmds.push({
      title: `AI: ${s.title}`,
      desc: s.desc,
      emoji: s.emoji,
      group: 'AI 技能',
      badge: 'skill',
      action: () => router.push(s.route),
    })
  })

  // Quick Actions
  cmds.push(
    { title: '切换深色/浅色模式', emoji: '🌓', group: '操作', action: () => toggleTheme() },
    { title: '新建经营分析', emoji: '🚀', group: '操作', action: () => router.push('/analyze') },
    { title: '生成报告', emoji: '📊', group: '操作', action: () => router.push('/report') },
    { title: '打开 AI 助手', emoji: '🤖', group: '操作', action: () => copilotStore.toggleDrawer(true) },
  )

  return cmds
})

// ── Filtering + grouping ──
const flatFiltered = computed(() => {
  if (isAskMode.value) return []
  const q = query.value.toLowerCase().trim()
  if (!q) return allCommands.value.slice(0, 12)
  return allCommands.value.filter(c =>
    c.title.toLowerCase().includes(q) ||
    (c.desc && c.desc.toLowerCase().includes(q))
  )
})

const groupedResults = computed(() => {
  const groups = {}
  flatFiltered.value.forEach((cmd, i) => {
    const g = cmd.group || '其他'
    if (!groups[g]) groups[g] = { label: g, items: [] }
    groups[g].items.push({ ...cmd, _idx: i })
  })
  return Object.values(groups)
})

function highlight(text, match) {
  if (!match || isAskMode.value) return text
  const q = match.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  if (!q) return text
  return text.replace(new RegExp(`(${q})`, 'gi'), '<strong>$1</strong>')
}

function open() {
  visible.value = true
  query.value = ''
  selectedIndex.value = 0
  nextTick(() => inputRef.value?.focus())
}

function close() { visible.value = false }

function selectNext() {
  if (selectedIndex.value < flatFiltered.value.length - 1) selectedIndex.value++
}
function selectPrev() {
  if (selectedIndex.value > 0) selectedIndex.value--
}

function executeSelected() {
  if (isAskMode.value) {
    const q = query.value.slice(1).trim()
    if (q) {
      copilotStore.toggleDrawer(true)
      copilotStore.ask(q)
      close()
    }
    return
  }
  const cmd = flatFiltered.value[selectedIndex.value]
  if (cmd) { cmd.action(); close() }
}

useHotkeys([
  {
    id: 'cmd-palette-toggle',
    keys: 'ctrl+k',
    label: '打开命令面板',
    group: 'Global',
    allowInInput: true,
    handler: () => (visible.value ? close() : open()),
  },
])

defineExpose({ open, close })
</script>

<style scoped>
.cmd-overlay { position: fixed; inset: 0; z-index: 10000; background: rgba(0,0,0,0.25); backdrop-filter: blur(8px); display: flex; justify-content: center; align-items: flex-start; padding-top: 14vh; }

.cmd-box { width: 100%; max-width: 580px; background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: 14px; box-shadow: 0 20px 40px rgba(0,0,0,0.12); display: flex; flex-direction: column; overflow: hidden; }

/* Header */
.cmd-header { display: flex; align-items: center; padding: 14px 18px; border-bottom: 1px solid var(--v2-border-2); gap: 10px; }
.cmd-icon { color: var(--v2-text-3); flex-shrink: 0; }
.cmd-input { flex: 1; border: none; background: transparent; font-size: 15px; color: var(--v2-text-1); outline: none; font-family: var(--v2-font-sans); }
.cmd-input::placeholder { color: var(--v2-text-4); }
.cmd-mode-badge { font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 4px; background: var(--v2-text-1); color: #fff; letter-spacing: 0.5px; }
.cmd-esc { font-size: 10px; padding: 2px 8px; font-weight: 600; color: var(--v2-text-4); border: 1px solid var(--v2-border-1); border-radius: 4px; background: none; cursor: pointer; font-family: var(--v2-font-mono); }

/* AI hint */
.cmd-ask-hint { display: flex; align-items: center; gap: 8px; padding: 10px 18px; font-size: 12px; color: var(--v2-text-3); background: var(--v2-bg-hover); border-bottom: 1px solid var(--v2-border-2); }

/* Body */
.cmd-body { max-height: 380px; overflow-y: auto; padding: 6px; }
.cmd-group-label { font-size: 10px; font-weight: 600; color: var(--v2-text-4); text-transform: uppercase; letter-spacing: 0.5px; padding: 8px 14px 4px; }

.cmd-item { display: flex; align-items: center; gap: 10px; padding: 8px 14px; border-radius: 8px; cursor: pointer; }
.cmd-item.is-active { background: var(--v2-bg-active, rgba(0,0,0,0.04)); }
.cmd-item__icon { font-size: 15px; width: 22px; text-align: center; flex-shrink: 0; }
.cmd-item__body { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.cmd-item__title { font-size: 13px; color: var(--v2-text-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cmd-item.is-active .cmd-item__title { color: var(--v2-text-1); }
.cmd-item__desc { font-size: 11px; color: var(--v2-text-4); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cmd-item__shortcut { font-size: 10px; color: var(--v2-text-4); background: var(--v2-bg-sunken); padding: 1px 5px; border-radius: 3px; font-family: var(--v2-font-mono); }
.cmd-item__badge { font-size: 9px; font-weight: 600; color: var(--v2-text-3); padding: 1px 5px; border: 1px solid var(--v2-border-1); border-radius: 3px; text-transform: uppercase; letter-spacing: 0.3px; }

:deep(strong) { color: var(--v2-text-1); font-weight: 700; }

.cmd-empty { padding: 32px 20px; text-align: center; font-size: 13px; color: var(--v2-text-4); }

/* Footer */
.cmd-footer { display: flex; justify-content: space-between; align-items: center; padding: 10px 18px; border-top: 1px solid var(--v2-border-2); background: var(--v2-bg-hover); }
.cmd-footer-cmds { display: flex; gap: 14px; font-size: 11px; color: var(--v2-text-4); }
.cmd-footer-brand { font-size: 11px; color: var(--v2-text-4); font-family: var(--v2-font-mono); font-weight: 600; }
kbd { font-family: var(--v2-font-mono); background: var(--v2-bg-card); border: 1px solid var(--v2-border-1); border-radius: 3px; padding: 0px 3px; font-size: 10px; color: var(--v2-text-3); }

.cmd-fade-enter-active, .cmd-fade-leave-active { transition: opacity 0.15s ease; }
.cmd-fade-enter-from, .cmd-fade-leave-to { opacity: 0; }
</style>
