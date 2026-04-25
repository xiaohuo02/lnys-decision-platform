<template>
  <ConsoleTabPage title="知识与记忆" subtitle="记忆治理 · 新鲜度（知识库已合并入知识库中台）" :tabs="TABS" />
</template>

<script setup>
import ConsoleTabPage from '@/components/console/ConsoleTabPage.vue'
import ConsoleKnowledgeLegacy from './ConsoleKnowledgeLegacy.vue'
import ConsoleMemory from './ConsoleMemory.vue'
import MemoryGovernance from '@/components/telemetry/MemoryGovernance.vue'

const TABS = [
  { label: '知识库',   value: 'knowledge', component: ConsoleKnowledgeLegacy },
  { label: '记忆治理', value: 'memory',    component: ConsoleMemory },
  { label: '新鲜度',   value: 'freshness', component: MemoryGovernance },
]
</script>
