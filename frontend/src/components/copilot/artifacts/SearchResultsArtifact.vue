<template>
  <div class="sr-art">
    <div class="sr-art__query" v-if="data?.query">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
      <span>{{ data.query }}</span>
    </div>
    <div class="sr-art__list" v-if="data?.results?.length">
      <div v-for="(r, i) in data.results" :key="i" class="sr-art__item">
        <div class="sr-art__item-hd">
          <span class="sr-art__item-idx">#{{ i + 1 }}</span>
          <span class="sr-art__item-score" v-if="r.score != null">{{ (r.score * 100).toFixed(0) }}%</span>
        </div>
        <div class="sr-art__item-content">{{ r.content || r.document || '-' }}</div>
        <div class="sr-art__item-meta" v-if="r.metadata && Object.keys(r.metadata).length">
          <span v-for="(v, k) in r.metadata" :key="k" class="sr-art__meta-chip">{{ k }}: {{ v }}</span>
        </div>
      </div>
    </div>
    <div class="sr-art__empty" v-else>No results found</div>
  </div>
</template>

<script setup>
defineProps({ data: Object, metadata: Object })
</script>

<style scoped>
.sr-art__query { display: flex; align-items: center; gap: 8px; font-size: 13px; color: #71717a; margin-bottom: 12px; }
.sr-art__list { display: flex; flex-direction: column; gap: 8px; }
.sr-art__item { padding: 12px; border: 1px solid rgba(0,0,0,0.04); border-radius: 6px; background: #fff; }
.sr-art__item-hd { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.sr-art__item-idx { font-size: 11px; font-weight: 600; color: #71717a; }
.sr-art__item-score { font-size: 11px; padding: 2px 8px; border-radius: 999px; background: rgba(0,0,0,0.04); font-variant-numeric: tabular-nums; }
.sr-art__item-content { font-size: 13px; line-height: 1.6; color: #18181b; }
.sr-art__item-meta { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
.sr-art__meta-chip { font-size: 11px; padding: 2px 8px; border-radius: 999px; background: rgba(0,0,0,0.03); color: #71717a; }
.sr-art__empty { font-size: 13px; color: #a1a1aa; text-align: center; padding: 24px; }
</style>
