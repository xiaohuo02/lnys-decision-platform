<template>
  <div class="v2-md-container" :class="{ 'is-streaming': streaming }">
    <!-- Render the converted markdown to HTML -->
    <div class="markdown-body" v-html="renderedHtml"></div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'
const props = defineProps({
  content: { type: String, default: '' },
  streaming: { type: Boolean, default: false }
})

// Advanced setup for markdown-it
const md = new MarkdownIt({
  html: true,
  breaks: true,
  linkify: true,
  typographer: true,
})

// In a real extreme-performance scenario, we'd write a custom token-based AST 
// reconciler. Here, to ensure stability within the competition timeline, 
// we use markdown-it with a trailing cursor trick.
const renderedHtml = computed(() => {
  let text = props.content || ''
  
  // If streaming, append the bespoke blinking block cursor
  if (props.streaming) {
    text += ' █'
  }
  
  return md.render(text)
})
</script>

<style>
/* 
  Global Markdown styling scoped to the container.
  Zero-component smell. Pure typography. 
*/
.v2-md-container {
  font-family: var(--v2-font-sans);
  color: var(--v2-text-1);
  line-height: 1.6;
  font-size: 15px;
}

.markdown-body {
  word-break: break-word;
}

.markdown-body p {
  margin-top: 0;
  margin-bottom: 16px;
}

.markdown-body p:last-child {
  margin-bottom: 0;
}

/* Blinking Cursor for Streaming */
.markdown-body p:last-child::after {
  content: '';
  /* The block cursor is rendered as part of text, but we can target the █ char if needed. */
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

.is-streaming .markdown-body p:last-child {
  /* Make the last text node containing the block blink */
  animation: none;
}

/* Headings - Geist tight tracking */
.markdown-body h1, .markdown-body h2, .markdown-body h3,
.markdown-body h4, .markdown-body h5, .markdown-body h6 {
  margin-top: 24px;
  margin-bottom: 12px;
  font-weight: 600;
  line-height: 1.25;
  color: var(--v2-text-1);
  letter-spacing: -0.02em;
}

.markdown-body h1 { font-size: 2em; }
.markdown-body h2 { font-size: 1.5em; padding-bottom: 0.3em; border-bottom: var(--v2-border-width) solid var(--v2-border-2); }
.markdown-body h3 { font-size: 1.25em; }

/* Lists */
.markdown-body ul, .markdown-body ol {
  padding-left: 2em;
  margin-top: 0;
  margin-bottom: 16px;
}

.markdown-body li {
  margin-bottom: 4px;
}

/* Inline Code */
.markdown-body code {
  font-family: var(--v2-font-mono);
  font-size: 85%;
  background-color: var(--v2-bg-hover);
  padding: 0.2em 0.4em;
  border-radius: 6px;
  color: var(--v2-text-1);
}

/* Code Blocks */
.markdown-body pre {
  margin-top: 0;
  margin-bottom: 16px;
  background-color: var(--v2-bg-sunken, #121212) !important; /* Zinc 900 */
  padding: 16px;
  overflow: auto;
  border-radius: 8px;
  border: var(--v2-border-width) solid var(--v2-border-2);
}

.markdown-body pre code {
  background-color: transparent;
  padding: 0;
  border-radius: 0;
  color: #e7e9ea; /* Default light text for code block */
  font-size: 13px;
  line-height: 1.45;
}

/* Tables */
.markdown-body table {
  border-collapse: collapse;
  width: 100%;
  margin-bottom: 16px;
}

.markdown-body table th,
.markdown-body table td {
  padding: 8px 12px;
  border: var(--v2-border-width) solid var(--v2-border-2);
  font-size: 14px;
}

.markdown-body table th {
  font-weight: 600;
  background-color: var(--v2-bg-hover);
  text-align: left;
}

/* Blockquotes */
.markdown-body blockquote {
  margin: 0 0 16px;
  padding: 0 1em;
  color: var(--v2-text-3);
  border-left: 0.25em solid var(--v2-border-2);
}
</style>
