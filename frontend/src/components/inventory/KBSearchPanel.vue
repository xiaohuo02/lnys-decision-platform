<template>
  <div class="kbs">
    <div class="kbs__search">
      <svg class="kbs__search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
      <input
        ref="inputRef"
        v-model="query"
        class="kbs__input"
        placeholder="搜索库存管理知识..."
        @keydown.enter="search"
      />
      <button v-if="query" class="kbs__clear" @click="query = ''; results = []">&times;</button>
    </div>

    <div class="kbs__results" v-if="results.length">
      <div
        v-for="(doc, i) in results"
        :key="i"
        class="kbs__doc"
        @click="$emit('docClick', doc)"
      >
        <div class="kbs__doc-title">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
          {{ doc.title || doc.name || '文档 ' + (i + 1) }}
        </div>
        <p class="kbs__doc-snippet">{{ doc.snippet || doc.content?.slice(0, 120) || '' }}</p>
        <div class="kbs__doc-meta">
          <span v-if="doc.collection" class="kbs__doc-collection">{{ doc.collection }}</span>
          <span v-if="doc.score" class="kbs__doc-score">{{ (doc.score * 100).toFixed(0) }}% 匹配</span>
        </div>
      </div>
    </div>

    <div class="kbs__empty" v-else-if="searched && !loading">
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="15" x2="15" y2="15"/></svg>
      <p>{{ query ? '未找到相关文档' : '暂无知识库文档' }}</p>
    </div>

    <div class="kbs__hint" v-else-if="!searched">
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1"><path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/></svg>
      <p>搜索补货SOP、库存管理规范等知识库文档</p>
      <div class="kbs__suggestions">
        <button v-for="s in suggestions" :key="s" class="kbs__sug-btn" @click="query = s; search()">{{ s }}</button>
      </div>
    </div>

    <div class="kbs__loading" v-if="loading">
      <span class="kbs__spinner"></span>
      搜索中...
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

defineEmits(['docClick'])

const query = ref('')
const results = ref([])
const loading = ref(false)
const searched = ref(false)
const inputRef = ref(null)

const suggestions = [
  '补货流程SOP',
  '安全库存计算方法',
  'ABC分类标准',
]

async function search() {
  const q = query.value.trim()
  if (!q) return
  loading.value = true
  searched.value = true

  // Simulate KB RAG search — in production, this calls the kb_rag skill or a dedicated API
  try {
    await new Promise(r => setTimeout(r, 600))
    results.value = [
      {
        title: `${q}相关文档`,
        snippet: `这是关于「${q}」的知识库文档摘要。实际使用中，此处将返回 Milvus/ChromaDB 的向量检索结果。`,
        collection: 'inventory_docs',
        score: 0.87,
      },
      {
        title: '库存管理操作手册 v2.1',
        snippet: '本手册涵盖日常库存盘点、补货申请流程、异常处理等操作指引...',
        collection: 'ops_manual',
        score: 0.72,
      },
    ]
  } catch {
    results.value = []
  } finally {
    loading.value = false
  }
}

defineExpose({ focus: () => inputRef.value?.focus() })
</script>

<style scoped>
.kbs { display: flex; flex-direction: column; height: 100%; }

.kbs__search {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid rgba(0,0,0,0.06);
  flex-shrink: 0;
}
.kbs__search-icon { color: #a1a1aa; flex-shrink: 0; }
.kbs__input {
  flex: 1;
  border: none;
  outline: none;
  font-size: 13px;
  background: transparent;
  font-family: inherit;
  color: #18181b;
}
.kbs__input::placeholder { color: #a1a1aa; }
.kbs__clear {
  border: none;
  background: none;
  cursor: pointer;
  color: #a1a1aa;
  font-size: 16px;
  padding: 0 4px;
}
.kbs__clear:hover { color: #18181b; }

.kbs__results {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}
.kbs__doc {
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.1s;
  margin-bottom: 4px;
}
.kbs__doc:hover { background: rgba(0,0,0,0.03); }
.kbs__doc-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 500;
  color: #18181b;
  margin-bottom: 4px;
}
.kbs__doc-snippet {
  font-size: 12px;
  color: #71717a;
  line-height: 1.5;
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.kbs__doc-meta {
  display: flex;
  gap: 8px;
  margin-top: 6px;
}
.kbs__doc-collection {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  background: rgba(0,0,0,0.04);
  color: #71717a;
}
.kbs__doc-score {
  font-size: 10px;
  color: #a1a1aa;
  font-variant-numeric: tabular-nums;
}

.kbs__empty, .kbs__hint {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #a1a1aa;
  padding: 20px;
}
.kbs__empty p, .kbs__hint p { font-size: 12px; margin: 0; text-align: center; }

.kbs__suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
  justify-content: center;
}
.kbs__sug-btn {
  padding: 5px 12px;
  border: 1px solid rgba(0,0,0,0.08);
  border-radius: 999px;
  background: #fff;
  font-size: 12px;
  color: #18181b;
  cursor: pointer;
  transition: all 0.15s;
  font-family: inherit;
}
.kbs__sug-btn:hover { background: #f4f4f5; border-color: rgba(0,0,0,0.15); }

.kbs__loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px;
  font-size: 12px;
  color: #71717a;
}
.kbs__spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(0,0,0,0.1);
  border-top-color: #18181b;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
