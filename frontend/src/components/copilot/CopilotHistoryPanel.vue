<template>
  <div class="cop-hist">
    <div class="cop-hist__hd">
      <span class="cop-hist__title">History</span>
      <button class="cop-hist__new-btn" @click="$emit('new-thread')">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 5v14M5 12h14"/></svg>
      </button>
    </div>
    <div class="cop-hist__list" v-if="threads.length">
      <div
        v-for="t in threads"
        :key="t.id"
        class="cop-hist__item"
        :class="{ 'cop-hist__item--active': t.id === activeThreadId }"
        @click="$emit('select-thread', t.id)"
      >
        <div class="cop-hist__item-title">{{ t.title || 'Untitled' }}</div>
        <div class="cop-hist__item-meta">
          <span class="cop-hist__item-mode">{{ t.mode }}</span>
          <span class="cop-hist__item-time">{{ formatTime(t.updated_at) }}</span>
        </div>
        <div class="cop-hist__item-pin" v-if="t.pinned" @click.stop="$emit('toggle-pin', t.id, false)">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
        </div>
      </div>
    </div>
    <div class="cop-hist__empty" v-else>No conversations yet</div>
  </div>
</template>

<script setup>
defineProps({
  threads: { type: Array, default: () => [] },
  activeThreadId: { type: String, default: '' },
})
defineEmits(['new-thread', 'select-thread', 'toggle-pin'])

function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  const now = new Date()
  const diffMs = now - d
  if (diffMs < 60000) return 'just now'
  if (diffMs < 3600000) return Math.floor(diffMs / 60000) + 'm ago'
  if (diffMs < 86400000) return Math.floor(diffMs / 3600000) + 'h ago'
  return d.toLocaleDateString()
}
</script>

<style scoped>
.cop-hist { display: flex; flex-direction: column; height: 100%; }
.cop-hist__hd { display: flex; align-items: center; padding: 16px 16px 12px; }
.cop-hist__title { flex: 1; font-size: 14px; font-weight: 600; color: #18181b; }
.cop-hist__new-btn { width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; border: 1px solid rgba(0,0,0,0.08); border-radius: 6px; background: #fff; cursor: pointer; color: #71717a; }
.cop-hist__new-btn:hover { background: #f4f4f5; color: #18181b; }
.cop-hist__list { flex: 1; overflow-y: auto; padding: 0 8px; }
.cop-hist__item { padding: 10px 12px; border-radius: 6px; cursor: pointer; margin-bottom: 2px; position: relative; }
.cop-hist__item:hover { background: rgba(0,0,0,0.03); }
.cop-hist__item--active { background: rgba(0,0,0,0.05); }
.cop-hist__item-title { font-size: 13px; font-weight: 500; color: #18181b; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cop-hist__item-meta { display: flex; gap: 8px; margin-top: 4px; }
.cop-hist__item-mode { font-size: 11px; padding: 1px 6px; border-radius: 3px; background: rgba(0,0,0,0.04); color: #71717a; }
.cop-hist__item-time { font-size: 11px; color: #a1a1aa; }
.cop-hist__item-pin { position: absolute; top: 10px; right: 12px; color: #f59e0b; }
.cop-hist__empty { flex: 1; display: flex; align-items: center; justify-content: center; font-size: 13px; color: #a1a1aa; }
</style>
