<template>
  <div class="cop-artifact" v-if="artifact && artifact.content">
    <div class="cop-artifact__hd">
      <span class="cop-artifact__icon">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></svg>
      </span>
      <span class="cop-artifact__title">{{ artifact.metadata?.title || artifact.type }}</span>
      <span class="cop-artifact__badge" v-if="!artifact.closed">loading...</span>
    </div>
    <div class="cop-artifact__body">
      <component
        v-if="resolvedComponent"
        :is="resolvedComponent"
        :data="artifact.content"
        :metadata="artifact.metadata"
      />
      <pre v-else class="cop-artifact__fallback">{{ JSON.stringify(artifact.content, null, 2) }}</pre>
    </div>
  </div>
</template>

<script setup>
import { computed, defineAsyncComponent } from 'vue'

const props = defineProps({
  artifact: { type: Object, required: true },
})

const componentMap = {
  inventory_table:   defineAsyncComponent(() => import('./artifacts/InventoryArtifact.vue')),
  forecast_chart:    defineAsyncComponent(() => import('./artifacts/ForecastArtifact.vue')),
  sentiment_overview: defineAsyncComponent(() => import('./artifacts/SentimentArtifact.vue')),
  customer_insight:  defineAsyncComponent(() => import('./artifacts/CustomerArtifact.vue')),
  fraud_detail:      defineAsyncComponent(() => import('./artifacts/GenericTableArtifact.vue')),
  association_graph: defineAsyncComponent(() => import('./artifacts/GenericTableArtifact.vue')),
  search_results:    defineAsyncComponent(() => import('./artifacts/SearchResultsArtifact.vue')),
  generic_table:     defineAsyncComponent(() => import('./artifacts/GenericTableArtifact.vue')),
}

const resolvedComponent = computed(() => {
  return componentMap[props.artifact?.type] || null
})
</script>

<style scoped>
.cop-artifact {
  border: 1px solid rgba(0,0,0,0.06);
  border-radius: 8px;
  overflow: hidden;
  margin: 12px 0;
  background: #fafafa;
}
.cop-artifact__hd {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-bottom: 1px solid rgba(0,0,0,0.04);
  font-size: 13px;
  font-weight: 500;
  color: #18181b;
}
.cop-artifact__icon { color: #71717a; display: flex; }
.cop-artifact__title { flex: 1; }
.cop-artifact__badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(0,0,0,0.04);
  color: #71717a;
  animation: pulse 1.5s infinite;
}
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }
.cop-artifact__body { padding: 16px; }
.cop-artifact__fallback {
  font-size: 12px;
  font-family: 'Geist Mono', monospace;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 300px;
  overflow: auto;
  color: #52525b;
  margin: 0;
}
</style>
