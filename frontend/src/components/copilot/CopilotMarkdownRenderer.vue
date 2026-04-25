<template>
  <div class="cop-md" ref="containerRef">
    <div class="cop-md__content" v-html="renderedHtml"></div>
    <span v-if="streaming" class="cop-md__cursor"></span>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'

const props = defineProps({
  text: { type: String, default: '' },
  streaming: { type: Boolean, default: false },
})

const containerRef = ref(null)

const renderedHtml = computed(() => {
  if (!props.text) return ''
  return parseMarkdown(props.text)
})

watch(() => props.text, async () => {
  await nextTick()
  if (containerRef.value && props.streaming) {
    containerRef.value.scrollTop = containerRef.value.scrollHeight
  }
})

/**
 * Lightweight incremental Markdown → HTML parser.
 * Handles: headings, bold, italic, code, code blocks, links, lists, tables, hr.
 * Designed for streaming: no jitter on partial tokens.
 */
function parseMarkdown(src) {
  const lines = src.split('\n')
  const out = []
  let inCode = false
  let codeLang = ''
  let codeLines = []
  let inTable = false
  let tableRows = []

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]

    // Code block toggle
    if (line.startsWith('```')) {
      if (!inCode) {
        inCode = true
        codeLang = line.slice(3).trim()
        codeLines = []
      } else {
        out.push(renderCodeBlock(codeLines.join('\n'), codeLang))
        inCode = false
        codeLang = ''
        codeLines = []
      }
      continue
    }
    if (inCode) {
      codeLines.push(escHtml(line))
      continue
    }

    // Table detection
    if (line.includes('|') && line.trim().startsWith('|')) {
      if (!inTable) {
        inTable = true
        tableRows = []
      }
      // Skip separator row
      if (/^\|[\s\-:|]+\|$/.test(line.trim())) continue
      tableRows.push(parseCells(line))
      continue
    } else if (inTable) {
      out.push(renderTable(tableRows))
      inTable = false
      tableRows = []
    }

    // HR
    if (/^---+$/.test(line.trim())) {
      out.push('<hr class="cop-md__hr"/>')
      continue
    }

    // Headings
    const hMatch = line.match(/^(#{1,4})\s+(.+)/)
    if (hMatch) {
      const level = hMatch[1].length
      out.push(`<h${level} class="cop-md__h${level}">${inlineFormat(hMatch[2])}</h${level}>`)
      continue
    }

    // Unordered list
    if (/^\s*[-*]\s+/.test(line)) {
      out.push(`<li class="cop-md__li">${inlineFormat(line.replace(/^\s*[-*]\s+/, ''))}</li>`)
      continue
    }

    // Ordered list
    if (/^\s*\d+\.\s+/.test(line)) {
      out.push(`<li class="cop-md__li ol">${inlineFormat(line.replace(/^\s*\d+\.\s+/, ''))}</li>`)
      continue
    }

    // Empty line
    if (!line.trim()) {
      out.push('<div class="cop-md__br"></div>')
      continue
    }

    // Paragraph
    out.push(`<p class="cop-md__p">${inlineFormat(line)}</p>`)
  }

  // Flush remaining
  if (inCode) {
    out.push(renderCodeBlock(codeLines.join('\n'), codeLang))
  }
  if (inTable) {
    out.push(renderTable(tableRows))
  }

  return out.join('')
}

