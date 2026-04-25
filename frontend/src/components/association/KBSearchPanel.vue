<template>
  <div class="kb">
    <div class="kb__search">
      <input
        v-model="query"
        class="kb__input"
        placeholder="搜索交叉营销策略 / 陈列 SOP..."
        @keydown.enter="doSearch"
      />
      <button class="kb__btn" :disabled="!query.trim() || searching" @click="doSearch">搜索</button>
    </div>

    <div v-if="searching" class="kb__status">正在检索知识库…</div>

    <div v-if="sources.length" class="kb__results">
      <div v-for="(src, i) in sources" :key="i" class="kb__doc">
        <div class="kb__doc-head">
          <span class="kb__doc-title">{{ src.title || src.source || '未命名文档' }}</span>
          <span v-if="src.score" class="kb__doc-score">{{ (src.score * 100).toFixed(0) }}%</span>
        </div>
        <p v-if="src.content || src.snippet" class="kb__doc-snippet">{{ (src.content || src.snippet || '').slice(0, 200) }}</p>
        <span v-if="src.collection" class="kb__doc-source">{{ src.collection }}</span>
      </div>
    </div>

    <div v-if="aiText" class="kb__ai-answer">
      <div class="kb__ai-label">AI 摘要</div>
      <div class="kb__ai-text" v-html="aiText.replace(/\n/g, '<br>')"></div>
    </div>

    <div v-if="!searching && !sources.length && !aiText" class="kb__empty">
      <p>输入关键词搜索知识库</p>
      <div class="kb__suggestions">
        <button v-for="s in defaultQueries" :key="s" class="kb__chip" @click="query = s; doSearch()">{{ s }}</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  askAgent: { type: Function, required: true },
  sources:  { type: Array, default: () => [] },
  aiText:   { type: String, default: '' },
  streaming:{ type: Boolean, default: false },
})

const query = ref('')
const searching = ref(false)

const defaultQueries = [
  '交叉营销策略',
  '搭配陈列 SOP',
  '组合促销方案模板',
]

async function doSearch() {
  const q = query.value.trim()
  if (!q) return
  searching.value = true
  try {
    await props.askAgent('kb_rag', `关联分析知识库查询: ${q}`)
  } finally {
    searching.value = false
  }
}
</script>

<style scoped>
.kb { padding: var(--v2-space-3); display: flex; flex-direction: column; gap: var(--v2-space-3); height: 100%; overflow-y: auto; }
.kb__search { display: flex; gap: var(--v2-space-2); }
.kb__input { flex: 1; padding: 6px 10px; border: 1px solid var(--v2-border-1); border-radius: var(--v2-radius-md); background: var(--v2-bg-sunken); color: var(--v2-text-1); font-size: var(--v2-text-xs); font-family: var(--v2-font-sans); outline: none; transition: border-color var(--v2-trans-fast); }
.kb__input:focus { border-color: var(--v2-brand-primary); }
.kb__input::placeholder { color: var(--v2-text-4); }
.kb__btn { padding: 6px 12px; font-size: var(--v2-text-xs); font-weight: 500; border: 1px solid var(--v2-border-1); border-radius: var(--v2-radius-md); background: var(--v2-text-1); color: #fff; cursor: pointer; }
.kb__btn:disabled { opacity: .4; cursor: not-allowed; }
.kb__status { font-size: var(--v2-text-xs); color: var(--v2-text-3); }
.kb__results { display: flex; flex-direction: column; gap: var(--v2-space-2); }
.kb__doc { padding: var(--v2-space-2) var(--v2-space-3); background: var(--v2-bg-sunken); border-radius: var(--v2-radius-md); border: 1px solid var(--v2-border-2); }
.kb__doc-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.kb__doc-title { font-size: var(--v2-text-xs); font-weight: 600; color: var(--v2-text-1); }
.kb__doc-score { font-size: 10px; color: var(--v2-text-3); }
.kb__doc-snippet { font-size: var(--v2-text-xs); color: var(--v2-text-2); line-height: 1.5; margin: 0; }
.kb__doc-source { font-size: 10px; color: var(--v2-text-4); margin-top: 4px; display: inline-block; }
.kb__ai-answer { padding: var(--v2-space-3); background: var(--v2-ai-purple-bg, var(--v2-bg-sunken)); border-radius: var(--v2-radius-md); }
.kb__ai-label { font-size: 10px; font-weight: 600; color: var(--v2-ai-purple, var(--v2-text-3)); text-transform: uppercase; letter-spacing: .5px; margin-bottom: 4px; }
.kb__ai-text { font-size: var(--v2-text-xs); color: var(--v2-text-1); line-height: 1.6; }
.kb__empty { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: var(--v2-space-3); color: var(--v2-text-4); font-size: var(--v2-text-sm); }
.kb__suggestions { display: flex; flex-wrap: wrap; gap: var(--v2-space-2); justify-content: center; }
.kb__chip { padding: 4px 10px; font-size: var(--v2-text-xs); border: 1px solid var(--v2-border-1); border-radius: var(--v2-radius-full); background: var(--v2-bg-card); color: var(--v2-text-2); cursor: pointer; transition: all var(--v2-trans-fast); }
.kb__chip:hover { background: var(--v2-bg-sunken); color: var(--v2-text-1); }
</style>
