<template>
  <div class="jp">
    <div v-if="showToolbar" class="jp__toolbar">
      <span class="jp__title">{{ title }}</span>
      <div class="jp__actions">
        <button class="jp__btn" @click="toggleCollapse" :title="allCollapsed ? '展开全部' : '折叠全部'">
          <el-icon :size="13"><component :is="allCollapsed ? 'ArrowDown' : 'ArrowUp'" /></el-icon>
        </button>
        <button class="jp__btn" @click="copyJson" title="复制 JSON">
          <el-icon :size="13"><CopyDocument /></el-icon>
        </button>
      </div>
    </div>
    <div class="jp__body" ref="bodyRef">
      <pre class="jp__pre"><code v-html="highlighted" /></pre>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { CopyDocument } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  data:        { type: [Object, Array, String, Number, Boolean, null], default: null },
  title:       { type: String, default: 'JSON' },
  showToolbar: { type: Boolean, default: true },
  maxHeight:   { type: String, default: '' },
  indent:      { type: Number, default: 2 },
})

const bodyRef = ref(null)
const allCollapsed = ref(false)

const jsonString = computed(() => {
  if (props.data === null || props.data === undefined) return 'null'
  try {
    return typeof props.data === 'string'
      ? JSON.stringify(JSON.parse(props.data), null, props.indent)
      : JSON.stringify(props.data, null, props.indent)
  } catch {
    return String(props.data)
  }
})

const highlighted = computed(() => syntaxHighlight(jsonString.value))

function syntaxHighlight(json) {
  return json
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(
      /("(\\u[\da-fA-F]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)/g,
      (match) => {
        let cls = 'jp--number'
        if (/^"/.test(match)) {
          cls = /:$/.test(match) ? 'jp--key' : 'jp--string'
        } else if (/true|false/.test(match)) {
          cls = 'jp--boolean'
        } else if (/null/.test(match)) {
          cls = 'jp--null'
        }
        return `<span class="${cls}">${match}</span>`
      }
    )
}

function toggleCollapse() {
  allCollapsed.value = !allCollapsed.value
}

async function copyJson() {
  try {
    await navigator.clipboard.writeText(jsonString.value)
    ElMessage.success({ message: '已复制', duration: 1500 })
  } catch {
    ElMessage.error('复制失败')
  }
}
</script>

<style scoped>
.jp {
  border: 1px solid var(--v2-border-2);
  border-radius: var(--v2-radius-lg);
  background: var(--v2-bg-sunken);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.jp__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--v2-space-2) var(--v2-space-3);
  border-bottom: 1px solid var(--v2-border-2);
  background: var(--v2-bg-card);
}
.jp__title {
  font-size: var(--v2-text-xs);
  font-weight: var(--v2-font-semibold);
  color: var(--v2-text-3);
  text-transform: uppercase;
  letter-spacing: .3px;
}
.jp__actions {
  display: flex;
  gap: 4px;
}
.jp__btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px; height: 24px;
  border: none;
  border-radius: var(--v2-radius-sm);
  background: transparent;
  color: var(--v2-text-3);
  cursor: pointer;
  transition: all var(--v2-trans-fast);
}
.jp__btn:hover {
  background: var(--v2-bg-hover);
  color: var(--v2-text-1);
}

.jp__body {
  overflow: auto;
  max-height: v-bind("maxHeight || 'none'");
  padding: var(--v2-space-3);
}

.jp__pre {
  margin: 0;
  font-family: var(--v2-font-mono);
  font-size: var(--v2-text-xs);
  line-height: var(--v2-leading-relaxed);
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--v2-text-2);
}
</style>

<style>
/* Syntax highlight colors — unscoped so v-html can pick them up */
.jp--key     { color: #3b82f6; }
.jp--string  { color: #22c55e; }
.jp--number  { color: #f59e0b; }
.jp--boolean { color: #a78bfa; }
.jp--null    { color: #6b7280; font-style: italic; }

html[data-theme="dark"] .jp--key     { color: #60a5fa; }
html[data-theme="dark"] .jp--string  { color: #4ade80; }
html[data-theme="dark"] .jp--number  { color: #fbbf24; }
html[data-theme="dark"] .jp--boolean { color: #c4b5fd; }
html[data-theme="dark"] .jp--null    { color: #9ca3af; }
</style>
