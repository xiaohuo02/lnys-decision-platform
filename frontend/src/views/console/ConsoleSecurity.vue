<template>
  <ConsoleTabPage title="安全合规" subtitle="安全策略 · 审计日志" :tabs="TABS" />
</template>

<script setup>
import ConsoleTabPage from '@/components/console/ConsoleTabPage.vue'
import ConsolePolicies from './ConsolePolicies.vue'
import ConsoleAudit from './ConsoleAudit.vue'

const TABS = [
  { label: '安全策略', value: 'policies', component: ConsolePolicies },
  { label: '审计日志', value: 'audit',    component: ConsoleAudit },
]
</script>
