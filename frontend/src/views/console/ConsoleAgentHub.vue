<template>
  <ConsoleTabPage title="智能体中枢" subtitle="Agent 与 Workflow 统一管理" :tabs="TABS" />
</template>

<script setup>
import ConsoleTabPage from '@/components/console/ConsoleTabPage.vue'
import ConsoleAgents from './ConsoleAgents.vue'
import ConsoleWorkflows from './ConsoleWorkflows.vue'

const TABS = [
  { label: '智能体', value: 'agents',    component: ConsoleAgents },
  { label: '工作流', value: 'workflows', component: ConsoleWorkflows },
]
</script>