function inlineFormat(s) {
  s = escHtml(s)
  // Bold **text**
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  // Italic *text*
  s = s.replace(/\*(.+?)\*/g, '<em>$1</em>')
  // Inline code `code`
  s = s.replace(/`([^`]+)`/g, '<code class="cop-md__inline-code">$1</code>')
  // Links [text](url)
  s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" class="cop-md__link" target="_blank">$1</a>')
  return s
}

function escHtml(s) {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function renderCodeBlock(code, lang) {
  return `<div class="cop-md__code-block"><div class="cop-md__code-hd">${lang || 'code'}</div><pre class="cop-md__pre"><code>${code}</code></pre></div>`
}

function parseCells(line) {
  return line.split('|').filter(c => c.trim()).map(c => c.trim())
}

function renderTable(rows) {
  if (!rows.length) return ''
  const [header, ...body] = rows
  let html = '<div class="cop-md__table-wrap"><table class="cop-md__table"><thead><tr>'
  for (const c of header) html += `<th>${inlineFormat(c)}</th>`
  html += '</tr></thead><tbody>'
  for (const row of body) {
    html += '<tr>'
    for (const c of row) html += `<td>${inlineFormat(c)}</td>`
    html += '</tr>'
  }
  html += '</tbody></table></div>'
  return html
}
</script>

<style scoped>
.cop-md { line-height: 1.6; color: #18181b; font-size: 14px; position: relative; }
.cop-md__cursor {
  display: inline-block;
  width: 7px; height: 7px;
  border-radius: 50%;
  background: #18181b;
  margin-left: 3px;
  vertical-align: middle;
  animation: cursor-breathe 1.2s ease-in-out infinite;
}
@keyframes cursor-breathe {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.3; transform: scale(0.85); }
}

.cop-md__content :deep(h1) { font-size: 20px; font-weight: 600; margin: 16px 0 8px; }
.cop-md__content :deep(h2) { font-size: 17px; font-weight: 600; margin: 14px 0 6px; }
.cop-md__content :deep(h3) { font-size: 15px; font-weight: 600; margin: 12px 0 4px; }
.cop-md__content :deep(h4) { font-size: 14px; font-weight: 600; margin: 10px 0 4px; }

.cop-md__content :deep(p) { margin: 4px 0; }
.cop-md__content :deep(.cop-md__br) { height: 8px; }

.cop-md__content :deep(strong) { font-weight: 600; }
.cop-md__content :deep(em) { font-style: italic; }

.cop-md__content :deep(.cop-md__inline-code) {
  font-family: 'Geist Mono', monospace; font-size: 12px;
  padding: 1px 5px; background: rgba(0,0,0,0.04); border-radius: 3px;
}

.cop-md__content :deep(.cop-md__link) {
  color: #18181b; text-decoration: underline; text-underline-offset: 2px;
}

.cop-md__content :deep(.cop-md__li) {
  margin-left: 20px; list-style: disc; padding: 1px 0;
}
.cop-md__content :deep(.cop-md__li.ol) { list-style: decimal; }

.cop-md__content :deep(.cop-md__hr) {
  border: none; border-top: 1px solid rgba(0,0,0,0.08); margin: 12px 0;
}

/* Code block */
.cop-md__content :deep(.cop-md__code-block) {
  margin: 8px 0; border: 1px solid rgba(0,0,0,0.06); border-radius: 8px; overflow: hidden;
  background: #1e1e1e;
}
.cop-md__content :deep(.cop-md__code-hd) {
  padding: 6px 12px; font-size: 11px; color: #a1a1aa;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}
.cop-md__content :deep(.cop-md__pre) {
  margin: 0; padding: 12px 16px; overflow-x: auto;
  font-family: 'Geist Mono', monospace; font-size: 12px;
  line-height: 1.5; color: #d4d4d8;
}

/* Table */
.cop-md__content :deep(.cop-md__table-wrap) {
  margin: 8px 0; overflow-x: auto; border: 1px solid rgba(0,0,0,0.06); border-radius: 8px;
}
.cop-md__content :deep(.cop-md__table) {
  width: 100%; border-collapse: collapse; font-size: 13px;
}
.cop-md__content :deep(.cop-md__table th) {
  text-align: left; padding: 8px 12px; font-weight: 500; color: #52525b;
  background: #fafafa; border-bottom: 1px solid rgba(0,0,0,0.08);
}
.cop-md__content :deep(.cop-md__table td) {
  padding: 6px 12px; border-bottom: 1px solid rgba(0,0,0,0.04);
  font-variant-numeric: tabular-nums;
}
</style>
